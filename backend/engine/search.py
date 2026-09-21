"""置换表、杀手着法与历史启发表（Task 9）；静态搜索（Task 10）；
主搜索（Task 11：根 PVS + negaScout + 迭代加深）。

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
  （`getSortAfterBestMove` 选择排序）、`NodeLink.java`（链结构）；
- Task 11：`PrincipalVariation.java` L40-94（`searchMove`）、L95-148
  （`rootNegaScout`）、L154-337（`negaScout`）、`SearchEngine.java` L102-113
  （`RAdapt`）、L274-286（`isDanger`）、`MoveNodesSort.java` L81-150
  （`next` 的阶段顺序）、`ChessMovePlay.java` L44-83
  （`savePlayChess` 的 MVV-LVA/历史排序与 `isOppProtect`）。

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
- **修正 Java 继承缺陷**：mate 分数（`|value| >= MATE_BOUND`）不入置换表。
  Java 的 mate 分数按 `±(maxScore - ply)` 编码（量纲是 ply），而 TT 读取按
  `value -= (depth - entry_depth)` 调整（量纲是剩余深度），量纲不一致会在
  同一 ctx 迭代加深时导致杀步虚报/漂移（如 3 步杀被报成 4~5 步）。不入表后
  每层重新搜索杀棋，以速度换 mate 步数准确；
- `set_root_tt` 对应 `setRootTranZobrist`（L177-185）：只写 **STEP** 槽的
  key+move（`OVERRIDESTEP=0`；`setRootTranZobrist2` 才写 STRAIGHT 槽），
  不改 depth/entry_type/value；槽从未分配时按 Java 新建 `HashItem` 语义把
  `exists` 置 True；
- `history_decay` 复刻 Java int 除法**向零截断**（numpy `//` 是向下取整，
  负数行为不同，故显式处理）。

`Ctx` 中 `stop`/`nodes` 是搜索层（Task 10）的共享标志与节点计数；
`root_moves/root_scores/root_count/root_inited` 是 Task 11 的根着法缓冲。

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

Task 11 的主搜索语义（与 Java 一致的关键点）：
- 迭代加深从 depth=4 开始（`ROOT_START_DEPTH`），每轮用全窗口调用
  `root_nega_scout`；本轮 `getSortAfterBestMove` 的原地交换已让
  `root_moves` 按分数降序，故下一轮天然 PV-first；
- 根节点**无 beta 截断**；停旗在根每着后检查（Java L135-137），无着法完成
  时返回 `-(MAX_SCORE - lastLink.depth)`；
- `MoveNodesSort.next()` 的阶段顺序：TT 着法 1 → TT 着法 2（Java 中
  `getTranZobrist` 只填第 0 个，第 1 个恒空）→ killer1 → killer2 →
  good 吃子（`destScore >= srcScore`，`srcScore` 在目标格受对方保护时为
  子力+位置分、否则 -500）→ general（其余吃子与全部非吃子，排序分 =
  历史分 + 受保护 256 加成）；已返回的 TT/killer 着法从后续列表中去重；
- 空着裁剪递归的是"同一局面、走子方不变"的 nullLink（`is_null=1`），
  回溯与和棋判定据此跳过；`is_long_check` 遇空着层终止（对应 Java
  `getMoveNode()==null`）；
- Futility 是"跳过着法"（`!is_checked && !is_pv && depth<6 && !is_danger(play)
  && moves_searched >= moves_count && FutilityScore[depth][k] + rough < alpha`）；
- LMR：`!is_checked && depth>=3 && moves_searched>=moves_count` 时按
  `moves_searched` 与 `is_danger(1-play)` 计算 kk ∈ {2,3,4}，先
  `depth-kk` 零窗口，超过 thisAlpha 再 `depth-1` 零窗口、再全窗口重搜；
- 收尾：best move 写入 `stack.pv[ply]`（首着 + 复制子层），
  `entry_type != HASH_ALPHA` 时才写 TT 着法与历史加分；
- 无着法返回 `-(MAX_SCORE - ply)`。

与 Java 的有意差异：
- `nega_scout` 入口检查 `ctx.stop`（Java 只在根循环检查），置位立即返回
  当前下界 `ply - MAX_SCORE`，支持外部快速中断；
- `nega_scout` 在 `ply >= MAX_PLY` 时返回 `fine_evaluate`（Java 无主搜索
  保险丝，仅静态搜索有；连续将军延伸理论上可在 Java 中深递归）；
- `FUTILITY_SCORE` 的行列是 64×64、killer 索引在越界极端情形下钳位
  （Java 为 32×80、killer[64]，越界会抛异常）；
- `stack.pv` 是三角 PV 表（Java 用 NodeLink 链）：每层发现更优着法时立即
  写入"本层最佳着法 + 子层 PV"（`_store_pv`），根层 `stack.pv[0]` 即完整 PV；
- **本模块全部 `@njit(nogil=True, cache=False)`**：numba 0.67 对"递归 +
  跨函数调用 + 磁盘缓存"的组合存在缺陷（缓存加载时报
  `LLVM ERROR: Symbol not found` 并段错误），禁用缓存换取稳定性；代价是
  进程首次调用前需要一次性 JIT 编译（本机约 20s）。`nogil=True` 让搜索
  期间释放 GIL，其他线程可并发写 `ctx.stop`（配合 `nega_scout` 入口检查
  实现亚毫秒级中断；实测 depth8 全量 3.8s 的搜索在置位后 <1ms 返回）。
  递归标志用模块级只读数组 `_FLAGS` 传递，避免 numba 把常量实参字面量化
  导致递归签名不统一；**stop 中断返回的分数/`mate`/PV 无效，必须由上层
  丢弃**（见 `search_depth`）；
- `init_root` 首轮根序为 killer → 全部吃子生成序 → 非吃子生成序，Java 为
  killer → MVV-LVA 吃子 → 历史分混排（排序分在生成时写入 `savePlayChess`）；
  首轮之后的排序由 `_select_best` 动态选择，二者行为一致，首轮差异只影响
  等分着法的尝试顺序、不改变最终分数；
- 共享 TT 多线程写序（Lazy SMP）：`_write_*`/`_copy_slot`/`set_root_tt` 均最后写
  `tt_key`（写序在 numba 生成的原生代码中成立），`get_tt` 用 `inline="never"`
  的 `_key_unchanged` 复核两次 key 一致：函数体内先执行 `_tt_read_barrier()`
  （`~{memory}` 空内联汇编），使 LLVM 无法把复核读与首读做 CSE。`inline="never"`
  只约束 numba IR 层内联（LLVM 仍会内联本函数，实测）；屏障才是复核必然执行的
  保证（编译产物中两处 `asm sideeffect`、`tt_key` load 由 2 次增至 4 次）。
  该方案依赖 x86_64/TSO 的 store-store 顺序：写者先数据后 key、读者复核判定，
  残余「数据已新、key 未更新」窗口为设计接受的棋力级风险；`_copy_slot` 的
  读-改-写窗口更宽但也属同一风险等级。`tt_move` 消费点（`nega_scout` 排序）
  已有 `legal_move` 校验，脏读不会触发非法着法；
"""

