"""Task 9：置换表、杀手着法与历史启发表（`engine/search.py`）的测试。

覆盖：
- Ctx 布局与空表；
- TT 三种 entry_type 的写入/读取往返、深度限制、mate 分数调整；
- 8000-9000 长将分数不入表；
- STEP 槽按深度替换（踢出/放弃）与 STRAIGHT 槽的覆盖语义；
- 槽位边界（slot == N-1）与掩码等价；
- clean_tt 只失效 STEP 槽；
- killer 双槽轮转、history 加分/衰减/读取。

Java 参考：`TranspositionTable.java` L67-78/L177-185/L264-330/L335-391、
`CHistoryHeuritic.java` L11-35。
"""

import numpy as np

from engine import constants as C
from engine import search as S

SMALL = 1 << 10
Z32 = 0x1A2B3C
Z64 = 0x0123456789ABCDEF


def ctx_small():
    return S.new_context(hash_size=SMALL)


def slot_of(zob32, n=SMALL):
    return zob32 & (n - 1)


# --------------------------------------------------------------------------
# Ctx 布局
# --------------------------------------------------------------------------


def test_new_context_shapes_and_empty():
    ctx = S.new_context(hash_size=1 << 8)
    assert ctx.tt_key.shape == (2, 2, 1 << 8)
    assert ctx.tt_key.dtype == np.int64
    assert ctx.tt_type.shape == (2, 2, 1 << 8)
    assert ctx.tt_type.dtype == np.int8
    assert ctx.tt_value.dtype == np.int32
    assert ctx.tt_depth.dtype == np.int8
    assert ctx.tt_move.shape == (2, 2, 1 << 8)
    assert ctx.tt_move.dtype == np.int32
    assert ctx.tt_exists.shape == (2, 2, 1 << 8)
    assert ctx.tt_exists.dtype == np.bool_
    assert ctx.killer.shape == (64, 2)
    assert ctx.killer.dtype == np.int32
    assert ctx.history.shape == (8, 256)
    assert ctx.history.dtype == np.int32
    assert ctx.stop.shape == (1,)
    assert ctx.stop.dtype == np.int8
    assert ctx.nodes.shape == (1,)
    assert ctx.nodes.dtype == np.int64
    assert not ctx.tt_exists.any()
    assert not ctx.killer.any()
    assert not ctx.history.any()
    assert ctx.stop[0] == 0 and ctx.nodes[0] == 0


def test_default_hash_size_and_constants():
    assert S.N == 1 << 19
    assert S._SLOT_MASK == S.N - 1
    assert S.SLOT_STRAIGHT == 0 and S.SLOT_STEP == 1
    assert (S.HASH_BETA, S.HASH_ALPHA, S.HASH_PV) == (1, 2, 3)
    assert S.FAIL == np.iinfo(np.int32).min + 1
    ctx = S.new_context()
    assert ctx.tt_key.shape == (2, 2, S.N)
    # 默认尺寸下最后一个槽（Java 缺陷位置）读写安全
    move = C.pack_move(0, 1)
    S.set_tt(ctx, 0, S.N - 1, Z64, S.HASH_PV, 42, 3, move)
    assert ctx.tt_value[0, S.SLOT_STEP, S.N - 1] == 42
    hit, value, got_move = S.get_tt(ctx, 0, S.N - 1, Z64, 3, -9999, 9999)
    assert hit and value == 42 and got_move == move
    S.clean_tt(ctx)


# --------------------------------------------------------------------------
# TT 基本读写
# --------------------------------------------------------------------------


def test_tt_roundtrip_all_entry_types():
    move = C.pack_move(2, 3)
    cases = (
        (S.HASH_BETA, 500, -9999, 500),
        (S.HASH_ALPHA, 500, 500, 9999),
        (S.HASH_PV, 500, -9999, 9999),
    )
    for entry_type, value, alpha, beta in cases:
        ctx = ctx_small()
        S.set_tt(ctx, 0, Z32, Z64, entry_type, value, 6, move)
        hit, got_value, got_move = S.get_tt(ctx, 0, Z32, Z64, 6, alpha, beta)
        assert hit
        assert got_value == value
        assert got_move == move


