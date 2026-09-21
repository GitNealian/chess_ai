"""置换表、杀手着法与历史启发表（Task 9）；静态搜索（Task 10）。

Java 参考：
- `TranspositionTable.java`：双槽置换表（STEP 深度替换槽 + STRAIGHT 覆盖槽）、
  `cleanTranZobrist`（L67-78）、`setRootTranZobrist`（L177-185）、
  `setTranZobristOverride`（L264-283）、`setTranZobristOverrideByStep`（L287-315）、
  `setTranZobrist`（L319-330）、`getTranZobrist`（L335-360）、
  `getTranZobristByHashItem`（L361-391）；
- `CHistoryHeuritic.java`（L11-35）与 `AICoreHandler.moveEnd` L143-147 的 `/512`；
- Task 10：`SearchEngine.java` L163-239（`quiescSearch`）、L240-260（`isLongChk`）、
  L267-273（`isDraw`）、L115-118（`fineEvaluate`）、L123-125（`roughEvaluate`）、
  `ChessQuiescMove.java` L44-64（`savePlayChess` 的 good/general 分类）、
  `MoveNodesSort.java` L44-80（`quiescNext` 消费顺序）与 L215-228
  （`getSortAfterBestMove` 选择排序）、`NodeLink.java`（链结构）。

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

Task 10 的静态搜索语义（与 Java 一致的关键点）：
- 搜索栈 `Stack` 第 ply 层保存的是**走到该局面后**的 zobrist（对应 Java
  NodeLink 在 `moveOperate` 之后取 `transTable.boardZobrist*`），`is_eat`
  是该步是否吃子，`chk` 由搜索层设置（该局面是否被将）；
- `is_checked` 参数表示**当前 ply 层局面是否被将**（上一步走完后的状态）；
  递归时传 `in_check(st, 1-play)`，即对手（子节点走子方）是否被将，
  对应 Java L219 的 `chessQuiescMove.checked(1-play)`；
- 长将回溯范围是 `ply-1 .. 1`：Java 从 `lastLink.getLastLink()` 开始，
  遇到根节点（`getMoveNode()==null`）终止，根节点不参与比较；
- `is_draw` 只看双方攻击子（兵卒车马炮）数量是否为 0，**不检查是否吃子**
  （任务书中"上一步吃子"为误述，此处以 Java L267-273 为准）。即使当前
  未被将也先判和（Java 顺序：王被吃 → 长将 → 和棋 → 深度保险丝）；
- 非被将时只消费 good 吃子（`destScore >= 150`）并结束；被将时 good 之后
  继续消费 general（低价值吃子 + 全部非吃子），对应 `quiescNext` L44-80；
- `ply >= 64` 返回 `fine_evaluate`，递归深度有界（栈长 68）。
"""

import collections

import numpy as np
from numba import njit

from . import constants as C
from . import eval_tables as _eval_tables
from . import evaluate as _evaluate
from . import movegen as _movegen
from . import position as _position