import collections

import numpy as np
from llvmlite import ir
from numba import njit, types
from numba.extending import intrinsic

from . import bitboard as _bitboard
from . import constants as C
from . import eval_tables as _eval_tables
from . import evaluate as _evaluate
from . import movegen as _movegen
from . import position as _position

__all__ = [
    "FAIL",
    "FUTILITY_SCORE",
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
    "RAdapt",
    "Stack",
    "clean_tt",
    "fine_evaluate",
    "gen_quiesc_moves",
    "get_tt",
    "history_bonus",
    "history_decay",
    "history_score",
    "init_root",
    "is_danger",
    "is_draw",
    "is_long_check",
    "nega_scout",
    "new_context",
    "new_stack",
    "new_worker_context",
    "quiesc_search",
    "root_nega_scout",
    "rough_evaluate",
    "search_depth",
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
    "tt_key tt_type tt_value tt_depth tt_move tt_exists killer history stop nodes"
    " root_moves root_scores root_count root_inited",
)
Ctx.__doc__ = """搜索上下文。

- `tt_key/tt_type/tt_value/tt_depth/tt_move/tt_exists`：形状 [play][kind][slot]，
  kind 取 `SLOT_STRAIGHT`/`SLOT_STEP`；
- `killer`：int32[64][2]（按剩余深度索引的双槽）；
- `history`：int32[8][256]（基础类型 × 目标格）；
- `stop`：int8[1] 停止标志；`nodes`：int64[1] 节点计数；
- `root_moves`：int32[128] 根着法缓冲；`root_scores`：int32[128] 根着法分数；
  `root_count`：int32[1] 根着法数；`root_inited`：int8[1] 初始化标志。

并行（Lazy SMP）时由 `new_worker_context` 派生的上下文共享 TT 六数组与
`stop`，其余字段各自独立（见该函数）。
"""

# 置换表六数组字段名（并行派生时共享）。
_TT_FIELDS = ("tt_key", "tt_type", "tt_value", "tt_depth", "tt_move", "tt_exists")


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
        root_moves=np.zeros(128, dtype=np.int32),
        root_scores=np.zeros(128, dtype=np.int32),
        root_count=np.zeros(1, dtype=np.int32),
        root_inited=np.zeros(1, dtype=np.int8),
    )


def new_worker_context(ctx, stop):
    """派生 Lazy SMP 工作线程上下文：TT 数组引用共享，其余字段独立。

    共享：`tt_*` 六数组（线程间互补填表）与 `stop`（总停旗，须与
    `ctx.stop` 为同一数组，保证各线程停旗联动）；
    独立：killer/history/nodes 与根着法缓冲（避免线程间互相干扰排序状态）。
    实现为「默认独立、显式共享」：先按同尺寸 `new_context` 新建，再逐个
    替换 TT 六数组为共享引用，避免 `Ctx` 未来新增字段时被静默共享。

    仅限 Python 层调用：numba 不支持 namedtuple 的 `_replace`。
    """
    stop = np.asarray(stop)
    if stop.shape != (1,) or stop.dtype != np.int8:
        raise ValueError("stop 必须是 np.int8[1]")
    if stop is not ctx.stop:
        raise ValueError("stop 必须与 ctx.stop 为同一数组")
    fresh = new_context(hash_size=ctx.tt_key.shape[2])
    return fresh._replace(
        stop=stop, **{field: getattr(ctx, field) for field in _TT_FIELDS}
    )


@njit(nogil=True, cache=False)
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


@intrinsic
def _tt_read_barrier(typingctx):
    """LLVM 内存屏障（空内联汇编 + `~{memory}` clobber），阻止访存跨点合并。

    背景：读复核是纯函数，若 LLVM 把复核读与 `get_tt` 的首读做 CSE 合并，
    复核会被整体消除；numba 0.67 下 `inline="never"` 只约束 numba IR 层内联、
    不产生 LLVM `noinline`，内联与合并的实际发生与否取决于编译上下文。
    函数体内的屏障使 LLVM 无法跨屏障合并访存，复核读因此必然执行。
    """
    sig = types.none()

    def codegen(context, builder, sig, args):
        fty = ir.FunctionType(ir.VoidType(), [])
        asm = ir.InlineAsm(fty, "", "~{memory}", side_effect=True)
        builder.call(asm, [])
        return context.get_dummy_value()

    return sig, codegen


@njit(nogil=True, cache=False, inline="never")
def _key_unchanged(ctx, play, kind, slot, key):
    """复核 TT 槽 key 是否仍等于 `key`（多线程读保护）。

    **`inline="never"` 与 `_tt_read_barrier()` 缺一不可**：`inline="never"`
    只约束 numba IR 层内联，LLVM 仍会把本函数内联进 `get_tt`（numba 0.67
    实测），两次 `tt_key` 读之间存在被 CSE 合并的理论通道；函数体内的内存
    屏障使 LLVM 无法跨屏障合并访存，复核读因此必然执行。
    """
    _tt_read_barrier()
    return ctx.tt_key[play, kind, slot] == key


