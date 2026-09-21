"""Task 8：残局评估、动态子力与阶段判定测试。

覆盖：
- `phase_of`：初始中局、只剩将士象兵残局、7 分临界；
- 残局 `evaluate`：双兵互保（SOLDIERS_PROTECTED）、炮/马对缺士表、
  1.7 倍率的 int 截断；
- `dynamic_piece_scores`：满子基准值、少子后马升值/炮贬值、兵随
  兵所属方自己的攻击子数变化；
- State 扩展：`piece_scores`/`phase` 初值、`attach_score` 按阶段选表；
- `prepare`：字段一致性、base_score 用动态子力 + 当前阶段位置表重算；
- `prepare` 后 make/unmake 增量与 `full_base_score` 一致。
"""

import numpy as np

from chess_engine.board import INITIAL_FEN
from engine import analysis as A
from engine import constants as C
from engine import eval_tables as T
from engine import evaluate as E
from engine import position as P

# 只剩将士象兵（红 1 兵 2 仕 1 相，黑 2 士 1 象）→ 残局
END_FEN = "3ak1b2/4a4/9/9/9/9/9/4P4/4A4/3AKB3 w - - 0 1"
# 红兵正前方有黑卒，可用于走子/吃子往返测试
END_CAPTURE_FEN = "3ak4/9/9/9/9/9/4p4/4P4/4A4/3AK4 w - - 0 1"
# 双方各 1 车 1 马 1 炮 → 3+3=6 < 7 → 残局
SIX_FEN = "rnk6/9/1c7/9/9/9/9/1C7/9/RN3K3 w - - 0 1"
# 红方多一门炮 → 4+3=7 → 中局
SEVEN_FEN = "rnk6/9/1c7/9/9/9/9/1C2C4/9/RN3K3 w - - 0 1"

# 互保双兵（row4 col3/col4，攻击位互相覆盖）
PAIR_SOLDIERS_FEN = "4k4/9/9/9/3PP4/9/9/9/9/4K4 w - - 0 1"
# 分离双兵（row4 col3/col6，攻击位不相交）
SPLIT_SOLDIERS_FEN = "4k4/9/9/9/3P2P2/9/9/9/9/4K4 w - - 0 1"

# 红炮一/二门，黑方 0/2 士
GUN_VS_NO_GUARD = "4k4/9/9/9/9/4C4/9/9/9/4K4 w - - 0 1"
GUN_VS_TWO_GUARDS = "3aka3/9/9/9/9/4C4/9/9/9/4K4 w - - 0 1"
TWO_GUNS_VS_TWO_GUARDS = "3aka3/9/9/9/9/2C1C4/9/9/9/4K4 w - - 0 1"

# 红马一匹，黑方 0/1/2 士
KNIGHT_VS_NO_GUARD = "4k4/9/9/9/9/4N4/9/9/9/4K4 w - - 0 1"
KNIGHT_VS_ONE_GUARD = "3ak4/9/9/9/9/4N4/9/9/9/4K4 w - - 0 1"
KNIGHT_VS_TWO_GUARDS = "3aka3/9/9/9/9/4N4/9/9/9/4K4 w - - 0 1"

# 少一个黑车：全场 31 子，黑方攻击子数 10（红方仍 11）
FEWER_FEN = "1nbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

BARE_KINGS = "4k4/9/9/9/9/9/9/9/9/3K5 w - - 0 1"


def load_prepared(fen):
    st = P.load_position(fen)
    A.prepare(st)
    return st


def eval_extra_red(st_a, st_b):
    """红视角评估差，扣除 base_score 差（子力 + 位置分）后的残局项差。"""
    delta = int(E.evaluate(st_a, C.RED)) - int(E.evaluate(st_b, C.RED))
    base = (
        int(st_a.base_score[C.RED])
        - int(st_a.base_score[C.BLACK])
        - int(st_b.base_score[C.RED])
        + int(st_b.base_score[C.BLACK])
    )
    return delta - base