def test_tt_plays_are_separate():
    move = C.pack_move(2, 3)
    ctx = ctx_small()
    S.set_tt(ctx, C.RED, Z32, Z64, S.HASH_PV, 500, 6, move)
    assert S.get_tt(ctx, C.RED, Z32, Z64, 6, -9999, 9999)[0]
    assert not S.get_tt(ctx, C.BLACK, Z32, Z64, 6, -9999, 9999)[0]


def test_tt_key_mismatch_misses():
    move = C.pack_move(2, 3)
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 500, 6, move)
    assert not S.get_tt(ctx, 0, Z32, Z64 ^ 1, 6, -9999, 9999)[0]


def test_depth_too_shallow_misses_non_mate():
    move = C.pack_move(2, 3)
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 100, 3, move)
    hit, value, _ = S.get_tt(ctx, 0, Z32, Z64, 5, -9999, 9999)
    assert not hit
    assert value == 100  # Java value[0] 仍输出失败条目的原始 value


def test_mate_value_hits_despite_depth_and_adjusts():
    move = C.pack_move(2, 3)
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 9990, 5, move)
    hit, value, got_move = S.get_tt(ctx, 0, Z32, Z64, 8, -9999, 9999)
    assert hit
    assert value == 9990 - (8 - 5)  # value -= depth - entry_depth
    assert got_move == move

    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, -9990, 5, move)
    hit, value, _ = S.get_tt(ctx, 0, Z32, Z64, 8, -9999, 9999)
    assert hit
    assert value == -9990 + (8 - 5)  # value += depth - entry_depth


def test_mate_else_if_chain_boundary():
    move = C.pack_move(2, 3)
    # value == 9899 不满足 value > mateNode，落入 else-if 的 entry_depth < depth
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, S.MATE_BOUND, 3, move)
    assert not S.get_tt(ctx, 0, Z32, Z64, 5, -9999, 9999)[0]
    # value == 9900 是 mate 分支：不做 entry_depth < depth 检查
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, S.MATE_BOUND + 1, 3, move)
    hit, value, _ = S.get_tt(ctx, 0, Z32, Z64, 5, -9999, 9999)
    assert hit
    assert value == S.MATE_BOUND + 1 - (5 - 3)
    # 负侧边界对称
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, -S.MATE_BOUND, 3, move)
    assert not S.get_tt(ctx, 0, Z32, Z64, 5, -9999, 9999)[0]
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, -S.MATE_BOUND - 1, 3, move)
    hit, value, _ = S.get_tt(ctx, 0, Z32, Z64, 5, -9999, 9999)
    assert hit
    assert value == -S.MATE_BOUND - 1 + (5 - 3)


def test_alpha_beta_bounds():
    move = C.pack_move(2, 3)
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_BETA, 500, 4, move)
    assert S.get_tt(ctx, 0, Z32, Z64, 4, 0, 500)[0]  # value >= beta
    assert not S.get_tt(ctx, 0, Z32, Z64, 4, 0, 501)[0]

    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_ALPHA, 500, 4, move)
    assert S.get_tt(ctx, 0, Z32, Z64, 4, 500, 9999)[0]  # value <= alpha
    assert not S.get_tt(ctx, 0, Z32, Z64, 4, 499, 9999)[0]


def test_longcheck_score_range_not_stored():
    move = C.pack_move(2, 3)
    slot = slot_of(Z32)
    for value in (8000, 8500, 9000, -8000, -8500, -9000):
        ctx = ctx_small()
        S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, value, 5, move)
        assert not ctx.tt_exists[0, S.SLOT_STEP, slot]
        assert not ctx.tt_exists[0, S.SLOT_STRAIGHT, slot]
        assert not S.get_tt(ctx, 0, Z32, Z64, 5, -9999, 9999)[0]
    # 区间外正常入表
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 7999, 5, move)
    assert ctx.tt_exists[0, S.SLOT_STEP, slot]
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, -9001, 5, move)
    assert ctx.tt_exists[0, S.SLOT_STEP, slot]


