"""阶段判定与动态子力价值（Task 8）；对外分析接口（Task 12）。

Java 参考：
- `AICoreHandler.getPhase` L112-130：中局/残局判定；
- `AICoreHandler.moveBegin` L132-142：兵/卒、马、炮的动态子力价值；
- `AICoreHandler.run` L42-65 的"迭代加深 + 时限/停旗"外层控制（Task 12 的
  `analyze` 以生成器逐层产出，把时间控制上移到 Python 层）。

约定与差异：
- Java 的时序是"先用静态子力表算 baseScore、之后 moveBegin 才改动态子力表"，
  导致同一局面的 baseScore 与后续走子增量使用不同的子力值；本项目 `prepare`
  统一为"动态子力 + 当前阶段位置表全量重算 base_score"，属**有意简化**
  （更自洽，增量与全量恒等）。
- 兵/卒的动态值使用**兵所属方自己**的攻击子数：Java moveBegin 中黑卒传
  `BLACKPLAYSIGN`、红兵传 `REDPLAYSIGN`，即 `getAttackChessesNum(己方)`；
  迁移笔记 5.2 写作"对方攻击子数"系笔误，此处以 Java 源码为准。
- `st.piece_scores`/`st.phase` 由 `position.State` 以视图 property 提供
  （分别打包在 `base_score[_PIECE_SCORES_OFFSET:...]`、
  `side_to_move[_PHASE_SLOT]`），此处可直接读写；njit 热路径按索引或
  `position.get_phase` 访问，理由见 `position` 模块 docstring。

Task 12（`analyze`/`warmup`）语义要点：
- 逐层迭代加深：从 `constants.ROOT_START_DEPTH`（4）搜到 `max_depth`，
  **只有 `depth >= start_depth` 的完成层才产出**（4/5 层是垫脚石，让首个
  结果更快且复用 TT/PV 排序）；
- 停旗与时限的检查在**层边界**：搜索进行中被其他线程置位 `stop` 的层结果
  不可信（见 `search_depth` docstring），直接丢弃不产出；**中断契约：
  `stop` 一旦置位，直到生成器结束前不得复位**——内部按 `stop[0]` 判定，
  复用同一停旗数组存在 TOCTOU 窗口；
- 时限为**层边界软时限 + 时间预算外推**：完成一层后，除检查累计耗时外，
  还按"上一层耗时 × 1.5"预估下一层；预判超支即不再开始下一层，把单层
  耗时不可预估的风险收敛到"最后一层最多约为上一层的 1.5 倍"；
- `start_depth > max_depth` 时提前返回（不加载局面、不分配 `Ctx`/`Stack`）；
- 每次 `analyze` 新建 `Ctx`（默认 40MB 置换表），生成器结束时显式释放；
- `warmup` 用初始局面触发全链 JIT 编译并计入日志，`_WARMED` 保证幂等。
"""

import dataclasses
import logging
import os
import threading
import time

import numpy as np
from numba import njit

from . import constants as C
from .position import full_base_score, load_position

__all__ = [
    "END_GAME",
    "MAX_THREADS",
    "MIDDLE_GAME",
    "AnalysisResult",
    "_resolve_threads",
    "analyze",
    "dynamic_piece_scores",
    "phase_of",
    "prepare",
    "warmup",
]

# 与 position.State.phase / attach_score 的取值约定一致
MIDDLE_GAME = 0
END_GAME = 1


@njit(cache=True)
def phase_of(st):
    """阶段判定（对应 Java `AICoreHandler.getPhase`）。

    redChessNum = 红车 + 红马 + 红炮 + (红兵 > 3 ? 1 : 0)，黑方同理；
    两者之和 < 7 → END_GAME，否则 MIDDLE_GAME。
    """
    red = 0
    red += int(st.remain[C.RED_CHARIOT])
    red += int(st.remain[C.RED_KNIGHT])
    red += int(st.remain[C.RED_GUN])
    if st.remain[C.RED_SOLDIER] > 3:
        red += 1
    black = 0
    black += int(st.remain[C.BLACK_CHARIOT])
    black += int(st.remain[C.BLACK_KNIGHT])
    black += int(st.remain[C.BLACK_GUN])
    if st.remain[C.BLACK_SOLDIER] > 3:
        black += 1
    if red + black < 7:
        return END_GAME
    return MIDDLE_GAME