# ---------------------------------------------------------------- 阶段判定


def test_phase_of_initial_is_middle_game():
    st = P.load_position(INITIAL_FEN)
    assert A.phase_of(st) == A.MIDDLE_GAME
    assert A.MIDDLE_GAME == 0 and A.END_GAME == 1


def test_phase_of_guards_elephants_soldiers_only_is_endgame():
    st = P.load_position(END_FEN)
    assert A.phase_of(st) == A.END_GAME
    # 只剩将帅也是残局
    assert A.phase_of(P.load_position(BARE_KINGS)) == A.END_GAME


def test_phase_of_boundary_at_seven_points():
    assert A.phase_of(P.load_position(SIX_FEN)) == A.END_GAME
    assert A.phase_of(P.load_position(SEVEN_FEN)) == A.MIDDLE_GAME


def test_phase_of_counts_soldiers_only_above_three():
    # 双方各 1 车马炮 + 4 兵/卒：兵 >3 记 1 → 4+4=8 → 中局
    four = P.load_position("rn2k4/9/1c7/9/9/9/pppp5/PPPPC4/9/RN2K4 w - - 0 1")
    assert A.phase_of(four) == A.MIDDLE_GAME
    # 双方各 1 车马炮 + 3 兵/卒：兵不记分 → 3+3=6 < 7 → 残局
    three = P.load_position("rn2k4/9/1c7/9/9/9/ppp6/PPPC5/9/RN2K4 w - - 0 1")
    assert A.phase_of(three) == A.END_GAME


# ---------------------------------------------------------------- State 扩展


def test_state_extension_defaults():
    st = P.load_position(INITIAL_FEN)
    assert st.piece_scores.shape == (15,)
    assert st.piece_scores.dtype == np.int32
    assert st.piece_scores.flags.writeable
    assert st.piece_scores is not C.PIECE_SCORES
    assert np.array_equal(st.piece_scores, C.PIECE_SCORES)
    assert st.phase.shape == (1,)
    assert st.phase.dtype == np.int8
    assert int(st.phase[0]) == A.MIDDLE_GAME


def test_attach_score_follows_phase_tables():
    st = P.load_position(END_FEN)
    for role in range(1, 15):
        for site in (0, 4, 39, 40, 81):
            want = (
                T.MIDDLE_RED[role - 1, site]
                if role <= 7
                else T.MIDDLE_BLACK[role - 8, site]
            )
            assert int(P.attach_score(st, role, site)) == int(want)
    st.phase[0] = np.int8(A.END_GAME)
    for role in range(1, 15):
        for site in (0, 4, 39, 40, 81):
            want = (
                T.END_RED[role - 1, site]
                if role <= 7
                else T.END_BLACK[role - 8, site]
            )
            assert int(P.attach_score(st, role, site)) == int(want)


# ---------------------------------------------------------------- 动态子力


def test_dynamic_piece_scores_initial_position():
    st = P.load_position(INITIAL_FEN)
    scores = A.dynamic_piece_scores(st)
    assert scores.shape == (15,)
    assert scores.dtype == np.int32
    # 满子 32：马 490 + 0*6、炮 610 - 0*6
    assert int(scores[C.RED_KNIGHT]) == 490
    assert int(scores[C.BLACK_KNIGHT]) == 490
    assert int(scores[C.RED_GUN]) == 610
    assert int(scores[C.BLACK_GUN]) == 610
    # 双方攻击子数均为 11（车 2 + 马 2 + 炮 2 + 兵 5）→ 兵/卒 100
    assert int(scores[C.RED_SOLDIER]) == 100
    assert int(scores[C.BLACK_SOLDIER]) == 100
    # 只改兵/马/炮三类，其余角色保持静态子力值
    for role in (C.RED_CHARIOT, C.BLACK_CHARIOT, C.RED_GUARD, C.BLACK_GUARD,
                 C.RED_ELEPHANT, C.BLACK_ELEPHANT, C.RED_KING, C.BLACK_KING):
        assert int(scores[role]) == int(C.PIECE_SCORES[role])