# --------------------------------------------------------------------------
# STEP / STRAIGHT 槽语义
# --------------------------------------------------------------------------


def test_step_slot_rejects_shallower_and_keeps_straight_new():
    move1 = C.pack_move(0, 1)
    move2 = C.pack_move(3, 4)
    slot = slot_of(Z32)
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 700, 7, move1)
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 500, 5, move2)
    # STEP 保留更深条目
    assert ctx.tt_value[0, S.SLOT_STEP, slot] == 700
    assert ctx.tt_depth[0, S.SLOT_STEP, slot] == 7
    assert ctx.tt_move[0, S.SLOT_STEP, slot] == move1
    # STRAIGHT 仍写入新条目（Java setTranZobristOverride 的 else 分支）
    assert ctx.tt_value[0, S.SLOT_STRAIGHT, slot] == 500
    assert ctx.tt_depth[0, S.SLOT_STRAIGHT, slot] == 5
    assert ctx.tt_move[0, S.SLOT_STRAIGHT, slot] == move2
    # 读取命中 STEP 的 700
    hit, value, got_move = S.get_tt(ctx, 0, Z32, Z64, 7, -9999, 9999)
    assert hit
    assert value == 700
    assert got_move == move1


def test_step_slot_kicks_old_entry_to_straight():
    move1 = C.pack_move(0, 1)
    move2 = C.pack_move(3, 4)
    slot = slot_of(Z32)
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 500, 5, move1)
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 700, 7, move2)
    assert ctx.tt_value[0, S.SLOT_STEP, slot] == 700
    assert ctx.tt_depth[0, S.SLOT_STEP, slot] == 7
    assert ctx.tt_move[0, S.SLOT_STEP, slot] == move2
    # 旧条目（depth=5）被踢到 STRAIGHT
    assert ctx.tt_value[0, S.SLOT_STRAIGHT, slot] == 500
    assert ctx.tt_depth[0, S.SLOT_STRAIGHT, slot] == 5
    assert ctx.tt_move[0, S.SLOT_STRAIGHT, slot] == move1


def test_step_slot_equal_depth_replaces():
    move1 = C.pack_move(0, 1)
    move2 = C.pack_move(3, 4)
    slot = slot_of(Z32)
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 500, 5, move1)
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_ALPHA, 600, 5, move2)
    # 深度相等 → 不算"更深"，踢出旧条目
    assert ctx.tt_value[0, S.SLOT_STEP, slot] == 600
    assert ctx.tt_value[0, S.SLOT_STRAIGHT, slot] == 500


def test_straight_keeps_old_move_when_new_move_is_zero():
    move1 = C.pack_move(0, 1)
    slot = slot_of(Z32)
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 700, 7, move1)
    # depth=5 < 7 → STEP 放弃；STRAIGHT 被写但 move=0 保留旧 moveNode
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_ALPHA, 500, 5, 0)
    assert ctx.tt_value[0, S.SLOT_STRAIGHT, slot] == 500
    assert ctx.tt_move[0, S.SLOT_STRAIGHT, slot] == move1
    assert ctx.tt_value[0, S.SLOT_STEP, slot] == 700


def test_get_prefers_straight_move_when_no_hit():
    move1 = C.pack_move(0, 1)
    move2 = C.pack_move(3, 4)
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 500, 5, move1)
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 700, 7, move2)
    # 查询 depth=9：两槽都太浅 → 不命中；move 取 STRAIGHT（hi2）、
    # value 因 STEP.depth(7) < STRAIGHT.depth(5) 为假而保持 STEP 的 value
    hit, value, got_move = S.get_tt(ctx, 0, Z32, Z64, 9, -9999, 9999)
    assert not hit
    assert got_move == move1
    assert value == 700


def test_get_uses_straight_value_when_step_missing():
    move1 = C.pack_move(0, 1)
    move2 = C.pack_move(3, 4)
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 500, 5, move1)
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 700, 7, move2)
    S.clean_tt(ctx)
    hit, value, got_move = S.get_tt(ctx, 0, Z32, Z64, 9, -9999, 9999)
    assert not hit
    assert got_move == move1
    assert value == 500  # hi == null → value 取 STRAIGHT