@njit(cache=True)
def dynamic_piece_scores(st):
    """动态子力价值（对应 Java `AICoreHandler.moveBegin` L132-142）。

    返回新的 `np.int32[15]`（索引 = 角色 1..14，不修改只读常量表）：

    - 兵/卒 = 100 + (11 - 己方攻击子数) * 8（兵所属方自己的车马炮兵数）；
    - 马 = 490 + (32 - 全场剩余棋子数) * 6（越到残局越升值）；
    - 炮 = 610 - (32 - 全场剩余棋子数) * 6（越到残局越贬值）；
    - 其余角色保持 `constants.PIECE_SCORES`。
    """
    scores = np.copy(C.PIECE_SCORES)
    total = 0
    for role in range(1, 15):
        total += int(st.remain[role])
    left = 32 - total
    scores[C.BLACK_SOLDIER] = np.int32(
        100 + (11 - int(st.attack_def[C.BLACK, 0])) * 8
    )
    scores[C.RED_SOLDIER] = np.int32(
        100 + (11 - int(st.attack_def[C.RED, 0])) * 8
    )
    scores[C.BLACK_KNIGHT] = np.int32(490 + left * 6)
    scores[C.RED_KNIGHT] = np.int32(490 + left * 6)
    scores[C.BLACK_GUN] = np.int32(610 - left * 6)
    scores[C.RED_GUN] = np.int32(610 - left * 6)
    return scores


def prepare(st):
    """搜索前一次性准备：动态子力 → 阶段 → base_score 全量重算。

    顺序：
    1. `st.piece_scores[:] = dynamic_piece_scores(st)`（视图写入）；
    2. `st.phase[0] = phase_of(st)`（视图写入）；
    3. `base_score = full_base_score(st)` 写回（动态子力 + 当前阶段位置表）。

    Java 中 baseScore 先于动态子力表刷新，本项目统一为先写动态表再全量重算
    （有意简化，见模块 docstring）；此后 make/unmake 的增量维护与之恒等。
    """
    st.piece_scores[:] = dynamic_piece_scores(st)
    st.phase[0] = np.int8(phase_of(st))
    red, black = full_base_score(st)
    st.base_score[C.RED] = np.int32(red)
    st.base_score[C.BLACK] = np.int32(black)


# --------------------------------------------------------------------------
# Task 12：对外分析接口（渐进加深生成器）
# --------------------------------------------------------------------------

_log = logging.getLogger(__name__)

# 并行搜索线程数上限（含主线程）。
MAX_THREADS = 16

# 自动线程数：核数 - 1（给 UI/系统留余量），最多 8。
_AUTO_THREADS_MAX = 8


def _resolve_threads(threads):
    """解析并行线程数：显式参数 > 环境变量 `ENGINE_THREADS` > 自动。

    自动值 = `max(1, min(cpu_count - 1, 8))`；显式值夹逼到 `[1, MAX_THREADS]`；
    不可转换为整数的值回退自动；浮点/布尔按 `int()` 语义转换。
    """
    if threads is None:
        raw = os.environ.get("ENGINE_THREADS")
        if raw is not None:
            try:
                threads = int(raw)
            except ValueError:
                threads = None
    if threads is None:
        return max(1, min((os.cpu_count() or 1) - 1, _AUTO_THREADS_MAX))
    try:
        threads = int(threads)
    except (TypeError, ValueError, OverflowError):
        return max(1, min((os.cpu_count() or 1) - 1, _AUTO_THREADS_MAX))
    return max(1, min(threads, MAX_THREADS))

# 分析深度硬上限（防外部传参失控；与 Java 最高难度 32 层一致）。
MAX_ANALYSIS_DEPTH = 32

# PV 对外拷贝的最大步数（不必把 68 长的三角表整行带走）。
PV_LIMIT = 8

# 将杀分阈值：`|score|` 超过它即视为将杀（与 `search.MATE_BOUND` 一致）。
_MATE_THRESHOLD = C.MAX_SCORE - 100

# warmup 使用的初始局面（红先），覆盖常规分析路径。
_WARMUP_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

_WARMED = False


@dataclasses.dataclass
class AnalysisResult:
    """单层迭代加深完成后的分析快照。

    - `depth`：已完成的搜索层数；
    - `score_stm`：引擎原始分数（走子方视角）；
    - `score_red`：红方视角分数（走子方为黑时取反）；
    - `mate`：将杀步数（ply），`|score|` 未越过将杀阈值时为 `None`；
    - `pv`：主变着法（packed int 的独立 Python 列表，最多 `PV_LIMIT` 步）；
    - `nodes`：本层结束后的累计 leaf 节点数（`ctx.nodes[0]`）；
    - `time_ms`：进入 `analyze` 到本层结束的累计耗时（毫秒）；
    - `side_to_move`：走子方（`constants.RED`/`constants.BLACK`）。
    """

    depth: int
    score_stm: int
    score_red: int
    mate: int | None
    pv: list[int]
    nodes: int
    time_ms: int
    side_to_move: int