__all__ = [
    "FAIL",
    "HASH_ALPHA",
    "HASH_BETA",
    "HASH_PV",
    "MATE_BOUND",
    "MAX_PLY",
    "QUIESC_GOOD_SCORE",
    "SLOT_STEP",
    "SLOT_STRAIGHT",
    "STACK_SIZE",
    "Ctx",
    "N",
    "Stack",
    "clean_tt",
    "fine_evaluate",
    "gen_quiesc_moves",
    "get_tt",
    "history_bonus",
    "history_decay",
    "history_score",
    "is_draw",
    "is_long_check",
    "new_context",
    "new_stack",
    "quiesc_search",
    "rough_evaluate",
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


# --------------------------------------------------------------------------
# Task 10：搜索栈与静态搜索
# --------------------------------------------------------------------------

# 搜索栈层数：ply 上限 64，递归中最深写 ply+1 = 65。
STACK_SIZE = 68

# `ChessQuiescMove.savePlayChess` 的 goodMoveList 门槛：目标"子力 + 位置"分。
QUIESC_GOOD_SCORE = 150

# 静态搜索深度保险丝（Java L183 `lastLink.depth >= 64`）。
MAX_PLY = 64

Stack = collections.namedtuple("Stack", "zob32 zob64 is_eat chk pv")
Stack.__doc__ = """静态搜索栈（对应 Java NodeLink 链 + Task 11 的三角 PV 表）。

- `zob32`/`zob64`：int64[68]，第 ply 层局面的 zobrist（走到该局面**之后**）；
- `is_eat`：int8[68]，走到该局面的着法是否吃子（长将回溯的截断条件）；
- `chk`：int8[68]，该局面是否被将（由搜索层设置）；
- `pv`：int32[68][68] 三角 PV 表（Task 11 使用）。

ply 0 为根节点（Java 根 NodeLink 的 depth=0，moveNode 为空、不参与长将回溯）。
"""


def new_stack():
    """新建全零搜索栈。"""
    return Stack(
        zob32=np.zeros(STACK_SIZE, dtype=np.int64),
        zob64=np.zeros(STACK_SIZE, dtype=np.int64),
        is_eat=np.zeros(STACK_SIZE, dtype=np.int8),
        chk=np.zeros(STACK_SIZE, dtype=np.int8),
        pv=np.zeros((STACK_SIZE, STACK_SIZE), dtype=np.int32),
    )


@njit(cache=True)
def fine_evaluate(st, play, ctx):
    """精确评估（`fineEvaluate` L115-118）：计节点数后按阶段分派 `evaluate`。"""
    ctx.nodes[0] += 1
    return _evaluate.evaluate(st, play)


@njit(cache=True)
def rough_evaluate(st, play):
    """粗评估（`roughEvaluate` L123-125）：`base_score[play] - base_score[1-play]`。"""
    return st.base_score[play] - st.base_score[1 - play]


@njit(cache=True)
def is_long_check(stack, ply):
    """长将检测（`isLongChk` L240-260）。

    仅当第 ply 层被将时检测：从 `ply-1` 向根回溯到第 1 层（根节点不参与，
    对应 Java `getMoveNode()==null` 终止），先比较 zobrist（相等即长将），
    再判断该层着法是否吃子（吃子截断）。
    """
    if stack.chk[ply] == 0:
        return False
    t = ply - 1
    while t > 0:
        if stack.zob32[t] == stack.zob32[ply] and stack.zob64[t] == stack.zob64[ply]:
            return True
        if stack.is_eat[t] != 0:
            return False
        t -= 1
    return False


@njit(cache=True)
def is_draw(st, stack, ply):
    """和棋判定（`isDraw` L267-273）：双方攻击子（兵卒车马炮）数都为 0。

    `st.attack_def[play, 0]` 即 Java `getAttackChessesNum`（`indexOfAttackAndDefense`
    中兵/卒与车马炮同为攻击子，士/象/将为防御子）；只依赖局面，不检查是否吃子。
    `stack`/`ply` 为调用一致性保留（Java 签名带 `lastLink` 但未使用其内容）。
    """
    return st.attack_def[C.RED, 0] == 0 and st.attack_def[C.BLACK, 0] == 0


@njit(cache=True)
def _select_best(buf, score, index, count):
    """从 `index..count-1` 选出最大 score 与 `index` 原地交换（严格大于）。

    复刻 `MoveNodesSort.getSortAfterBestMove` L215-228：等分保留靠前者。
    """
    best = index
    for i in range(index + 1, count):
        if score[i] > score[best]:
            best = i
    if best != index:
        tm = buf[index]
        buf[index] = buf[best]
        buf[best] = tm
        ts = score[index]
        score[index] = score[best]
        score[best] = ts


@njit(cache=True)
def gen_quiesc_moves(
    st, ctx, play, is_checked, good_buf, good_score, general_buf, general_score
):
    """生成静态搜索的 good/general 着法列表，返回 `(good_n, general_n)`。

    复刻 `ChessQuiescMove.savePlayChess` L44-64 与 `MoveNodesSort.quiescNext`
    L44-80：

    - good：目标格"子力 + 位置"分 `>= 150` 的吃子，排序分 =
      `destScore - srcScore`（都用静态子力表 `EvaluateCompute.chessBaseScore`）；
    - general：其余吃子，排序分 = `history[PIECE_KINDS[src]][dest]`；
    - 被将时（`is_checked`）：在 general 末尾追加全部非吃子（
      `genNopMoveList` 语义），排序分同样取历史分。
    """
    tmp = np.empty(_movegen.MAX_MOVES, dtype=np.int32)
    n = _movegen.gen_captures_into(st, play, tmp)
    good_n = 0
    general_n = 0
    for i in range(n):
        m = tmp[i]
        src = C.move_src(m)
        dest = C.move_dest(m)
        dest_chess = st.board[dest]
        dest_score = _eval_tables.BASE_SCORES[dest_chess] + _position.attach_score(
            st, C.PIECE_ROLES[dest_chess], dest
        )
        src_chess = st.board[src]
        if dest_score >= QUIESC_GOOD_SCORE:
            if good_n >= good_buf.shape[0]:
                continue
            src_score = _eval_tables.BASE_SCORES[src_chess] + _position.attach_score(
                st, C.PIECE_ROLES[src_chess], src
            )
            good_buf[good_n] = m
            good_score[good_n] = dest_score - src_score
            good_n += 1
        else:
            if general_n >= general_buf.shape[0]:
                continue
            general_buf[general_n] = m
            general_score[general_n] = ctx.history[C.PIECE_KINDS[src_chess], dest]
            general_n += 1
    if is_checked:
        n = _movegen.gen_moves_into(st, play, tmp, False)
        for i in range(n):
            if general_n >= general_buf.shape[0]:
                break
            m = tmp[i]
            dest = C.move_dest(m)
            if st.board[dest] != 0:
                continue
            src = C.move_src(m)
            general_buf[general_n] = m
            general_score[general_n] = ctx.history[C.PIECE_KINDS[st.board[src]], dest]
            general_n += 1
    return good_n, general_n


@njit(cache=True)
def quiesc_search(st, ctx, stack, alpha, beta, ply, play, is_checked):
    """静态搜索（`quiescSearch` L163-239），返回 `play` 视角分数。

    按 Java 顺序：王被吃（`-(MAX_SCORE-ply)`）→ 记录 `chk` → 长将（8888）
    → 和棋（0）→ 深度保险丝（`fine_evaluate`）→ 非被将 stand-pat 并尝试
    beta 截断 → 依次搜索 good/general 着法（自将被过滤，beta 截断），
    非被将只搜 good；无合法着法（且非被将无 stand-pat）返回 `-(MAX_SCORE-ply)`。

    递归时子节点 `is_checked` 传 `in_check(st, 1-play)`（对手是否被将），
    与 Java L219 一致。
    """
    if st.all_chess[C.PIECE_STARTS[play]] == C.NOTHING:
        return -(C.MAX_SCORE - ply)
    if is_checked:
        stack.chk[ply] = 1
    else:
        stack.chk[ply] = 0
    if is_long_check(stack, ply):
        return C.LONG_CHECK_SCORE
    if is_draw(st, stack, ply):
        return C.DRAW_SCORE
    if ply >= MAX_PLY:
        return fine_evaluate(st, play, ctx)

    best = -C.MAX_SCORE - 2
    is_move = False
    if not is_checked:
        # Java：非被将时 isMove 先置 true，即使无着法也返回 stand-pat
        is_move = True
        v = fine_evaluate(st, play, ctx)
        if v > best:
            if v >= beta:
                return v
            best = v
            if v > alpha:
                alpha = v

    good_buf = np.empty(_movegen.MAX_MOVES, dtype=np.int32)
    good_score = np.empty(_movegen.MAX_MOVES, dtype=np.int32)
    general_buf = np.empty(_movegen.MAX_MOVES, dtype=np.int32)
    general_score = np.empty(_movegen.MAX_MOVES, dtype=np.int32)
    good_n, general_n = gen_quiesc_moves(
        st, ctx, play, is_checked, good_buf, good_score, general_buf, general_score
    )

    i = 0
    while i < good_n:
        _select_best(good_buf, good_score, i, good_n)
        m = good_buf[i]
        i += 1
        undo = _position.make_move(st, m)
        if _movegen.in_check(st, play):
            _position.unmake_move(st, m, undo)
            continue
        stack.zob32[ply + 1] = st.zob[0]
        stack.zob64[ply + 1] = st.zob[1]
        stack.is_eat[ply + 1] = 1
        v = -quiesc_search(
            st,
            ctx,
            stack,
            -beta,
            -alpha,
            ply + 1,
            1 - play,
            _movegen.in_check(st, 1 - play),
        )
        _position.unmake_move(st, m, undo)
        is_move = True
        if v > best:
            best = v
            if v > alpha:
                alpha = v
            if v >= beta:
                return best

    if is_checked:
        i = 0
        while i < general_n:
            _select_best(general_buf, general_score, i, general_n)
            m = general_buf[i]
            i += 1
            is_eat = st.board[C.move_dest(m)] != 0
            undo = _position.make_move(st, m)
            if _movegen.in_check(st, play):
                _position.unmake_move(st, m, undo)
                continue
            stack.zob32[ply + 1] = st.zob[0]
            stack.zob64[ply + 1] = st.zob[1]
            if is_eat:
                stack.is_eat[ply + 1] = 1
            else:
                stack.is_eat[ply + 1] = 0
            v = -quiesc_search(
                st,
                ctx,
                stack,
                -beta,
                -alpha,
                ply + 1,
                1 - play,
                _movegen.in_check(st, 1 - play),
            )
            _position.unmake_move(st, m, undo)
            is_move = True
            if v > best:
                best = v
                if v > alpha:
                    alpha = v
                if v >= beta:
                    return best

    if is_move:
        return best
    return -(C.MAX_SCORE - ply)
