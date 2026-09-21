"""置换表、杀手着法与历史启发表（Task 9）。

Java 参考：
- `TranspositionTable.java`：双槽置换表（STEP 深度替换槽 + STRAIGHT 覆盖槽）、
  `cleanTranZobrist`（L67-78）、`setRootTranZobrist`（L177-185）、
  `setTranZobristOverride`（L264-283）、`setTranZobristOverrideByStep`（L287-315）、
  `setTranZobrist`（L319-330）、`getTranZobrist`（L335-360）、
  `getTranZobristByHashItem`（L361-391）；
- `CHistoryHeuritic.java`（L11-35）与 `AICoreHandler.moveEnd` L143-147 的 `/512`。

约定与差异：
- Java 表是 `HashItem[2][TRANZOBRISTSIZE][2]`（第 3 维 0=`OVERRIDESTEP`、
  1=`OVERRIDESTRAIGHT`）；本迁移按字段拆成 6 个常量数组，最后一维是槽号
  `slot = zob32 & (N - 1)`，槽序相反：0=STRAIGHT、1=STEP；
- **修正 Java 缺陷**：`setHashSize(0x7FFFF)` 使数组长度 524287，而槽号
  `zob32 & 0x7FFFF` 可达 524287 → 越界；此处 `N = 1 << 19`，槽号合法区间
  0..N-1，正常路径行为与 Java 一致；
- 读取时按任务设计额外校验 `tt_exists`：`clean_tt` 置 STEP 槽
  `tt_exists=False` 后该槽不再命中（Java 的读取只看 checkSum，本迁移让
  `isExists` 真正参与读取，语义更自洽）；
- `set_tt` 中"STEP 槽旧条目更深则放弃"仅指 STEP 槽不更新，STRAIGHT 槽
  仍按 Java 写入新条目（`setTranZobrist` L319-330 无条件调用覆盖写入）；
- `set_root_tt` 对应 `setRootTranZobrist`（L177-185）：只写 **STEP** 槽的
  key+move（`OVERRIDESTEP=0`；`setRootTranZobrist2` 才写 STRAIGHT 槽），
  不改 depth/entry_type/value；槽从未分配时按 Java 新建 `HashItem` 语义把
  `exists` 置 True；
- `history_decay` 复刻 Java int 除法**向零截断**（numpy `//` 是向下取整，
  负数行为不同，故显式处理）。

`Ctx` 中 `stop`/`nodes` 是搜索层（Task 10）的共享标志与节点计数。
"""

import collections

import numpy as np
from numba import njit

from . import constants as C

__all__ = [
    "FAIL",
    "HASH_ALPHA",
    "HASH_BETA",
    "HASH_PV",
    "MATE_BOUND",
    "SLOT_STEP",
    "SLOT_STRAIGHT",
    "Ctx",
    "N",
    "clean_tt",
    "get_tt",
    "history_bonus",
    "history_decay",
    "history_score",
    "new_context",
    "set_root_tt",
    "set_tt",
    "update_killer",
]

# 槽数与槽号掩码（Java TRANZOBRISTSIZE 的 2 的幂版本，见模块 docstring）。
N = 1 << 19
_SLOT_MASK = N - 1

# 第 3 维槽类型：STRAIGHT 始终覆盖、STEP 按深度替换。
SLOT_STRAIGHT = 0
SLOT_STEP = 1

# HashItem.entry_type：下界 / 上界 / 精确值。
HASH_BETA = 1
HASH_ALPHA = 2
HASH_PV = 3

# getTranZobristByHashItem 的失败哨兵（Integer.MIN_VALUE + 1）。
FAIL = int(np.iinfo(np.int32).min) + 1

# Java `mateNode = maxScore - 100`：超过该绝对值的分数视为将杀分，按深度差调整。
MATE_BOUND = C.MAX_SCORE - 100