def _mate_of(score):
    """由分数换算将杀步数：`MAX_SCORE - abs(score)`；非将杀分返回 `None`。"""
    if score > _MATE_THRESHOLD or score < -_MATE_THRESHOLD:
        return C.MAX_SCORE - abs(score)
    return None


def _copy_pv(stack):
    """把 `stack.pv[0]` 的头段拷贝成独立 Python 列表（遇 0 或满 `PV_LIMIT` 止）。"""
    pv = []
    row = stack.pv[0]
    for i in range(row.shape[0]):
        move = int(row[i])
        if move == 0 or len(pv) >= PV_LIMIT:
            break
        pv.append(move)
    return pv


def _forward_stop(external_stop, stop_all, done):
    """把外部停旗轮询转发到内部总停旗；`done` 置位后退出。"""
    while not done.wait(0.01):
        if external_stop[0] != 0:
            stop_all[0] = 1
            return


def _worker_loop(fen, shared_ctx, stop_all, start_depth, max_depth):
    """Lazy SMP 辅助线程：独立 State/Stack/轻量 Ctx，共享 TT 与停旗。

    不产出结果、不做时限判断；主线程结束置位 `stop_all` 后自行退出。
    辅助线程异常只记录日志，不影响主线程结果。
    """
    from . import search as _search

    try:
        st = load_position(fen)
        prepare(st)
        ctx = _search.new_worker_context(shared_ctx, stop_all)
        stack = _search.new_stack()
        stack.zob32[0] = st.zob[0]
        stack.zob64[0] = st.zob[1]
        depth = start_depth
        while depth <= max_depth and stop_all[0] == 0:
            _search.search_depth(st, ctx, stack, depth)
            depth += 1
    except Exception:  # noqa: BLE001 - 辅助线程失败不影响主线程
        _log.debug("Lazy SMP 辅助线程异常退出", exc_info=True)