@njit(nogil=True, cache=False)
def get_tt(ctx, play, zob32, zob64, depth, alpha, beta):
    """探测置换表，返回 `(hit, value, move)`。

    复刻 `getTranZobrist` L335-360：先 STEP 槽后 STRAIGHT 槽（均要求
    `tt_exists` 且 `tt_key == zob64`）。第一个通过 `_get_by_hash_item` 的槽
    直接命中；否则按 Java 逻辑输出失败条目的 `move`（STRAIGHT 优先覆盖）与
    `value`（仅当 `step 不存在或 step.depth < straight.depth` 时被 STRAIGHT
    覆盖）。`move == 0` 表示无着法。

    共享 TT 无锁读复核：写者把 `tt_key` 放在最后写，取完数据后用
    `_key_unchanged`（`inline="never"` + `_tt_read_barrier`，防 LLVM 把复核读
    与首读做 CSE 消除）再读一次 key；不一致即视为条目不完整并放弃该槽，保守
    当作未命中；单线程下 key 不会被并发改动，行为不变。
    """
    slot = zob32 & (ctx.tt_key.shape[2] - 1)
    value = 0
    move = 0

    step_key = ctx.tt_key[play, SLOT_STEP, slot]
    step_exists = ctx.tt_exists[play, SLOT_STEP, slot] and step_key == zob64
    if step_exists:
        step_value = _get_by_hash_item(ctx, play, SLOT_STEP, slot, depth, alpha, beta)
        if _key_unchanged(ctx, play, SLOT_STEP, slot, step_key):
            if step_value != FAIL:
                return True, step_value, ctx.tt_move[play, SLOT_STEP, slot]
            move = ctx.tt_move[play, SLOT_STEP, slot]
            value = ctx.tt_value[play, SLOT_STEP, slot]
        else:
            # 复核失败：条目正被并发覆盖，本槽视为不存在（也不再影响
            # STRAIGHT 的 fallback value 覆盖判断）
            step_exists = False

    straight_key = ctx.tt_key[play, SLOT_STRAIGHT, slot]
    straight_exists = ctx.tt_exists[play, SLOT_STRAIGHT, slot] and straight_key == zob64
    if straight_exists:
        straight_value = _get_by_hash_item(
            ctx, play, SLOT_STRAIGHT, slot, depth, alpha, beta
        )
        if _key_unchanged(ctx, play, SLOT_STRAIGHT, slot, straight_key):
            if straight_value != FAIL:
                return True, straight_value, ctx.tt_move[play, SLOT_STRAIGHT, slot]
            move = ctx.tt_move[play, SLOT_STRAIGHT, slot]
            if (
                not step_exists
                or ctx.tt_depth[play, SLOT_STEP, slot]
                < ctx.tt_depth[play, SLOT_STRAIGHT, slot]
            ):
                value = ctx.tt_value[play, SLOT_STRAIGHT, slot]

    return False, value, move


@njit(nogil=True, cache=False)
def _copy_slot(ctx, play, src_kind, dst_kind, slot):
    """整体复制条目（Java 中把 STEP 旧条目引用赋给 STRAIGHT 槽）。

    被 clean 失效的 STEP 条目踢到 STRAIGHT 后置 `exists=True`：Java 读取
    只看 checkSum、不看 isExists，故 clean 过的旧条目依然可命中；本迁移的
    `get_tt` 额外校验 `tt_exists`，在此保持同样的可观察行为（clean 只让
    STEP 槽失效）。

    共享 TT 无锁写序：key 最后写，读者以两次 key 一致判定条目完整。
    """
    ctx.tt_type[play, dst_kind, slot] = ctx.tt_type[play, src_kind, slot]
    ctx.tt_value[play, dst_kind, slot] = ctx.tt_value[play, src_kind, slot]
    ctx.tt_depth[play, dst_kind, slot] = ctx.tt_depth[play, src_kind, slot]
    ctx.tt_move[play, dst_kind, slot] = ctx.tt_move[play, src_kind, slot]
    ctx.tt_exists[play, dst_kind, slot] = True
    # 共享 TT 无锁写序：key 最后写，读者以两次 key 一致判定条目完整
    ctx.tt_key[play, dst_kind, slot] = ctx.tt_key[play, src_kind, slot]


@njit(nogil=True, cache=False)
def _write_straight(ctx, play, slot, zob64, entry_type, value, depth, move):
    """覆盖写 STRAIGHT 槽（`setTranZobristOverride` else 分支）。

    Java 复用已有 HashItem：`moveNode == null`（move=0）时保留旧 moveNode。
    共享 TT 无锁写序：key 最后写。
    """
    ctx.tt_type[play, SLOT_STRAIGHT, slot] = np.int8(entry_type)
    ctx.tt_value[play, SLOT_STRAIGHT, slot] = np.int32(value)
    ctx.tt_depth[play, SLOT_STRAIGHT, slot] = np.int8(depth)
    if move != 0:
        ctx.tt_move[play, SLOT_STRAIGHT, slot] = np.int32(move)
    ctx.tt_exists[play, SLOT_STRAIGHT, slot] = True
    # 共享 TT 无锁写序：key 最后写
    ctx.tt_key[play, SLOT_STRAIGHT, slot] = zob64


@njit(nogil=True, cache=False)
def _write_step(ctx, play, slot, zob64, entry_type, value, depth, move):
    """把新条目写入 STEP 槽（Java 中总是新建 HashItem，move 默认空）。

    共享 TT 无锁写序：key 最后写。
    """
    ctx.tt_type[play, SLOT_STEP, slot] = np.int8(entry_type)
    ctx.tt_value[play, SLOT_STEP, slot] = np.int32(value)
    ctx.tt_depth[play, SLOT_STEP, slot] = np.int8(depth)
    if move != 0:
        ctx.tt_move[play, SLOT_STEP, slot] = np.int32(move)
    else:
        ctx.tt_move[play, SLOT_STEP, slot] = np.int32(0)
    ctx.tt_exists[play, SLOT_STEP, slot] = True
    # 共享 TT 无锁写序：key 最后写
    ctx.tt_key[play, SLOT_STEP, slot] = zob64


@njit(nogil=True, cache=False)
def _step_allocated(ctx, play, slot):
    """STEP 槽是否分配过条目（对应 Java `HashItem == null` 的反面）。"""
    return (
        ctx.tt_exists[play, SLOT_STEP, slot]
        or ctx.tt_type[play, SLOT_STEP, slot] != 0
        or ctx.tt_key[play, SLOT_STEP, slot] != 0
        or ctx.tt_move[play, SLOT_STEP, slot] != 0
    )


@njit(nogil=True, cache=False)
def set_tt(ctx, play, zob32, zob64, entry_type, value, depth, move):
    """写入置换表（`setTranZobrist` L319-330 + 两个 Override 辅助）。

    - 8000..9000 / -9000..-8000（长将等）不入表；
    - **修正 Java 继承缺陷**：mate 分数（`|value| >= MATE_BOUND`）直接不入表。
      Java 的 mate 分数按 `±(maxScore - ply)` 编码（量纲是 ply），而 TT 读取
      按 `value -= (depth - entry_depth)` 调整（量纲是剩余深度），两者不一致
      会导致同一 ctx 迭代加深时杀步虚报/漂移（3 步杀被报成 4~5 步）；不入表
      后每层重新搜索杀棋，以少量速度换取 mate 步数准确；
    - STEP 槽：已分配且 `tt_exists` 且旧 depth > 新 depth → 只放弃 STEP 更新，
      STRAIGHT 槽仍写新条目；否则旧条目踢出到 STRAIGHT，新条目写 STEP；
    - STEP 未分配时 STEP 与 STRAIGHT 都写新条目。
    """
    if (value >= 8000 and value <= 9000) or (value >= -9000 and value <= -8000):
        return
    if value > MATE_BOUND or value < -MATE_BOUND:
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