def test_get_uses_straight_value_when_straight_deeper():
    move1 = C.pack_move(0, 1)
    move2 = C.pack_move(3, 4)
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 700, 7, move2)
    S.clean_tt(ctx)
    # clean 后写入 shallow：旧条目（depth=7）被踢到 STRAIGHT，STEP 变 shallow
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 500, 5, move1)
    hit, value, got_move = S.get_tt(ctx, 0, Z32, Z64, 9, -9999, 9999)
    assert not hit
    assert got_move == move2
    assert value == 700  # STEP.depth(5) < STRAIGHT.depth(7) → 取 STRAIGHT


def test_get_no_entry_returns_zero_move():
    ctx = ctx_small()
    hit, value, got_move = S.get_tt(ctx, 0, 7, 99, 5, -9999, 9999)
    assert not hit
    assert value == 0
    assert got_move == 0


# --------------------------------------------------------------------------
# 槽位边界与 clean
# --------------------------------------------------------------------------


def test_slot_boundary_no_overflow():
    n = 1 << 8
    z32 = n - 1  # slot == N-1（Java 数组长度缺陷处）
    move = C.pack_move(8, 7)
    z64 = 0x0F0E0D0C0B0A0908
    ctx = S.new_context(hash_size=n)
    S.set_tt(ctx, 0, z32, z64, S.HASH_PV, 42, 4, move)
    assert ctx.tt_value[0, S.SLOT_STEP, n - 1] == 42
    hit, value, got_move = S.get_tt(ctx, 0, z32, z64, 4, -9999, 9999)
    assert hit and value == 42 and got_move == move
    # 掩码等价：z32 + N 落在同一槽
    assert S.get_tt(ctx, 0, z32 + n, z64, 4, -9999, 9999)[0]
    # z32 恰好为 N 的倍数也落在 0 号槽
    ctx2 = S.new_context(hash_size=n)
    S.set_tt(ctx2, 0, 0, z64, S.HASH_PV, 7, 2, move)
    assert S.get_tt(ctx2, 0, n << 3, z64, 2, -9999, 9999)[0]


def test_clean_tt_invalidates_step_only():
    move1 = C.pack_move(0, 1)
    move2 = C.pack_move(3, 4)
    slot = slot_of(Z32)
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 700, 7, move1)
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 500, 5, move2)
    S.set_tt(ctx, 1, Z32, Z64, S.HASH_PV, 300, 6, move1)
    assert ctx.tt_exists[0, S.SLOT_STEP, slot]
    assert ctx.tt_exists[1, S.SLOT_STEP, slot]
    S.clean_tt(ctx)
    assert not ctx.tt_exists[0, S.SLOT_STEP, slot]
    assert not ctx.tt_exists[1, S.SLOT_STEP, slot]
    # STRAIGHT 槽不受影响：读 depth=5 命中 depth=5 的新条目 500
    hit, value, got_move = S.get_tt(ctx, 0, Z32, Z64, 5, -9999, 9999)
    assert hit and value == 500 and got_move == move2


def test_set_after_clean_kicks_stale_entry():
    move1 = C.pack_move(0, 1)
    move2 = C.pack_move(3, 4)
    slot = slot_of(Z32)
    ctx = ctx_small()
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 700, 7, move1)
    S.clean_tt(ctx)
    S.set_tt(ctx, 0, Z32, Z64, S.HASH_PV, 500, 5, move2)
    # 失效的旧条目被踢到 STRAIGHT，STEP 写入新条目
    assert ctx.tt_value[0, S.SLOT_STEP, slot] == 500
    assert ctx.tt_value[0, S.SLOT_STRAIGHT, slot] == 700
    assert ctx.tt_depth[0, S.SLOT_STRAIGHT, slot] == 7
    assert ctx.tt_exists[0, S.SLOT_STEP, slot]


