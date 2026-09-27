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
- 兵/卒的动态值使用**兵所属方自己**的攻击子数。

推理后端（`engine.backend`）：
- `analyze`/`intent` 通过 `backend.create` 获得统一会话，后端可为 numba（njit）
  或 Cython（AOT，见 `_cycore.pyx`）；`ENGINE_BACKEND=cython|numba` 选择，
  缺省优先 Cython（扩展可用时），不可用时回退 numba。
- 停旗：外部停旗数组（np.int8[1]）在层边界与转发线程同步到 `Session.request_stop()`；
  被中断的层不可信、不产出（中断契约：一旦置位不得复位）。

Task 12（`analyze`/`warmup`）语义要点：
- 逐层迭代加深：从 `constants.ROOT_START_DEPTH`（4）搜到 `max_depth`，
  **只有 `depth >= start_depth` 的完成层才产出**；
- 时限为**层边界软时限 + 时间预算外推**；
- 残局深度补偿（对齐 Java `AICoreHandler.searchEngineFactory`）；
- 并行（Lazy SMP）：`threads > 1` 时启动辅助 worker（共享 TT、深度相位错开）。
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
    """阶段判定（对应 Java `AICoreHandler.getPhase`）。"""
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
    """动态子力价值（对应 Java `AICoreHandler.moveBegin` L132-142）。"""
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
    """搜索前一次性准备：动态子力 → 阶段 → base_score 全量重算。"""
    st.piece_scores[:] = dynamic_piece_scores(st)
    st.phase[0] = np.int8(phase_of(st))
    red, black = full_base_score(st)
    st.base_score[C.RED] = np.int32(red)
    st.base_score[C.BLACK] = np.int32(black)


_log = logging.getLogger(__name__)

MAX_THREADS = 16
_AUTO_THREADS_MAX = 8


def _resolve_threads(threads):
    """解析并行线程数：显式参数 > 环境变量 `ENGINE_THREADS` > 自动。"""
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


MAX_ANALYSIS_DEPTH = 32
PV_LIMIT = 8
_MATE_THRESHOLD = C.MAX_SCORE - 100
_WARMUP_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

_WARMED = False
_WARMUP_LOCK = threading.Lock()


def _reset_warmup_lock_after_fork():
    global _WARMUP_LOCK
    _WARMUP_LOCK = threading.Lock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_warmup_lock_after_fork)


@dataclasses.dataclass
class AnalysisResult:
    """单层迭代加深完成后的分析快照。"""

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


def _forward_stop_sess(external_stop, session, done):
    """把外部停旗轮询转发到会话的 `request_stop`；`done` 置位后退出。"""
    while not done.wait(0.01):
        if external_stop[0] != 0:
            session.request_stop()
            return


def analyze(
    fen,
    *,
    start_depth=C.DEFAULT_START_DEPTH,
    max_depth=C.DEFAULT_MAX_DEPTH,
    time_limit_ms=C.DEFAULT_TIME_LIMIT_MS,
    stop=None,
    threads=None,
    hash_size=None,
):
    """逐层迭代加深分析生成器：每完成一层（且 `depth >= start_depth`）产出一个结果。

    参数与语义见模块 docstring / 原接口说明；搜索由 `engine.backend` 提供的
    会话执行（numba 或 Cython 后端）。
    """
    from . import backend as _backend

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
        return

    st_probe = load_position(fen)
    prepare(st_probe)
    if phase_of(st_probe) == END_GAME:
        max_depth = min(max_depth + 1, MAX_ANALYSIS_DEPTH)
    del st_probe

    session = _backend.create(fen, stop=stop, hash_size=hash_size)
    done = threading.Event()
    helpers = []
    forwarder = None

    t0 = time.perf_counter()
    try:
        if threads > 1:
            if has_external_stop:
                forwarder = threading.Thread(
                    target=_forward_stop_sess,
                    args=(stop, session, done),
                    name="engine-stop-forward",
                    daemon=True,
                )
                try:
                    forwarder.start()
                except Exception:  # noqa: BLE001 - 降级为无转发
                    _log.debug("外部停旗转发线程启动失败，降级为无转发", exc_info=True)
                    forwarder = None
            for i in range(1, threads):
                first_depth = C.ROOT_START_DEPTH + i
                if first_depth > max_depth:
                    break
                worker = session.spawn_worker(first_depth)
                helper = threading.Thread(
                    target=worker.run,
                    args=(max_depth,),
                    name=f"engine-helper-{i}",
                    daemon=True,
                )
                try:
                    helper.start()
                except Exception:  # noqa: BLE001 - 降级为更少线程
                    _log.debug(
                        "Lazy SMP 辅助线程 %d 启动失败，降级为更少线程",
                        i,
                        exc_info=True,
                    )
                    worker.close()
                    continue
                helpers.append((helper, worker))

        depth = C.ROOT_START_DEPTH
        last_layer_ms = 0
        while depth <= max_depth:
            if has_external_stop and stop[0] != 0:
                session.request_stop()
            if session.is_stopped() != 0:
                break
            layer_t0 = time.perf_counter()
            score, mate = session.search_layer(depth)
            if session.is_stopped() != 0:
                break  # 中断层结果不可信，丢弃
            last_layer_ms = int((time.perf_counter() - layer_t0) * 1000)
            score = int(score)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            if depth >= start_depth:
                side = session.side()
                yield AnalysisResult(
                    depth=depth,
                    score_stm=score,
                    score_red=score if side == C.RED else -score,
                    mate=int(mate) if int(mate) != 0 else None,
                    pv=session.pv(PV_LIMIT),
                    nodes=session.nodes(),
                    time_ms=elapsed_ms,
                    side_to_move=side,
                )
                if elapsed_ms >= time_limit_ms or depth >= max_depth:
                    break
                if last_layer_ms > 0 and (
                    elapsed_ms + last_layer_ms * 1.5 > time_limit_ms
                ):
                    break
            depth += 1
    finally:
        done.set()
        session.request_stop()
        deadline = time.monotonic() + 5.0
        for helper, worker in helpers:
            if helper.ident is not None:
                helper.join(timeout=max(0.05, deadline - time.monotonic()))
            worker.close()
        if forwarder is not None and forwarder.ident is not None:
            forwarder.join(timeout=0.5)
        session.close()


def warmup():
    """触发后端初始化（幂等、并发安全）。

    - numba 后端：用初始局面触发全链 JIT 编译；
    - Cython 后端：初始化只读表（AOT，无 JIT）。
    """
    global _WARMED
    if _WARMED:
        return
    from . import backend as _backend

    with _WARMUP_LOCK:
        if _WARMED:
            return
        t0 = time.perf_counter()
        if _backend.resolve_backend() == "cython":
            _backend._ensure_cython_tables()
        else:
            from . import search as _search

            st = load_position(_WARMUP_FEN)
            prepare(st)
            ctx = _search.new_context()
            stack = _search.new_stack()
            stack.zob32[0] = st.zob[0]
            stack.zob64[0] = st.zob[1]
            _search.init_root(st, ctx, stack)
            _search.search_depth(st, ctx, stack, C.ROOT_START_DEPTH)
            _search.clean_tt(ctx)
            _search.history_decay(ctx)
            del ctx, stack, st
        _WARMED = True
        _log.debug("engine warmup 完成：%.2fs", time.perf_counter() - t0)