def analyze(
    fen,
    *,
    start_depth=C.DEFAULT_START_DEPTH,
    max_depth=C.DEFAULT_MAX_DEPTH,
    time_limit_ms=C.DEFAULT_TIME_LIMIT_MS,
    stop=None,
    threads=None,
):
    """逐层迭代加深分析生成器：每完成一层（且 `depth >= start_depth`）产出一个结果。

    参数：
    - `fen`：局面 FEN（棋盘段必填，其余段可省，默认红先）；
    - `start_depth`：首个产出层；小于 `ROOT_START_DEPTH` 时按 4 处理；
    - `max_depth`：搜索到的最深层，钳位到 `[0, MAX_ANALYSIS_DEPTH]`；
      `start_depth > max_depth` 时无产出（提前返回，不分配搜索对象）；
    - `time_limit_ms`：层边界软时限。**首个产出层完成后才检查**；此后每完成
      一层，除累计耗时外还按"上一层耗时 × 1.5"外推下一层预算，预判超支即
      停止，因此 done 通常不超过 `time_limit_ms` 的 ~1.5 倍（单层实际耗时
      相对上一层暴涨时仍可能超出）。`time_limit_ms <= 0` 时仍会搜到并产出
      `start_depth` 层，然后立即停止；
    - `stop`：可选的 `np.int8[1]` 停旗（与 `ctx.stop` 共享，可被其他线程
      在 nogil 搜索中置位）。**中断契约：一旦置位，直到本生成器结束前
      不得复位**；被中断的层不可信、不会产出（当前实现按 `stop[0]` 判定，
      复用数组存在 TOCTOU 窗口）。搜索中途被置位的层结果直接丢弃；
      层边界置位则正常结束。该数组由调用方持有，`analyze` 只读不改。
    - `threads`：搜索线程数，`None` 表示自动（显式值 > 环境变量
      `ENGINE_THREADS` > `max(1, min(cpu_count-1, 8))`，夹逼 `[1, MAX_THREADS]`）。
      `threads == 1` 时与串行实现完全一致；`> 1` 时启动辅助线程共享 TT
      （Lazy SMP），结果只取主线程，`nodes` 只统计主线程；并行结果存在
      非确定性（同局面分数/PV 可能微变），中断与时限语义不变。

    产出：`AnalysisResult` 迭代器。`Ctx` 为生成器局部变量，提前关闭
    （`break`/`GeneratorExit`）或耗尽时在 `finally` 中释放。
    """
    # 延迟导入：`search → evaluate → analysis` 构成环，顶层导入会循环。
    from . import search as _search

    # 记录外部停旗来源（必须在下方替换 stop 之前）：转发线程只在调用方
    # 真的传入 stop 时才需要启动。
    has_external_stop = stop is not None

    if stop is None:
        stop = np.zeros(1, dtype=np.int8)
    else:
        stop = np.asarray(stop)
        if stop.shape != (1,) or stop.dtype != np.int8:
            raise ValueError(
                "stop 必须是 np.int8[1]，例如 np.zeros(1, dtype=np.int8)"
            )

    start_depth = max(int(start_depth), C.ROOT_START_DEPTH)
    max_depth = max(0, min(int(max_depth), MAX_ANALYSIS_DEPTH))
    time_limit_ms = int(time_limit_ms)
    threads = _resolve_threads(threads)

    if start_depth > max_depth:
        return  # 无产出：不加载局面、不分配 Ctx/Stack

    if threads > 1:
        warmup()  # 幂等；避免多个搜索线程并发触发 JIT 编译

    st = load_position(fen)
    prepare(st)
    # 总停旗：并行时所有搜索线程共享；串行时直接复用外部停旗（现状）。
    stop_all = np.zeros(1, dtype=np.int8) if threads > 1 else None
    search_stop = stop_all if stop_all is not None else stop
    ctx = _search.new_context()._replace(stop=search_stop)
    stack = _search.new_stack()
    stack.zob32[0] = st.zob[0]
    stack.zob64[0] = st.zob[1]

    done = threading.Event()
    helpers = []
    forwarder = None

    t0 = time.perf_counter()
    try:
        # 线程启动在 try 内：启动过程中任何异常（如 start() 失败）都会走
        # finally 置位总停旗并回收已启动的线程，不泄漏无法停止的后台线程。
        if threads > 1:
            if has_external_stop:
                forwarder = threading.Thread(
                    target=_forward_stop,
                    args=(stop, stop_all, done),
                    name="engine-stop-forward",
                    daemon=True,
                )
                forwarder.start()
            for i in range(1, threads):
                first_depth = C.ROOT_START_DEPTH + i
                if first_depth > max_depth:
                    break
                helper = threading.Thread(
                    target=_worker_loop,
                    args=(fen, ctx, stop_all, first_depth, max_depth),
                    name=f"engine-helper-{i}",
                    daemon=True,
                )
                helper.start()
                helpers.append(helper)

        depth = C.ROOT_START_DEPTH
        last_layer_ms = 0
        while depth <= max_depth:
            if search_stop[0] != 0:
                break
            layer_t0 = time.perf_counter()
            score, _ = _search.search_depth(st, ctx, stack, depth)
            if search_stop[0] != 0:
                break  # 中断层结果不可信，丢弃
            last_layer_ms = int((time.perf_counter() - layer_t0) * 1000)
            score = int(score)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            if depth >= start_depth:
                side = int(st.side_to_move[0])
                yield AnalysisResult(
                    depth=depth,
                    score_stm=score,
                    score_red=score if side == C.RED else -score,
                    mate=_mate_of(score),
                    pv=_copy_pv(stack),
                    nodes=int(ctx.nodes[0]),
                    time_ms=elapsed_ms,
                    side_to_move=side,
                )
                if elapsed_ms >= time_limit_ms or depth >= max_depth:
                    break
                # 若上一层耗时 * 1.5 后仍会超出预算，则不再开始下一层
                # （避免单层耗时远超 time_limit，把 done 收敛到约 1.5 倍内）
                if last_layer_ms > 0 and (
                    elapsed_ms + last_layer_ms * 1.5 > time_limit_ms
                ):
                    break
            depth += 1
    finally:
        done.set()
        if stop_all is not None:
            stop_all[0] = 1
        # 只 join 真正启动过的线程：start() 失败的线程 join 会抛 RuntimeError，
        # 掩盖启动时的原始异常。
        for helper in helpers:
            if helper.ident is not None:
                helper.join(timeout=2.0)
        if forwarder is not None and forwarder.ident is not None:
            forwarder.join(timeout=0.5)
        del ctx, stack, st


def warmup():
    """用初始局面触发全链 JIT 编译（幂等）。

    覆盖 `search_depth` 链、`init_root` 的外部默认签名、`clean_tt` 与
    `history_decay`。参数类型与正式调用保持一致（Python int），避免 numba
    对 np 标量重新特化。完成后置 `_WARMED`，重复调用近似零开销。
    """
    global _WARMED
    if _WARMED:
        return
    from . import search as _search

    t0 = time.perf_counter()
    st = load_position(_WARMUP_FEN)
    prepare(st)
    ctx = _search.new_context()
    stack = _search.new_stack()
    stack.zob32[0] = st.zob[0]
    stack.zob64[0] = st.zob[1]
    # 三参默认签名（外部 Python 调用）与内部调用会各自特化，都要触发。
    _search.init_root(st, ctx, stack)
    _search.search_depth(st, ctx, stack, C.ROOT_START_DEPTH)
    _search.clean_tt(ctx)
    _search.history_decay(ctx)
    del ctx, stack, st
    _WARMED = True
    _log.debug("engine warmup 完成：%.2fs", time.perf_counter() - t0)