Ctx = collections.namedtuple(
    "Ctx",
    "tt_key tt_type tt_value tt_depth tt_move tt_exists killer history stop nodes",
)
Ctx.__doc__ = """搜索上下文。

- `tt_key/tt_type/tt_value/tt_depth/tt_move/tt_exists`：形状 [play][kind][slot]，
  kind 取 `SLOT_STRAIGHT`/`SLOT_STEP`；
- `killer`：int32[64][2]（按剩余深度索引的双槽）；
- `history`：int32[8][256]（基础类型 × 目标格）；
- `stop`：int8[1] 停止标志；`nodes`：int64[1] 节点计数。
"""


def new_context(hash_size=N):
    """新建空搜索上下文；`hash_size` 须为 2 的幂（槽号 = `zob32 & (hash_size-1)`）。"""
    if hash_size <= 0 or hash_size & (hash_size - 1):
        raise ValueError("hash_size 必须是 2 的幂")
    return Ctx(
        tt_key=np.zeros((2, 2, hash_size), dtype=np.int64),
        tt_type=np.zeros((2, 2, hash_size), dtype=np.int8),
        tt_value=np.zeros((2, 2, hash_size), dtype=np.int32),
        tt_depth=np.zeros((2, 2, hash_size), dtype=np.int8),
        tt_move=np.zeros((2, 2, hash_size), dtype=np.int32),
        tt_exists=np.zeros((2, 2, hash_size), dtype=np.bool_),
        killer=np.zeros((64, 2), dtype=np.int32),
        history=np.zeros((8, 256), dtype=np.int32),
        stop=np.zeros(1, dtype=np.int8),
        nodes=np.zeros(1, dtype=np.int64),
    )


@njit(cache=True)
def _get_by_hash_item(ctx, play, kind, slot, depth, alpha, beta):
    """对应 `getTranZobristByHashItem`（L361-391）。

    注意 mate 处理是 else-if 链：只有非 mate 分数才检查 `entry_depth < depth`；
    mate 分数按 `depth - entry_depth` 调整后不再做深度过滤。
    """
    value = np.int64(ctx.tt_value[play, kind, slot])
    entry_depth = np.int64(ctx.tt_depth[play, kind, slot])
    if value > MATE_BOUND:
        value -= depth - entry_depth
    elif value < -MATE_BOUND:
        value += depth - entry_depth
    elif entry_depth < depth:
        return FAIL
    # Java switch：PV 直接返回；Beta（下界）要 value >= beta；Alpha（上界）要 value <= alpha
    entry_type = ctx.tt_type[play, kind, slot]
    if entry_type == HASH_PV:
        return value
    if entry_type == HASH_BETA and value >= beta:
        return value
    if entry_type == HASH_ALPHA and value <= alpha:
        return value
    return FAIL


@njit(cache=True)
def get_tt(ctx, play, zob32, zob64, depth, alpha, beta):
    """探测置换表，返回 `(hit, value, move)`。

    复刻 `getTranZobrist` L335-360：先 STEP 槽后 STRAIGHT 槽（均要求
    `tt_exists` 且 `tt_key == zob64`）。第一个通过 `_get_by_hash_item` 的槽
    直接命中；否则按 Java 逻辑输出失败条目的 `move`（STRAIGHT 优先覆盖）与
    `value`（仅当 `step 不存在或 step.depth < straight.depth` 时被 STRAIGHT
    覆盖）。`move == 0` 表示无着法。
    """
    slot = zob32 & (ctx.tt_key.shape[2] - 1)
    value = 0
    move = 0

    step_exists = (
        ctx.tt_exists[play, SLOT_STEP, slot]
        and ctx.tt_key[play, SLOT_STEP, slot] == zob64
    )
    if step_exists:
        step_value = _get_by_hash_item(ctx, play, SLOT_STEP, slot, depth, alpha, beta)
        if step_value != FAIL:
            return True, step_value, ctx.tt_move[play, SLOT_STEP, slot]
        move = ctx.tt_move[play, SLOT_STEP, slot]
        value = ctx.tt_value[play, SLOT_STEP, slot]

    straight_exists = (
        ctx.tt_exists[play, SLOT_STRAIGHT, slot]
        and ctx.tt_key[play, SLOT_STRAIGHT, slot] == zob64
    )
    if straight_exists:
        straight_value = _get_by_hash_item(
            ctx, play, SLOT_STRAIGHT, slot, depth, alpha, beta
        )
        if straight_value != FAIL:
            return True, straight_value, ctx.tt_move[play, SLOT_STRAIGHT, slot]
        move = ctx.tt_move[play, SLOT_STRAIGHT, slot]
        if not step_exists or ctx.tt_depth[
            play, SLOT_STEP, slot
        ] < ctx.tt_depth[play, SLOT_STRAIGHT, slot]:
            value = ctx.tt_value[play, SLOT_STRAIGHT, slot]

    return False, value, move