def test_set_root_tt_writes_step_key_and_move_only():
    move = C.pack_move(4, 5)
    slot = slot_of(Z32)
    ctx = ctx_small()
    S.set_root_tt(ctx, 0, Z32, Z64, move)
    assert ctx.tt_key[0, S.SLOT_STEP, slot] == Z64
    assert ctx.tt_move[0, S.SLOT_STEP, slot] == move
    # 其余字段保持默认（Java 只覆盖 checkSum/moveNode）
    assert ctx.tt_depth[0, S.SLOT_STEP, slot] == 0
    assert ctx.tt_type[0, S.SLOT_STEP, slot] == 0
    assert ctx.tt_value[0, S.SLOT_STEP, slot] == 0
    assert ctx.tt_exists[0, S.SLOT_STEP, slot]
    assert not ctx.tt_exists[0, S.SLOT_STRAIGHT, slot]
    # entry_type=0 不是有效边界：不命中，但 move 仍返回（tranGodMoveNode 语义）
    hit, value, got_move = S.get_tt(ctx, 0, Z32, Z64, 0, -9999, 9999)
    assert not hit
    assert value == 0
    assert got_move == move


# --------------------------------------------------------------------------
# killer 与 history
# --------------------------------------------------------------------------


def test_killer_rotation():
    ctx = ctx_small()
    S.update_killer(ctx, 3, 111)
    assert ctx.killer[3, 0] == 111
    assert ctx.killer[3, 1] == 0
    S.update_killer(ctx, 3, 222)
    assert ctx.killer[3, 0] == 222
    assert ctx.killer[3, 1] == 111
    assert not ctx.killer[4].any()


def test_history_bonus_formula_and_kind_row():
    ctx = ctx_small()
    assert C.PIECE_KINDS[43] == C.SOLDIER  # 红兵 → 基础类型 1
    S.history_bonus(ctx, 43, 10, 2)
    assert ctx.history[C.SOLDIER, 10] == 2 << 2
    S.history_bonus(ctx, 27, 10, 0)  # 黑卒共享同一行
    assert ctx.history[C.SOLDIER, 10] == (2 << 2) + (2 << 0)
    assert ctx.history[C.CHARIOT, 10] == 0


def test_history_bonus_java_int_shift_overflow():
    # Java int 移位环绕：2<<30 == INT_MIN，2<<31 == 0（移位量取低 5 位）
    ctx = ctx_small()
    S.history_bonus(ctx, 33, 0, 30)
    assert ctx.history[C.CHARIOT, 0] == np.iinfo(np.int32).min
    S.history_bonus(ctx, 33, 1, 31)
    assert ctx.history[C.CHARIOT, 1] == 0
    S.history_bonus(ctx, 33, 2, 32)
    assert ctx.history[C.CHARIOT, 2] == 2
    # 加分加法同样按 int32 环绕
    ctx.history[C.CHARIOT, 3] = np.iinfo(np.int32).max
    S.history_bonus(ctx, 33, 3, 1)
    assert ctx.history[C.CHARIOT, 3] == np.iinfo(np.int32).min + 3


def test_history_score_reads_kind_row():
    ctx = ctx_small()
    S.history_bonus(ctx, 33, 45, 3)  # 红车
    assert S.history_score(ctx, 33, 45) == 2 << 3
    assert S.history_score(ctx, 34, 45) == 2 << 3  # 红方两车同基础类型行
    assert S.history_score(ctx, 17, 45) == 2 << 3  # 黑车共享同一行
    assert S.history_score(ctx, 35, 45) == 0       # 红马不同行
    assert S.history_score(ctx, 33, 46) == 0       # 目标格区分


def test_history_decay_truncates_toward_zero():
    ctx = ctx_small()
    ctx.history[0, 0] = -1024
    ctx.history[0, 1] = -1025
    ctx.history[0, 2] = -511
    ctx.history[0, 3] = 1025
    ctx.history[0, 4] = 511
    ctx.history[1, 5] = -1
    S.history_decay(ctx)
    assert ctx.history[0, 0] == -2
    assert ctx.history[0, 1] == -2  # Java int 除法向零：-1025/512 = -2
    assert ctx.history[0, 2] == 0   # numpy // 会给 -1，必须与 Java 一致
    assert ctx.history[0, 3] == 2
    assert ctx.history[0, 4] == 0
    assert ctx.history[1, 5] == 0