def test_dynamic_piece_scores_after_piece_loss():
    st = P.load_position(FEWER_FEN)
    scores = A.dynamic_piece_scores(st)
    # 全场 31 子：马 490 + 6、炮 610 - 6
    assert int(scores[C.RED_KNIGHT]) == 496
    assert int(scores[C.BLACK_KNIGHT]) == 496
    assert int(scores[C.RED_GUN]) == 604
    assert int(scores[C.BLACK_GUN]) == 604
    # Java moveBegin：黑卒用黑方自己的攻击子数（10）→ +8；红兵用红方（11）→ 100
    assert int(scores[C.BLACK_SOLDIER]) == 108
    assert int(scores[C.RED_SOLDIER]) == 100


def test_dynamic_piece_scores_are_side_asymmetric():
    # 黑方少一个马：黑方攻击子数 10 → 黑卒 108，红兵仍 100
    st = P.load_position("r1bakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1")
    scores = A.dynamic_piece_scores(st)
    assert int(scores[C.BLACK_SOLDIER]) == 108
    assert int(scores[C.RED_SOLDIER]) == 100


# ---------------------------------------------------------------- prepare


def test_prepare_sets_phase_scores_and_base_score():
    for fen, phase in (
        (INITIAL_FEN, A.MIDDLE_GAME),
        (END_FEN, A.END_GAME),
        (END_CAPTURE_FEN, A.END_GAME),
    ):
        st = P.load_position(fen)
        A.prepare(st)
        assert int(st.phase[0]) == phase
        assert np.array_equal(st.piece_scores, A.dynamic_piece_scores(st))
        assert (int(st.base_score[C.RED]), int(st.base_score[C.BLACK])) == (
            P.full_base_score(st)
        )


def test_prepare_endgame_base_score_uses_end_tables():
    st = load_prepared(END_FEN)
    expect_red = 0
    expect_black = 0
    for site in range(90):
        piece = int(st.board[site])
        if piece == 0:
            continue
        role = int(C.PIECE_ROLES[piece])
        if piece < C.RED_PIECES_START:
            expect_black += int(st.piece_scores[role]) + int(T.END_BLACK[role - 8, site])
        else:
            expect_red += int(st.piece_scores[role]) + int(T.END_RED[role - 1, site])
    assert int(st.base_score[C.RED]) == expect_red
    assert int(st.base_score[C.BLACK]) == expect_black


def test_prepare_then_make_unmake_roundtrip():
    for fen in (END_FEN, END_CAPTURE_FEN):
        st = load_prepared(fen)
        snapshot = {f: getattr(st, f).copy() for f in st._fields}
        side = int(st.side_to_move[0])
        moves = P.pseudo_moves(st, side)
        assert moves
        saw_capture = False
        for m in moves:
            undo = P.make_move(st, m)
            if int(undo[0]) != 0:
                saw_capture = True
            assert P.full_base_score(st) == (
                int(st.base_score[C.RED]),
                int(st.base_score[C.BLACK]),
            ), m
            P.unmake_move(st, m, undo)
            for f in st._fields:
                assert np.array_equal(getattr(st, f), snapshot[f]), (f, m)
        if fen == END_CAPTURE_FEN:
            assert saw_capture


def test_prepare_then_make_unmake_roundtrip_middle_game():
    st = load_prepared(INITIAL_FEN)
    assert int(st.phase[0]) == A.MIDDLE_GAME
    snapshot = {f: getattr(st, f).copy() for f in st._fields}
    for m in P.pseudo_moves(st, C.RED):
        undo = P.make_move(st, m)
        assert P.full_base_score(st) == (
            int(st.base_score[C.RED]),
            int(st.base_score[C.BLACK]),
        ), m
        P.unmake_move(st, m, undo)
        for f in st._fields:
            assert np.array_equal(getattr(st, f), snapshot[f]), (f, m)