@njit(cache=True)
def _copy_slot(ctx, play, src_kind, dst_kind, slot):
    """整体复制条目（Java 中把 STEP 旧条目引用赋给 STRAIGHT 槽）。

    被 clean 失效的 STEP 条目踢到 STRAIGHT 后置 `exists=True`：Java 读取
    只看 checkSum、不看 isExists，故 clean 过的旧条目依然可命中；本迁移的
    `get_tt` 额外校验 `tt_exists`，在此保持同样的可观察行为（clean 只让
    STEP 槽失效）。
    """
    ctx.tt_key[play, dst_kind, slot] = ctx.tt_key[play, src_kind, slot]
    ctx.tt_type[play, dst_kind, slot] = ctx.tt_type[play, src_kind, slot]
    ctx.tt_value[play, dst_kind, slot] = ctx.tt_value[play, src_kind, slot]
    ctx.tt_depth[play, dst_kind, slot] = ctx.tt_depth[play, src_kind, slot]
    ctx.tt_move[play, dst_kind, slot] = ctx.tt_move[play, src_kind, slot]
    ctx.tt_exists[play, dst_kind, slot] = True


@njit(cache=True)
def _write_straight(ctx, play, slot, zob64, entry_type, value, depth, move):
    """覆盖写 STRAIGHT 槽（`setTranZobristOverride` else 分支）。

    Java 复用已有 HashItem：`moveNode == null`（move=0）时保留旧 moveNode。
    """
    ctx.tt_key[play, SLOT_STRAIGHT, slot] = zob64
    ctx.tt_type[play, SLOT_STRAIGHT, slot] = np.int8(entry_type)
    ctx.tt_value[play, SLOT_STRAIGHT, slot] = np.int32(value)
    ctx.tt_depth[play, SLOT_STRAIGHT, slot] = np.int8(depth)
    if move != 0:
        ctx.tt_move[play, SLOT_STRAIGHT, slot] = np.int32(move)
    ctx.tt_exists[play, SLOT_STRAIGHT, slot] = True


@njit(cache=True)
def _write_step(ctx, play, slot, zob64, entry_type, value, depth, move):
    """把新条目写入 STEP 槽（Java 中总是新建 HashItem，move 默认空）。"""
    ctx.tt_key[play, SLOT_STEP, slot] = zob64
    ctx.tt_type[play, SLOT_STEP, slot] = np.int8(entry_type)
    ctx.tt_value[play, SLOT_STEP, slot] = np.int32(value)
    ctx.tt_depth[play, SLOT_STEP, slot] = np.int8(depth)
    if move != 0:
        ctx.tt_move[play, SLOT_STEP, slot] = np.int32(move)
    else:
        ctx.tt_move[play, SLOT_STEP, slot] = np.int32(0)
    ctx.tt_exists[play, SLOT_STEP, slot] = True


@njit(cache=True)
def _step_allocated(ctx, play, slot):
    """STEP 槽是否分配过条目（对应 Java `HashItem == null` 的反面）。"""
    return (
        ctx.tt_exists[play, SLOT_STEP, slot]
        or ctx.tt_type[play, SLOT_STEP, slot] != 0
        or ctx.tt_key[play, SLOT_STEP, slot] != 0
        or ctx.tt_move[play, SLOT_STEP, slot] != 0
    )