@njit(nogil=True, cache=False)
def set_root_tt(ctx, play, zob32, zob64, move):
    """IID 根槽写入（`setRootTranZobrist` L177-185）。

    只覆盖 STEP 槽的 checkSum 与 moveNode，不改 depth/entry_type/value；
    槽从未分配时按新建 `HashItem` 默认 `isExists=true` 置位。
    共享 TT 无锁写序：key 最后写。
    """
    slot = zob32 & (ctx.tt_key.shape[2] - 1)
    if not _step_allocated(ctx, play, slot):
        ctx.tt_exists[play, SLOT_STEP, slot] = True
    ctx.tt_move[play, SLOT_STEP, slot] = np.int32(move)
    # 共享 TT 无锁写序：key 最后写
    ctx.tt_key[play, SLOT_STEP, slot] = zob64


@njit(nogil=True, cache=False)
def clean_tt(ctx):
    """清理 STEP 槽（`cleanTranZobrist` L67-78）：只把 exists 置 False。"""
    for play in range(2):
        for slot in range(ctx.tt_exists.shape[2]):
            ctx.tt_exists[play, SLOT_STEP, slot] = False


@njit(nogil=True, cache=False)
def update_killer(ctx, depth, move):
    """killer 双槽轮转：`killer[depth][1] = killer[depth][0]; [0] = move`。"""
    ctx.killer[depth, 1] = ctx.killer[depth, 0]
    ctx.killer[depth, 0] = np.int32(move)


@njit(nogil=True, cache=False)
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