# ---------------------------------------------------------------- 残局评估


def test_endgame_evaluate_matches_explicit_flag():
    st = load_prepared(END_FEN)
    assert int(E.evaluate(st, C.RED)) == int(E.evaluate_endgame(st, C.RED))
    # 中局局面下显式 endgame=True 也可强制走残局分支
    st_mid = P.load_position(INITIAL_FEN)
    assert int(E.evaluate(st_mid, C.RED, True)) == int(
        E.evaluate_endgame(st_mid, C.RED)
    )


def test_endgame_soldiers_protected_pair():
    pair = load_prepared(PAIR_SOLDIERS_FEN)
    split = load_prepared(SPLIT_SOLDIERS_FEN)
    assert int(T.SOLDIERS_PROTECTED[2]) == 150
    assert eval_extra_red(pair, split) == int(T.SOLDIERS_PROTECTED[2]) - int(
        T.SOLDIERS_PROTECTED[0]
    )


def test_endgame_single_soldier_gets_no_protection_bonus():
    # 只剩 1 兵时不触发保护表：与两兵分离局面的差 = 位置/子力差（已扣除 base）
    single = load_prepared("4k4/9/9/9/3P5/9/9/9/9/4K4 w - - 0 1")
    split = load_prepared(SPLIT_SOLDIERS_FEN)
    assert eval_extra_red(single, split) == 0


def test_endgame_gun_opponent_guard_table():
    no_guard = load_prepared(GUN_VS_NO_GUARD)
    two_guards = load_prepared(GUN_VS_TWO_GUARDS)
    assert int(T.GUN_OPPT_NOT_GUARD[0]) == 0
    assert int(T.GUN_OPPT_NOT_GUARD[2]) == 110
    assert eval_extra_red(no_guard, two_guards) == int(
        T.GUN_OPPT_NOT_GUARD[0]
    ) - int(T.GUN_OPPT_NOT_GUARD[2])


def test_endgame_two_guns_truncate_1_7():
    one = load_prepared(GUN_VS_TWO_GUARDS)
    two = load_prepared(TWO_GUNS_VS_TWO_GUARDS)
    truncated = int(T.GUN_OPPT_NOT_GUARD[2] * 1.7)
    assert truncated == 187  # 110 * 1.7 = 187.0，int 截断
    assert eval_extra_red(two, one) == truncated - int(T.GUN_OPPT_NOT_GUARD[2])


def test_endgame_knight_opponent_guard_table():
    no_guard = load_prepared(KNIGHT_VS_NO_GUARD)
    two_guards = load_prepared(KNIGHT_VS_TWO_GUARDS)
    # Java 表 {110,40,0}：对方无士时马方 +110，对方士满时 +0
    assert int(T.KNIGHT_OPPT_NOT_GUARD[0]) == 110
    assert int(T.KNIGHT_OPPT_NOT_GUARD[2]) == 0
    assert eval_extra_red(no_guard, two_guards) == int(
        T.KNIGHT_OPPT_NOT_GUARD[0]
    ) - int(T.KNIGHT_OPPT_NOT_GUARD[2])


def test_endgame_knight_opponent_one_guard():
    one = load_prepared(KNIGHT_VS_ONE_GUARD)
    two = load_prepared(KNIGHT_VS_TWO_GUARDS)
    assert int(T.KNIGHT_OPPT_NOT_GUARD[1]) == 40
    assert eval_extra_red(one, two) == int(T.KNIGHT_OPPT_NOT_GUARD[1]) - int(
        T.KNIGHT_OPPT_NOT_GUARD[2]
    )


def test_endgame_scores_are_side_symmetric():
    st = load_prepared(END_FEN)
    assert int(E.evaluate(st, C.RED)) == -int(E.evaluate(st, C.BLACK))