@njit(cache=True)
def set_tt(ctx, play, zob32, zob64, entry_type, value, depth, move):
    """写入置换表（`setTranZobrist` L319-330 + 两个 Override 辅助）。

    - 8000..9000 / -9000..-8000（长将等）不入表；
    - STEP 槽：已分配且 `tt_exists` 且旧 depth > 新 depth → 只放弃 STEP 更新，
      STRAIGHT 槽仍写新条目；否则旧条目踢出到 STRAIGHT，新条目写 STEP；
    - STEP 未分配时 STEP 与 STRAIGHT 都写新条目。
    """
    if (value >= 8000 and value <= 9000) or (value >= -9000 and value <= -8000):
        return
    slot = zob32 & (ctx.tt_key.shape[2] - 1)
    step_exists = ctx.tt_exists[play, SLOT_STEP, slot]
    step_depth = np.int64(ctx.tt_depth[play, SLOT_STEP, slot])
    if _step_allocated(ctx, play, slot):
        if step_exists and step_depth > depth:
            # 放弃 STEP 更新；STRAIGHT 仍写入新条目（Java 无条件调用覆盖写入）
            _write_straight(ctx, play, slot, zob64, entry_type, value, depth, move)
            return
        # 旧条目踢出到 STRAIGHT 槽，STEP 换新条目
        _copy_slot(ctx, play, SLOT_STEP, SLOT_STRAIGHT, slot)
    else:
        # 未分配：两个槽都写新条目（Java 两个新建 HashItem）
        _write_straight(ctx, play, slot, zob64, entry_type, value, depth, move)
    _write_step(ctx, play, slot, zob64, entry_type, value, depth, move)


@njit(cache=True)
def set_root_tt(ctx, play, zob32, zob64, move):
    """IID 根槽写入（`setRootTranZobrist` L177-185）。

    只覆盖 STEP 槽的 checkSum 与 moveNode，不改 depth/entry_type/value；
    槽从未分配时按新建 `HashItem` 默认 `isExists=true` 置位。
    """
    slot = zob32 & (ctx.tt_key.shape[2] - 1)
    if not _step_allocated(ctx, play, slot):
        ctx.tt_exists[play, SLOT_STEP, slot] = True
    ctx.tt_key[play, SLOT_STEP, slot] = zob64
    ctx.tt_move[play, SLOT_STEP, slot] = np.int32(move)


@njit(cache=True)
def clean_tt(ctx):
    """清理 STEP 槽（`cleanTranZobrist` L67-78）：只把 exists 置 False。"""
    for play in range(2):
        for slot in range(ctx.tt_exists.shape[2]):
            ctx.tt_exists[play, SLOT_STEP, slot] = False


@njit(cache=True)
def update_killer(ctx, depth, move):
    """killer 双槽轮转：`killer[depth][1] = killer[depth][0]; [0] = move`。"""
    ctx.killer[depth, 1] = ctx.killer[depth, 0]
    ctx.killer[depth, 0] = np.int32(move)


@njit(cache=True)
def history_bonus(ctx, piece_index, dest, depth):
    """历史加分（`setCHistoryGOOD`）：`history[PIECE_KINDS[piece_index]][dest] += 2 << depth`。

    Java 的 `2 << depth` 是 32 位 int 移位（位移量取低 5 位、结果按 32 位
    环绕）；搜索实际 depth 远小于 31，此处显式按 Java int 语义计算，保证
    极端 depth 下与 Java 一致（`2<<30 == INT_MIN`、`2<<31 == 0`）。加法与
    Java int 一样按 32 位环绕。
    """
    shift = depth & 31
    delta = (np.int64(2) << shift) & 0xFFFFFFFF
    if delta >= 0x80000000:
        delta -= 0x100000000
    ctx.history[C.PIECE_KINDS[piece_index], dest] += np.int32(delta)


@njit(cache=True)
def history_decay(ctx):
    """历史衰减（`AICoreHandler.moveEnd`）：逐元素 `/512`，**向零截断**。"""
    for i in range(ctx.history.shape[0]):
        for j in range(ctx.history.shape[1]):
            v = np.int64(ctx.history[i, j])
            if v >= 0:
                ctx.history[i, j] = np.int32(v // 512)
            else:
                ctx.history[i, j] = np.int32(-((-v) // 512))


@njit(cache=True)
def history_score(ctx, piece_index, dest):
    """读取历史分（`getCHistory`）：`history[PIECE_KINDS[piece_index]][dest]`。"""
    return ctx.history[C.PIECE_KINDS[piece_index], dest]