@njit(nogil=True, cache=False)
def history_decay(ctx):
    """历史衰减（`AICoreHandler.moveEnd`）：逐元素 `/512`，**向零截断**。"""
    for i in range(ctx.history.shape[0]):
        for j in range(ctx.history.shape[1]):
            v = np.int64(ctx.history[i, j])
            if v >= 0:
                ctx.history[i, j] = np.int32(v // 512)
            else:
                ctx.history[i, j] = np.int32(-((-v) // 512))


@njit(nogil=True, cache=False)
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

Stack = collections.namedtuple("Stack", "zob32 zob64 is_eat chk is_null pv")
Stack.__doc__ = """搜索栈（对应 Java NodeLink 链 + Task 11 的三角 PV 表）。

- `zob32`/`zob64`：int64[68]，第 ply 层局面的 zobrist（走到该局面**之后**）；
- `is_eat`：int8[68]，走到该局面的着法是否吃子（长将回溯的截断条件）；
- `chk`：int8[68]，该局面是否被将（由搜索层设置）；
- `is_null`：int8[68]，该层是否为空着节点（回溯终止条件）；
- `pv`：int32[68][68] 三角 PV 表（`pv[ply][0]` 是本层最佳着法）。

ply 0 为根节点（Java 根 NodeLink 的 depth=0，moveNode 为空、不参与长将回溯）。
"""


def new_stack():
    """新建全零搜索栈。"""
    return Stack(
        zob32=np.zeros(STACK_SIZE, dtype=np.int64),
        zob64=np.zeros(STACK_SIZE, dtype=np.int64),
        is_eat=np.zeros(STACK_SIZE, dtype=np.int8),
        chk=np.zeros(STACK_SIZE, dtype=np.int8),
        is_null=np.zeros(STACK_SIZE, dtype=np.int8),
        pv=np.zeros((STACK_SIZE, STACK_SIZE), dtype=np.int32),
    )


@njit(nogil=True, cache=False)
def fine_evaluate(st, play, ctx):
    """精确评估（`fineEvaluate` L115-118）：计节点数后按阶段分派 `evaluate`。"""
    ctx.nodes[0] += 1
    return _evaluate.evaluate(st, play)


@njit(nogil=True, cache=False)
def rough_evaluate(st, play):
    """粗评估（`roughEvaluate` L123-125）：`base_score[play] - base_score[1-play]`。"""
    return st.base_score[play] - st.base_score[1 - play]


@njit(nogil=True, cache=False)
def is_long_check(stack, ply):
    """长将检测（`isLongChk` L240-260）。

    仅当第 ply 层被将时检测：从 `ply-1` 向根回溯到第 1 层（根节点不参与，
    对应 Java `getMoveNode()==null` 终止），先比较 zobrist（相等即长将），
    再判断该层着法是否吃子（吃子截断）。空着节点没有着法，遇到即终止
    （对应 Java nullNode 的 `getMoveNode()==null`）。
    """
    if stack.chk[ply] == 0:
        return False
    t = ply - 1
    while t > 0:
        if stack.is_null[t] != 0:
            break
        if stack.zob32[t] == stack.zob32[ply] and stack.zob64[t] == stack.zob64[ply]:
            return True
        if stack.is_eat[t] != 0:
            return False
        t -= 1
    return False


@njit(nogil=True, cache=False)
def is_draw(st, stack, ply):
    """和棋判定（`isDraw` L267-273）：双方攻击子（兵卒车马炮）数都为 0。

    `st.attack_def[play, 0]` 即 Java `getAttackChessesNum`（`indexOfAttackAndDefense`
    中兵/卒与车马炮同为攻击子，士/象/将为防御子）；只依赖局面，不检查是否吃子。
    `stack`/`ply` 为调用一致性保留（Java 签名带 `lastLink` 但未使用其内容）。
    """
    return st.attack_def[C.RED, 0] == 0 and st.attack_def[C.BLACK, 0] == 0


@njit(nogil=True, cache=False)
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


@njit(nogil=True, cache=False)
def _store_pv(stack, ply, move):
    """把本层最佳着法与子层 PV 写入三角表（对应 Java `setNextLink(bestNodeLink)`）。

    约定：父层在 make 之后已把子层 `pv[ply+1][0]` 清零，故子层未写 PV
    （TT 命中/将死/长将/和棋早退）时复制立即终止。
    """
    stack.pv[ply, 0] = np.int32(move)
    j = 0
    while j + 1 < STACK_SIZE and stack.pv[ply + 1, j] != 0:
        stack.pv[ply, j + 1] = stack.pv[ply + 1, j]
        j += 1
    if j + 1 < STACK_SIZE:
        stack.pv[ply, j + 1] = 0


@njit(nogil=True, cache=False)
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


@njit(nogil=True, cache=False)
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
    best_move = np.int32(0)
    if not is_checked:
        # Java：非被将时 isMove 先置 true，即使无着法也返回 stand-pat
        is_move = True
        v = fine_evaluate(st, play, ctx)
        if v > best:
            if v >= beta:
                return v
            best = v
            alpha = max(alpha, v)

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
        stack.pv[ply + 1, 0] = 0
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
            best_move = m
            _store_pv(stack, ply, best_move)
            alpha = max(alpha, v)
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
            stack.pv[ply + 1, 0] = 0
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
                best_move = m
                _store_pv(stack, ply, best_move)
                alpha = max(alpha, v)
                if v >= beta:
                    return best

    if is_move:
        return best
    return -(C.MAX_SCORE - ply)


# --------------------------------------------------------------------------
# Task 11：主搜索（根 PVS + negaScout + 迭代加深）
# --------------------------------------------------------------------------

# Futility 分数表（`FutilityScore`，Java L19-30）：
# `FUTILITY_SCORE[d][k] = (int)(d * 1.29 * 155) - k * d * 10`，d=0 行全 0。
FUTILITY_SCORE = np.zeros((64, 64), dtype=np.int32)
for _d in range(64):
    _base = int(_d * 1.29 * 155)
    for _k in range(64):
        FUTILITY_SCORE[_d, _k] = _base - _k * _d * 10
del _d, _k, _base

# 危险区（`DangerMarginBit`，Java L287-313）：
# [0]=黑方半场（row0-2 + row3 中路）、[1]=红方半场（row6 中路 + row7-9）。
_BLACK_DANGER_SITES = list(range(27)) + [30, 31, 32]
_RED_DANGER_SITES = [57, 58, 59] + list(range(63, 90))
DANGER_MARGIN_LO = np.zeros(2, dtype=np.int64)
DANGER_MARGIN_HI = np.zeros(2, dtype=np.int64)
for _play, _sites in ((C.BLACK, _BLACK_DANGER_SITES), (C.RED, _RED_DANGER_SITES)):
    for _site in _sites:
        if _site < 64:
            DANGER_MARGIN_LO[_play] |= np.int64(1) << np.int64(_site)
        else:
            DANGER_MARGIN_HI[_play] |= np.int64(1) << np.int64(_site - 64)
del _play, _sites, _site

for _table in (FUTILITY_SCORE, DANGER_MARGIN_LO, DANGER_MARGIN_HI):
    _table.setflags(write=False)
del _table


# 递归标志来源（0=非 PV / 1=PV / 2=非空着 / 3=空着）：
# numba 对递归函数的常量实参会做字面量特化，导致 LLVM unresolved symbol；
# 通过模块级只读数组读取可保证实参类型恒为 int64。
_FLAGS = np.array([0, 1, 0, 1], dtype=np.int64)
_FLAGS.setflags(write=False)


@njit(nogil=True, cache=False)
def RAdapt(depth):
    """空着归约自适应 R（`RAdapt` L102-113）：<=6 → 2、<=8 → 3、否则 4。"""
    if depth <= 6:
        return 2
    if depth <= 8:
        return 3
    return 4


@njit(nogil=True, cache=False)
def is_danger(st, play):
    """危险判定（`isDanger` L274-286）。

    统计对方（1-play）车/马/炮落在 `DANGER_MARGIN[play]`（play 方九宫附近
    半场）内的数量，>= 3 视为危险（不安全，禁用 Futility 与 LMR）。
    """
    opp = 1 - play
    lo = np.int64(0)
    hi = np.int64(0)
    for kind in (C.CHARIOT, C.KNIGHT, C.GUN):
        role = kind + 7 * (1 - opp)
        lo |= st.mask_role[role, 0]
        hi |= st.mask_role[role, 1]
    return (
        _bitboard.count(lo & DANGER_MARGIN_LO[play], hi & DANGER_MARGIN_HI[play]) >= 3
    )


@njit(nogil=True, cache=False)
def _int32_wrap(v):
    """把 int64 按 Java int 语义环绕到 int32 范围（历史分加法用）。"""
    v = ((v + 0x80000000) & 0xFFFFFFFF) - 0x80000000
    return v


@njit(nogil=True, cache=False)
def _killer_index(depth):
    """killer 行索引钳位（Java killerMove[64] 越界会抛异常，此处防御）。"""
    d = depth if depth < 64 else 63
    d = max(d, 0)
    return d


@njit(nogil=True, cache=False)
def init_root(st, ctx, stack, killer_depth=0):
    """枚举根着法（`searchMove` L54-66）。

    与主搜索排序器相同的阶段顺序（TT 着法为空）：killer1 → killer2 →
    good/general 生成序；每个着法 make 后用 `in_check` 过滤自将，通过者写入
    `ctx.root_moves`，初始分 100, 99, 98...（Java `moveNode.score=initScore--`）。
    设置 `root_count` 与 `root_inited`；生成列表中的着法已按 repeat 语义
    与 killer 去重。

    `killer_depth` 对应 Java 根枚举的 `killerMove[depth]`（迭代加深的目标深度）。
    """
    play = np.int64(st.side_to_move[0])
    kd = _killer_index(killer_depth)
    limit = ctx.root_moves.shape[0]

    killer0 = np.int64(ctx.killer[kd, 0])
    killer1 = np.int64(ctx.killer[kd, 1])
    seen = np.zeros(4, dtype=np.int32)
    seen_n = 0
    head = np.zeros(2, dtype=np.int32)
    head_n = 0
    if killer0 != 0 and _movegen.legal_move(st, play, killer0):
        head[head_n] = np.int32(killer0)
        head_n += 1
        seen[seen_n] = np.int32(killer0)
        seen_n += 1
    if killer1 != 0 and killer1 != killer0 and _movegen.legal_move(st, play, killer1):
        head[head_n] = np.int32(killer1)
        head_n += 1
        seen[seen_n] = np.int32(killer1)
        seen_n += 1

    count = 0
    init_score = np.int32(100)
    for h in range(head_n):
        m = np.int64(head[h])
        undo = _position.make_move(st, m)
        ok = not _movegen.in_check(st, play)
        _position.unmake_move(st, m, undo)
        if ok and count < limit:
            ctx.root_moves[count] = np.int32(m)
            ctx.root_scores[count] = init_score
            count += 1
            init_score -= np.int32(1)

    move_buf = np.empty(_movegen.MAX_MOVES, dtype=np.int32)
    n_total = _movegen.gen_moves_into(st, play, move_buf, False)
    for phase in range(2):
        for idx in range(n_total):
            m = np.int64(move_buf[idx])
            is_eat = st.board[C.move_dest(m)] != 0
            if (phase == 0) != is_eat:
                continue
            skip = False
            for j in range(seen_n):
                if seen[j] == m:
                    seen[j] = seen[seen_n - 1]
                    seen_n -= 1
                    skip = True
                    break
            if skip:
                continue
            undo = _position.make_move(st, m)
            ok = not _movegen.in_check(st, play)
            _position.unmake_move(st, m, undo)
            if ok and count < limit:
                ctx.root_moves[count] = np.int32(m)
                ctx.root_scores[count] = init_score
                count += 1
                init_score -= np.int32(1)

    ctx.root_count[0] = np.int32(count)
    ctx.root_inited[0] = np.int8(1)


@njit(nogil=True, cache=False)
def search_depth(st, ctx, stack, depth):
    """一轮迭代加深的根搜索（`searchMove` 单轮 + `rootNegaScout`）。

    返回 `(score, mate)`：`score` 是根走子方视角分数；`mate` 是杀棋步数
    （正 = 己方 N 个 ply 内将杀，负 = 被对方 N 个 ply 内将杀，0 = 无杀）。

    若 `ctx.root_inited == 0` 先调用 `init_root`（`killer_depth=depth`）；
    连续多轮调用时复用已按分数排序的根着法列表，等价于 Java 的
    `for d in range(4, depth+1)` 迭代。每轮按 Java L71-78 用 PV 路径覆写
    killer 表（`killerMove[d+1..0]`）。

    **中断语义**：`ctx.stop` 置位后当前着法搜索完即返回，且未搜索完成的
    层会从下界保护处被直接裁剪，因此 **stop 中断返回的 `score`/`mate`/PV
    不可信，调用方必须丢弃该层结果**（本函数不做重试）。njit 均为
    `nogil=True`，搜索期间其他线程可并发置位 `ctx.stop`。
    """
    if ctx.root_inited[0] == 0:
        init_root(st, ctx, stack, depth)
    stack.pv[0, 0] = 0
    score = root_nega_scout(st, ctx, stack, -C.MAX_SCORE, C.MAX_SCORE, depth)

    mate = np.int64(0)
    if score > MATE_BOUND:
        mate = np.int64(C.MAX_SCORE - score)
    elif score < -MATE_BOUND:
        mate = np.int64(-(C.MAX_SCORE + score))

    # Java L71-78：PV 链写入 killerMove[d+1], killerMove[d], ..., killerMove[0]
    k = depth + 1
    j = 0
    while j < STACK_SIZE and k >= 0 and k < 64 and stack.pv[0, j] != 0:
        update_killer(ctx, k, np.int64(stack.pv[0, j]))
        j += 1
        k -= 1
    return score, mate


@njit(nogil=True, cache=False)
def root_nega_scout(st, ctx, stack, alpha, beta, depth):
    """根节点 PVS（`rootNegaScout` L95-148），返回根走子方视角分数。

    逐着法 `_select_best` 原地选择最优（`getSortAfterBestMove`）；
    首着全窗口、后续零窗口探测 + 超过 thisAlpha 时全窗口重搜；结果写回
    `root_scores` 供下一轮排序。根节点**无 beta 截断**；每着后检查
    `ctx.stop`（Java L135-137），中断时返回当前 best；无着法时返回
    `-(MAX_SCORE - 0)`。收尾把本层 PV 写入 `stack.pv[0]`。
    """
    play = np.int64(st.side_to_move[0])
    stack.chk[0] = 1 if _movegen.in_check(st, play) else 0
    # 递归标志从模块级只读数组读取（numba 会把常量实参字面量化，导致
    # 递归函数出现 `Literal[int]` 特化与 LLVM unresolved symbol）
    probe_pv = np.int64(_FLAGS[0])
    full_pv = np.int64(_FLAGS[1])
    not_null = np.int64(_FLAGS[2])

    count = int(ctx.root_count[0])
    this_alpha = np.int64(alpha)
    best_value = np.int64(-C.MAX_SCORE - 2)
    is_move = False
    i = 0
    while i < count:
        _select_best(ctx.root_moves, ctx.root_scores, i, count)
        m = np.int64(ctx.root_moves[i])
        i += 1
        is_eat = st.board[C.move_dest(m)] != 0
        undo = _position.make_move(st, m)
        stack.zob32[1] = st.zob[0]
        stack.zob64[1] = st.zob[1]
        if is_eat:
            stack.is_eat[1] = 1
        else:
            stack.is_eat[1] = 0
        stack.is_null[1] = 0
        stack.pv[1, 0] = 0
        if is_move:
            v = -nega_scout(
                st,
                ctx,
                stack,
                -this_alpha - 1,
                -this_alpha,
                depth - 1,
                1,
                1 - play,
                probe_pv,
                not_null,
            )
            if v > this_alpha:
                v = -nega_scout(
                    st,
                    ctx,
                    stack,
                    -beta,
                    -this_alpha,
                    depth - 1,
                    1,
                    1 - play,
                    full_pv,
                    not_null,
                )
        else:
            v = -nega_scout(
                st,
                ctx,
                stack,
                -beta,
                -this_alpha,
                depth - 1,
                1,
                1 - play,
                full_pv,
                not_null,
            )
            is_move = True
        _position.unmake_move(st, m, undo)
        ctx.root_scores[i - 1] = np.int32(v)
        if v > best_value:
            best_value = v
            this_alpha = max(this_alpha, v)
            # 立即落盘本层 PV：后续着法的搜索会覆盖子层 pv[1]
            _store_pv(stack, 0, np.int64(m))
        if ctx.stop[0] != 0:
            break

    if is_move:
        return best_value
    return np.int64(-(C.MAX_SCORE - 0))


@njit(nogil=True, cache=False)
def nega_scout(st, ctx, stack, alpha, beta, depth, ply, play, is_pv, is_null):
    """内部 PVS + negaScout（`negaScout` L154-337），返回 play 视角分数。

    按 Java 顺序：己方将已被吃 → 下界保护（`ply-MAX_SCORE`）→ TT 探测 →
    被将状态写入 `stack.chk` → 长将 8888 → 和棋（仅非空着且上一步吃子）→
    将军延伸 → `depth<=0` 转静态搜索 → 空着裁剪 → IID → 着法循环
    （TT/killer/good 吃子/general，Futility、PVS/LMR、beta 截断写 killer）→
    收尾写 PV/历史/TT。

    **中断增强**：入口检查 `ctx.stop`（Java 只在根循环检查），置位立即
    返回当前下界 `ply - MAX_SCORE`；所有 njit 为 `nogil=True`，搜索期间
    释放 GIL，其他线程可并发置位（中断延迟为亚毫秒级）。此时分数无效，
    由上层丢弃该层结果。

    `is_pv`/`is_null` 是 int64 标志（1=是、0=否；不用 bool 以避免 numba
    对递归函数生成 `Literal[bool]` 特化时的 LLVM 缺陷）。`is_null=1`
    表示当前节点是空着节点（Java `lastLink.isNullMove`）；空着递归时
    子层 `is_null=1`、`is_eat=0`、zobrist 不变。
    """
    play = np.int64(play)
    # 递归标志从模块级只读数组读取：numba 会把常量实参字面量化，使递归
    # 函数出现 `Literal[int]`/`Literal[bool]` 特化并报 LLVM unresolved symbol
    child_probe_pv = np.int64(_FLAGS[0])
    child_full_pv = np.int64(_FLAGS[1])
    child_not_null = np.int64(_FLAGS[2])
    child_is_null = np.int64(_FLAGS[3])
    # 1. 己方将已被吃（Java L158）
    if st.all_chess[C.PIECE_STARTS[play]] == C.NOTHING:
        return np.int64(ply - C.MAX_SCORE)
    # 2. 下界保护（L161-162）
    best_value = np.int64(ply - C.MAX_SCORE)
    if best_value > beta:
        return best_value
    # 有意增强：入口停旗检查（Java 只在根循环检查）
    if ctx.stop[0] != 0:
        return best_value
    # 深度保险丝：栈长 68，ply 到 64 即停（Java 主搜索无此保险丝）
    if ply >= MAX_PLY:
        return fine_evaluate(st, play, ctx)
    # 3. TT 探测（L164-169）
    hit, tt_value, tt_move = get_tt(ctx, play, st.zob[0], st.zob[1], depth, alpha, beta)
    if hit:
        return np.int64(tt_value)
    # 4. 被将状态（L171-173）
    is_checked = _movegen.in_check(st, play)
    stack.chk[ply] = 1 if is_checked else 0
    if is_null != 0:
        stack.is_null[ply] = 1
    else:
        stack.is_null[ply] = 0
    # 5. 长将（L175-177）
    if is_long_check(stack, ply):
        return np.int64(C.LONG_CHECK_SCORE)
    # 6. 和棋（L178-183）：仅非空着且上一步吃子时检查
    if is_null == 0 and stack.is_eat[ply] != 0 and is_draw(st, stack, ply):
        return np.int64(C.DRAW_SCORE)
    # 7. 将军延伸（L185-188）
    if is_checked:
        depth += 1
    entry_type = np.int64(HASH_ALPHA)
    # 8. 静态搜索（L192-196，stopDepth 恒 0）
    if depth <= 0:
        return quiesc_search(st, ctx, stack, alpha, beta, ply, play, is_checked)

    # 9. 空着裁剪（L201-222）
    if is_null == 0 and (not is_checked) and is_pv == 0 and depth >= 2:
        null_r = RAdapt(depth)
        attack_num = np.int64(st.attack_def[play, 0])
        if attack_num > 0:
            stack.zob32[ply + 1] = st.zob[0]
            stack.zob64[ply + 1] = st.zob[1]
            stack.is_eat[ply + 1] = 0
            stack.is_null[ply + 1] = 1
            stack.pv[ply + 1, 0] = 0
            val = -nega_scout(
                st,
                ctx,
                stack,
                -beta,
                -beta + 1,
                depth - null_r - 1,
                ply + 1,
                1 - play,
                child_probe_pv,
                child_is_null,
            )
            if val >= beta:
                if attack_num > 2 and depth < 6:
                    return val
                # 深验证的空着裁剪（L215-218）
                val = -nega_scout(
                    st,
                    ctx,
                    stack,
                    -beta,
                    -beta + 1,
                    depth - null_r + 1,
                    ply + 1,
                    1 - play,
                    child_probe_pv,
                    child_is_null,
                )
                if val >= beta:
                    return val

    # 10. IID（L224-230）
    if depth >= 6 and is_pv != 0 and tt_move == 0:
        nega_scout(st, ctx, stack, alpha, beta, depth - 2, ply, play, is_pv, is_null)
        if stack.pv[ply, 0] != 0:
            tt_move = np.int64(stack.pv[ply, 0])
            set_root_tt(ctx, play, st.zob[0], st.zob[1], tt_move)

    # 11. 着法排序器（L231-238）
    kd = _killer_index(depth)
    killer0 = np.int64(ctx.killer[kd, 0])
    killer1 = np.int64(ctx.killer[kd, 1])
    seen = np.zeros(3, dtype=np.int32)
    seen_n = 0
    head = np.zeros(3, dtype=np.int32)
    head_n = 0
    if tt_move != 0 and _movegen.legal_move(st, play, tt_move):
        head[head_n] = np.int32(tt_move)
        head_n += 1
        seen[seen_n] = np.int32(tt_move)
        seen_n += 1
    if killer0 != 0 and killer0 != tt_move and _movegen.legal_move(st, play, killer0):
        head[head_n] = np.int32(killer0)
        head_n += 1
        seen[seen_n] = np.int32(killer0)
        seen_n += 1
    if (
        killer1 != 0
        and killer1 != tt_move
        and killer1 != killer0
        and _movegen.legal_move(st, play, killer1)
    ):
        head[head_n] = np.int32(killer1)
        head_n += 1
        seen[seen_n] = np.int32(killer1)
        seen_n += 1

    opp_lo, opp_hi = _movegen.opp_attack_site(st, play)
    move_buf = np.empty(_movegen.MAX_MOVES, dtype=np.int32)
    n_total = _movegen.gen_moves_into(st, play, move_buf, False)
    eat_buf = np.empty(_movegen.MAX_MOVES, dtype=np.int32)
    eat_score = np.empty(_movegen.MAX_MOVES, dtype=np.int32)
    gen_buf = np.empty(_movegen.MAX_MOVES, dtype=np.int32)
    gen_score = np.empty(_movegen.MAX_MOVES, dtype=np.int32)
    eat_n = 0
    gen_n = 0
    for phase in range(2):
        for idx in range(n_total):
            m = np.int64(move_buf[idx])
            dest = C.move_dest(m)
            src = C.move_src(m)
            src_chess = st.board[src]
            dest_chess = st.board[dest]
            is_eat = dest_chess != 0
            if (phase == 0) != is_eat:
                continue
            skip = False
            for j in range(seen_n):
                if seen[j] == m:
                    seen[j] = seen[seen_n - 1]
                    seen_n -= 1
                    skip = True
                    break
            if skip:
                continue
            is_opp_protect = _bitboard.has_site(opp_lo, opp_hi, dest)
            if is_eat:
                if is_opp_protect:
                    src_score = np.int64(
                        _eval_tables.BASE_SCORES[src_chess]
                    ) + _position.attach_score(st, C.PIECE_ROLES[src_chess], src)
                else:
                    src_score = np.int64(-500)
                dest_score = np.int64(
                    _eval_tables.BASE_SCORES[dest_chess]
                ) + _position.attach_score(st, C.PIECE_ROLES[dest_chess], dest)
                if dest_score >= src_score:
                    if eat_n < eat_buf.shape[0]:
                        eat_buf[eat_n] = np.int32(m)
                        eat_score[eat_n] = np.int32(dest_score - src_score)
                        eat_n += 1
                    continue
            if gen_n < gen_buf.shape[0]:
                gen_buf[gen_n] = np.int32(m)
                h = np.int64(ctx.history[C.PIECE_KINDS[src_chess], dest]) + (
                    np.int64(0) if is_opp_protect else np.int64(256)
                )
                gen_score[gen_n] = np.int32(_int32_wrap(h))
                gen_n += 1

    is_move = False
    this_alpha = np.int64(alpha)
    best_move = np.int32(0)
    moves_searched = 0
    if is_pv != 0:
        moves_count = 10
    else:
        moves_count = 5
    stop_all = False
    for phase in range(3):
        if phase == 0:
            cur_n = head_n
        elif phase == 1:
            cur_n = eat_n
        else:
            cur_n = gen_n
        j = 0
        while j < cur_n:
            if phase == 0:
                m = np.int64(head[j])
            elif phase == 1:
                _select_best(eat_buf, eat_score, j, eat_n)
                m = np.int64(eat_buf[j])
            else:
                _select_best(gen_buf, gen_score, j, gen_n)
                m = np.int64(gen_buf[j])
            j += 1

            undo = _position.make_move(st, m)
            # 自将过滤（L243-248）
            if _movegen.in_check(st, play):
                _position.unmake_move(st, m, undo)
                continue
            # Futility 跳过（L256-260）
            if (
                (not is_checked)
                and is_pv == 0
                and depth < 6
                and (not is_danger(st, play))
                and moves_searched >= moves_count
            ):
                d_idx = depth if depth < 64 else 63
                k_idx = moves_searched if moves_searched < 64 else 63
                if (
                    np.int64(FUTILITY_SCORE[d_idx, k_idx]) + rough_evaluate(st, play)
                    < this_alpha
                ):
                    _position.unmake_move(st, m, undo)
                    moves_searched += 1
                    continue

            # 子节点栈层（对应 nodeLinkTemp）
            stack.zob32[ply + 1] = st.zob[0]
            stack.zob64[ply + 1] = st.zob[1]
            if st.board[C.move_dest(m)] != 0:
                stack.is_eat[ply + 1] = 1
            else:
                stack.is_eat[ply + 1] = 0
            stack.is_null[ply + 1] = 0
            stack.pv[ply + 1, 0] = 0

            if is_move:
                # PVS + LMR（L265-290）
                kk = 2
                if (not is_checked) and depth >= 3 and moves_searched >= moves_count:
                    if not is_danger(st, 1 - play):
                        if moves_searched >= (moves_count + (5 + depth)) * 2:
                            kk = 4
                        elif moves_searched >= moves_count + 5 + depth:
                            kk = 3
                    v = -nega_scout(
                        st,
                        ctx,
                        stack,
                        -this_alpha - 1,
                        -this_alpha,
                        depth - kk,
                        ply + 1,
                        1 - play,
                        child_probe_pv,
                        child_not_null,
                    )
                else:
                    v = this_alpha + 1
                if v > this_alpha:
                    if kk > 1:
                        # 解除归约（L280-281）
                        v = -nega_scout(
                            st,
                            ctx,
                            stack,
                            -this_alpha - 1,
                            -this_alpha,
                            depth - 1,
                            ply + 1,
                            1 - play,
                            child_probe_pv,
                            child_not_null,
                        )
                    if v > this_alpha:
                        # 全窗口重搜（L283）
                        v = -nega_scout(
                            st,
                            ctx,
                            stack,
                            -beta,
                            -this_alpha,
                            depth - 1,
                            ply + 1,
                            1 - play,
                            child_full_pv,
                            child_not_null,
                        )
            else:
                # 首着全窗口（L288-289）
                v = -nega_scout(
                    st,
                    ctx,
                    stack,
                    -beta,
                    -this_alpha,
                    depth - 1,
                    ply + 1,
                    1 - play,
                    child_full_pv,
                    child_not_null,
                )
                is_move = True

            _position.unmake_move(st, m, undo)
            moves_searched += 1
            if v > best_value:
                best_value = v
                best_move = np.int32(m)
                # 立即落盘本层 PV：后续着法的搜索会覆盖子层 pv[ply+1]
                _store_pv(stack, ply, np.int64(m))
                # beta 截断（L298-307）
                if v >= beta:
                    if is_null == 0 and m != killer0 and m != killer1:
                        update_killer(ctx, kd, np.int32(m))
                    entry_type = np.int64(HASH_BETA)
                    stop_all = True
                    break
                if v > this_alpha:
                    this_alpha = v
                    entry_type = np.int64(HASH_PV)
        if stop_all:
            break

    # 12. 收尾（L317-334）
    if is_move:
        if entry_type != HASH_ALPHA and best_move != 0:
            best_src = C.move_src(best_move)
            best_dest = C.move_dest(best_move)
            history_bonus(ctx, np.int64(st.board[best_src]), best_dest, depth)
        if entry_type != HASH_ALPHA:
            set_tt(
                ctx,
                play,
                st.zob[0],
                st.zob[1],
                entry_type,
                best_value,
                depth,
                np.int64(best_move),
            )
        else:
            set_tt(
                ctx,
                play,
                st.zob[0],
                st.zob[1],
                entry_type,
                best_value,
                depth,
                np.int64(0),
            )
        return best_value
    return best_value
