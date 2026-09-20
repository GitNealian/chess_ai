"""Task 7：评估表提取与中局评估测试。

覆盖：
- eval_tables 形状/ dtype / 只读 / 红黑行镜像 / Java 源码抽查值（硬编码）；
- 初始局面评估对称性、多子差分、镜像 FEN 取反；
- chess_all_move 与 movegen 目标一致性、空盘控制位数；
- 机动性（马/车/将）与分区（comp/trim/dynamic）手工构造用例；
- 炮检测（空头炮/沉底炮/残车）与 rough_evaluate。
"""

import numpy as np

from chess_engine.board import INITIAL_FEN
from engine import bitboard as B
from engine import constants as C
from engine import eval_tables as T
from engine import evaluate as E
from engine import position as P

# 只有双方将帅的基线局面
BARE_KINGS = "4k4/9/9/9/9/9/9/9/9/3K5 w - - 0 1"


def mirror_site(site):
    """红黑/行镜像：site (row, col) ↔ (9-row, col)。"""
    row, col = divmod(site, 9)
    return (9 - row) * 9 + col


def mirror_fen(fen):
    """镜像 FEN：行倒序 + 大小写互换（颜色互换），走子方互换。"""
    parts = fen.split()
    rows = parts[0].split("/")
    flipped = ["".join(ch.swapcase() for ch in row) for row in reversed(rows)]
    side = "b" if parts[1] != "b" else "w"
    return "/".join(flipped) + f" {side} - - 0 1"


def own_mask(st, play):
    return int(st.mask_personal[play, 0]), int(st.mask_personal[play, 1])


# ---------------------------------------------------------------- 表提取校验


def test_eval_tables_shape_dtype_readonly():
    for table in (T.MIDDLE_BLACK, T.MIDDLE_RED, T.END_BLACK, T.END_RED):
        assert table.shape == (7, 90)
        assert table.dtype == np.int32
        assert not table.flags.writeable
    for table in (T.MOBILITY_REWARDS, T.MIN_MOBILITY, T.BASE_SCORES):
        assert table.shape == (48,)
        assert table.dtype == np.int32
        assert not table.flags.writeable
    assert T.ROLE_PARTITION_SITE.shape == (15, 90)
    assert T.ROLE_PARTITION_SITE.dtype == np.int8
    assert not T.ROLE_PARTITION_SITE.flags.writeable
    for table in (T.ATTACK_PARTITION_SCORE, T.DEFENSE_PARTITION_SCORE):
        assert table.shape == (48,)
        assert table.dtype == np.int32
        assert not table.flags.writeable
    for table in (T.ATTACK_DIRECTION, T.DEFENSE_DIRECTION):
        assert table.shape == (2, 3, 2)  # [play][L/R/M][lo/hi]
        assert table.dtype == np.int64
        assert not table.flags.writeable


def test_red_tables_are_row_mirrors_of_black():
    index = np.array([mirror_site(site) for site in range(90)])
    assert np.array_equal(T.MIDDLE_RED, T.MIDDLE_BLACK[:, index])
    assert np.array_equal(T.END_RED, T.END_BLACK[:, index])
    # 逐项复核若干站点
    for role in range(7):
        for site in (0, 1, 4, 13, 40, 81, 85, 89):
            assert int(T.MIDDLE_RED[role, site]) == int(
                T.MIDDLE_BLACK[role, mirror_site(site)]
            )
            assert int(T.END_RED[role, site]) == int(
                T.END_BLACK[role, mirror_site(site)]
            )


def test_middle_tables_match_java_source_samples():
    knight = T.MIDDLE_BLACK[C.KNIGHT - 1]
    assert knight[:10].tolist() == [-60, -36, -20, -20, -20, -20, -20, -36, -60, -20]
    assert int(knight[13]) == -70
    assert int(knight[40]) == 60
    gun = T.MIDDLE_BLACK[C.GUN - 1]
    assert gun[:10].tolist() == [-30, 0, 30, 40, 20, 40, 30, 0, -30, -20]
    assert int(gun[13]) == 40
    chariot = T.MIDDLE_BLACK[C.CHARIOT - 1]
    assert chariot[:10].tolist() == [-60, -10, 0, 20, -10, 20, 0, -10, -60, -10]
    assert int(chariot[13]) == -40
    soldier = T.MIDDLE_BLACK[C.SOLDIER - 1]
    assert soldier[:10].tolist() == [0] * 10
    assert int(soldier[40]) == 35
    assert int(soldier[44]) == 20
    elephant = T.MIDDLE_BLACK[C.ELEPHANT - 1]
    assert elephant[:10].tolist() == [0, 0, 10, 0, 0, 0, 10, 0, 0, 0]
    assert int(elephant[22]) == 30
    assert int(elephant[38]) == 0
    guard = T.MIDDLE_BLACK[C.GUARD - 1]
    assert guard[:10].tolist() == [0] * 10
    assert int(guard[13]) == 25
    assert int(guard[21]) == 10
    king = T.MIDDLE_BLACK[C.KING - 1]
    assert king[:10].tolist() == [0, 0, 0, 10, 20, 10, 0, 0, 0, 0]
    assert int(king[12]) == -45
    assert int(king[13]) == -50
    assert int(king[22]) == -90


def test_end_tables_match_java_source_samples():
    knight = T.END_BLACK[C.KNIGHT - 1]
    assert knight[:10].tolist() == [0] * 10
    assert int(knight[11]) == 30
    assert int(knight[22]) == 45
    gun = T.END_BLACK[C.GUN - 1]
    assert gun[:10].tolist() == [0, 0, 30, 80, 20, 80, 30, 0, 0, 0]
    assert int(gun[13]) == 55
    chariot = T.END_BLACK[C.CHARIOT - 1]
    assert chariot[:10].tolist() == [20, 20, 20, 65, 0, 65, 20, 20, 20, 20]
    assert int(chariot[13]) == 35
    soldier = T.END_BLACK[C.SOLDIER - 1]
    assert int(soldier[40]) == 60
    assert int(soldier[49]) == 120
    elephant = T.END_BLACK[C.ELEPHANT - 1]
    assert int(elephant[2]) == 10
    assert int(elephant[22]) == 30
    assert int(elephant[4]) == 0
    guard = T.END_BLACK[C.GUARD - 1]
    assert int(guard[13]) == 25
    assert int(guard[21]) == 20
    king = T.END_BLACK[C.KING - 1]
    assert king[:10].tolist() == [0, 0, 0, 10, 10, 10, 0, 0, 0, 0]
    assert int(king[12]) == -15
    assert int(king[13]) == -20
    assert int(king[22]) == -50


def test_mobility_parameter_tables_match_source():
    assert int(T.MOBILITY_REWARDS[16]) == 50
    assert int(T.MOBILITY_REWARDS[17]) == int(T.MOBILITY_REWARDS[18]) == 5
    assert int(T.MOBILITY_REWARDS[19]) == int(T.MOBILITY_REWARDS[20]) == 12
    assert int(T.MOBILITY_REWARDS[21]) == int(T.MOBILITY_REWARDS[22]) == 2
    assert int(T.MOBILITY_REWARDS[32]) == 50
    assert int(T.MOBILITY_REWARDS[33]) == int(T.MOBILITY_REWARDS[34]) == 5
    assert int(T.MOBILITY_REWARDS[35]) == int(T.MOBILITY_REWARDS[36]) == 12
    assert int(T.MOBILITY_REWARDS[37]) == int(T.MOBILITY_REWARDS[38]) == 2
    assert (T.MOBILITY_REWARDS[23:32] == 0).all()
    assert (T.MOBILITY_REWARDS[39:48] == 0).all()
    assert int(T.MIN_MOBILITY[16]) == 1
    assert int(T.MIN_MOBILITY[17]) == int(T.MIN_MOBILITY[18]) == 19
    assert int(T.MIN_MOBILITY[19]) == int(T.MIN_MOBILITY[20]) == 8
    assert int(T.MIN_MOBILITY[21]) == int(T.MIN_MOBILITY[22]) == 19
    assert int(T.MIN_MOBILITY[32]) == 1
    assert int(T.MIN_MOBILITY[33]) == 19
    assert int(T.MIN_MOBILITY[35]) == 8
    assert int(T.MIN_MOBILITY[37]) == 19
    assert (T.MIN_MOBILITY[23:32] == 0).all()


def test_base_scores_match_source():
    assert int(T.BASE_SCORES[16]) == 3000
    assert int(T.BASE_SCORES[17]) == 1300
    assert int(T.BASE_SCORES[19]) == 490
    assert int(T.BASE_SCORES[21]) == 610
    assert int(T.BASE_SCORES[23]) == 200
    assert int(T.BASE_SCORES[25]) == 200
    assert int(T.BASE_SCORES[27]) == 100
    assert int(T.BASE_SCORES[32]) == 3000
    assert int(T.BASE_SCORES[43]) == 100
    assert (T.BASE_SCORES[:16] == 0).all()


def test_partition_tables_match_source():
    assert int(T.ATTACK_PARTITION_SCORE[17]) == 4
    assert int(T.ATTACK_PARTITION_SCORE[19]) == 4
    assert int(T.ATTACK_PARTITION_SCORE[21]) == 4
    assert int(T.ATTACK_PARTITION_SCORE[23]) == 3
    assert int(T.ATTACK_PARTITION_SCORE[27]) == 2
    assert int(T.DEFENSE_PARTITION_SCORE[33]) == 4
    assert int(T.DEFENSE_PARTITION_SCORE[41]) == 3
    assert int(T.DEFENSE_PARTITION_SCORE[47]) == 2
    assert (T.ATTACK_PARTITION_SCORE[:16] == 0).all()
    # chessRolePartitionSite：角色 → 90 格分区代号
    assert (T.ROLE_PARTITION_SITE[0] == 0).all()
    assert (T.ROLE_PARTITION_SITE[7] == 0).all()
    assert int(T.ROLE_PARTITION_SITE[6, 0]) == 1
    assert int(T.ROLE_PARTITION_SITE[6, 3]) == 31
    assert int(T.ROLE_PARTITION_SITE[6, 13]) == 33
    assert int(T.ROLE_PARTITION_SITE[6, 40]) == 3
    assert int(T.ROLE_PARTITION_SITE[6, 49]) == 6
    assert int(T.ROLE_PARTITION_SITE[6, 67]) == 66
    assert int(T.ROLE_PARTITION_SITE[6, 84]) == 64
    assert int(T.ROLE_PARTITION_SITE[1, 3]) == 3
    assert int(T.ROLE_PARTITION_SITE[2, 66]) == 64
    assert int(T.ROLE_PARTITION_SITE[8, 3]) == 3
    assert int(T.ROLE_PARTITION_SITE[8, 75]) == 6
    assert int(T.ROLE_PARTITION_SITE[14, 3]) == 0


def test_direction_masks_match_source():
    # 红方进攻方向 = 黑方半场；黑方进攻方向 = 红方半场
    red_left = T.ATTACK_DIRECTION[C.RED, 0]
    assert B.count(int(red_left[0]), int(red_left[1])) == 15  # row0-2 col0-4
    red_right = T.ATTACK_DIRECTION[C.RED, 1]
    assert B.count(int(red_right[0]), int(red_right[1])) == 15  # row0-2 col4-8
    red_mid = T.ATTACK_DIRECTION[C.RED, 2]
    assert B.count(int(red_mid[0]), int(red_mid[1])) == 12  # row0-3 col3-5
    for side in range(3):
        attack = T.ATTACK_DIRECTION[C.BLACK, side]
        defense = T.DEFENSE_DIRECTION[C.RED, side]
        assert np.array_equal(attack, defense)
        attack_red = T.ATTACK_DIRECTION[C.RED, side]
        assert np.array_equal(attack_red, T.DEFENSE_DIRECTION[C.BLACK, side])


# ---------------------------------------------------------------- attach 与 base


def test_attach_score_uses_middle_tables():
    for role in range(1, 15):
        for site in (0, 4, 40, 81, 89):
            want = (
                T.MIDDLE_RED[role - 1, site]
                if role <= 7
                else T.MIDDLE_BLACK[role - 8, site]
            )
            assert int(P.attach_score(role, site)) == int(want)
    assert int(P.attach_score(C.RED_CHARIOT, 81)) == int(
        T.MIDDLE_RED[C.CHARIOT - 1, 81]
    )
    assert int(P.attach_score(C.BLACK_KING, 4)) == int(T.MIDDLE_BLACK[C.KING - 1, 4])


def test_initial_base_score_is_material_plus_attach():
    st = P.load_position(INITIAL_FEN)
    red, black = P.full_base_score(st)
    assert (red, black) == (int(st.base_score[C.RED]), int(st.base_score[C.BLACK]))
    material = sum(
        int(C.PIECE_SCORES[role]) * int(st.remain[role]) for role in range(1, 15)
    )
    attach_total = 0
    for site in range(90):
        piece = int(st.board[site])
        if piece:
            attach_total += int(P.attach_score(int(C.PIECE_ROLES[piece]), site))
    assert red + black == material + attach_total


def test_rough_evaluate_matches_base_score_difference():
    st = P.load_position(INITIAL_FEN)
    assert int(E.rough_evaluate(st, C.RED)) == int(st.base_score[C.RED]) - int(
        st.base_score[C.BLACK]
    )
    moves = P.pseudo_moves(st, C.RED)
    m = int(moves[0])
    P.make_move(st, m)
    assert int(E.rough_evaluate(st, C.BLACK)) == int(st.base_score[C.BLACK]) - int(
        st.base_score[C.RED]
    )


# ---------------------------------------------------------------- 主评估


def test_initial_position_evaluate_near_zero():
    st = P.load_position(INITIAL_FEN)
    red = int(E.evaluate(st, C.RED))
    black = int(E.evaluate(st, C.BLACK))
    assert abs(red) <= 30
    assert red == -black


def test_extra_chariot_scores_positive_for_red():
    base = P.load_position(BARE_KINGS)
    extra = P.load_position("4k4/9/9/9/9/9/9/9/9/R2K5 w - - 0 1")
    delta = int(E.evaluate(extra, C.RED)) - int(E.evaluate(base, C.RED))
    assert delta > 500
    assert int(E.evaluate(extra, C.BLACK)) < -500


def test_extra_knight_scores_negative_for_red():
    base = P.load_position(BARE_KINGS)
    extra = P.load_position("3nk4/9/9/9/9/9/9/9/9/3K5 w - - 0 1")
    delta = int(E.evaluate(extra, C.RED)) - int(E.evaluate(base, C.RED))
    assert delta < -300


def test_mirror_fen_evaluation_negates():
    fen = "3nk4/9/9/9/9/9/9/9/9/R2K5 w - - 0 1"
    st = P.load_position(fen)
    st_m = P.load_position(mirror_fen(fen))
    red = int(E.evaluate(st, C.RED))
    red_m = int(E.evaluate(st_m, C.RED))
    assert abs(red + red_m) <= 100


def test_evaluate_is_deterministic_and_side_symmetric():
    st = P.load_position(INITIAL_FEN)
    assert int(E.evaluate(st, C.RED)) == int(E.evaluate(st, C.RED))
    assert int(E.evaluate(st, C.RED)) == -int(E.evaluate(st, C.BLACK))


# ---------------------------------------------------------------- 控制位/机动性


def test_chess_all_move_matches_movegen_targets():
    st = P.load_position(INITIAL_FEN)
    moves = P.pseudo_moves(st, C.RED)
    for piece in range(33, 48):
        src = int(st.all_chess[piece])
        if src < 0:
            continue
        role = int(C.PIECE_ROLES[piece])
        lo, hi = E.chess_all_move(st, role, src, C.RED)
        reached = set(B.iter_sites(int(lo), int(hi)))
        mine = [m for m in moves if C.move_src(m) == src]
        captures = {C.move_dest(m) for m in mine if P.move_is_capture(st, m)}
        # 吃子目标必然落在控制范围内
        assert captures <= reached, (piece, sorted(captures - reached))
        if role == C.RED_GUN:
            # Java chessAllMove 对炮只合并吃子位 + 压制位（平移位被注释掉）
            continue
        targets = {C.move_dest(m) for m in mine}
        assert targets <= reached, (piece, sorted(targets - reached))


def test_chariot_all_move_on_open_board():
    # 车在 row4/col4：行 8 格 + 列上 4 格（含黑将阻挡格）+ 列下 5 格（含红帅）= 17
    st = P.load_position("4k4/9/9/9/4R4/9/9/9/9/3K5 w - - 0 1")
    lo, hi = E.chess_all_move(st, C.RED_CHARIOT, 40, C.RED)
    assert B.count(int(lo), int(hi)) == 17


def test_chess_mobility_knight_open_and_surrounded():
    st = P.load_position("4k4/9/9/9/4N4/9/9/9/9/3K5 w - - 0 1")
    lo, hi = own_mask(st, C.RED)
    assert int(E.chess_mobility(st, C.RED_KNIGHT, 40, lo, hi)) == 8
    # 四个腿位 31/39/41/49 全被黑卒占据 → 蹩腿，攻击位为空
    st2 = P.load_position("4k4/9/9/4p4/3pNp3/4p4/9/9/9/3K5 w - - 0 1")
    lo2, hi2 = own_mask(st2, C.RED)
    assert int(E.chess_mobility(st2, C.RED_KNIGHT, 40, lo2, hi2)) == 0


def test_chess_mobility_knight_subtracts_own_pieces():
    # 马的目标位 21(row2,col3) 放一个己方车，mobility 减一
    st = P.load_position("4k4/9/3R5/9/4N4/9/9/9/9/3K5 w - - 0 1")
    src = int(st.all_chess[35])
    assert src == 40
    lo, hi = own_mask(st, C.RED)
    assert int(E.chess_mobility(st, C.RED_KNIGHT, 40, lo, hi)) == 7


def test_chess_mobility_chariot_uses_move_table():
    # 平移表只计空格：行 8 + 列上 3（row0 黑将阻挡）+ 列下 5 = 16
    st = P.load_position("4k4/9/9/9/4R4/9/9/9/9/3K5 w - - 0 1")
    lo, hi = own_mask(st, C.RED)
    assert int(E.chess_mobility(st, C.RED_CHARIOT, 40, lo, hi)) == 16


def test_chess_mobility_king_counts_empty_neighbors():
    st = P.load_position("4k4/9/9/9/9/9/9/9/9/3K5 w - - 0 1")
    # 红帅在 84(row9,col3)：九宫内邻格仅 75(row8,col3)、85(row9,col4)，83 在九宫外
    lo, hi = own_mask(st, C.RED)
    assert int(E.chess_mobility(st, C.RED_KING, 84, lo, hi)) == 2


# ---------------------------------------------------------------- 分区


def test_comp_partition_score_cases():
    atk = T.ATTACK_PARTITION_SCORE.copy()
    dfn = T.DEFENSE_PARTITION_SCORE.copy()
    atk[:] = 0
    dfn[:] = 0
    atk[17] = 4
    dfn[17] = 9

    def run(play, site, par):
        assert int(T.ROLE_PARTITION_SITE[6, site]) == par
        part = np.zeros(7, dtype=np.int32)
        E.comp_partition_score(play, site, 17, part, atk, dfn)
        return part.tolist()

    # 红方：1/2/3 走攻击表，31/32/33 展开到多路
    assert run(C.RED, 0, 1) == [0, 4, 0, 0, 0, 0, 0]
    assert run(C.RED, 7, 2) == [0, 0, 4, 0, 0, 0, 0]
    assert run(C.RED, 4, 3) == [0, 0, 0, 4, 0, 0, 0]
    assert run(C.RED, 3, 31) == [0, 4, 0, 4, 0, 0, 0]
    assert run(C.RED, 5, 32) == [0, 0, 4, 4, 0, 0, 0]
    assert run(C.RED, 13, 33) == [0, 4, 4, 4, 0, 0, 0]
    # 红方：4/5/6 走防御表，64/65/66 展开
    assert run(C.RED, 81, 4) == [0, 0, 0, 0, 9, 0, 0]
    assert run(C.RED, 87, 5) == [0, 0, 0, 0, 0, 9, 0]
    assert run(C.RED, 49, 6) == [0, 0, 0, 0, 0, 0, 9]
    assert run(C.RED, 84, 64) == [0, 0, 0, 0, 9, 0, 9]
    assert run(C.RED, 86, 65) == [0, 0, 0, 0, 0, 9, 9]
    assert run(C.RED, 67, 66) == [0, 0, 0, 0, 9, 9, 9]
    # 黑方：1/2/3 走防御表，4/5/6 走攻击表
    assert run(C.BLACK, 0, 1) == [0, 9, 0, 0, 0, 0, 0]
    assert run(C.BLACK, 3, 31) == [0, 9, 0, 9, 0, 0, 0]
    assert run(C.BLACK, 81, 4) == [0, 0, 0, 0, 4, 0, 0]
    assert run(C.BLACK, 67, 66) == [0, 0, 0, 0, 4, 4, 4]


def test_trim_partition_score_mapping():
    part = np.zeros((2, 7), dtype=np.int32)
    for play in (C.RED, C.BLACK):
        for p in range(1, 7):
            part[play, p] = play * 10 + p
    att = np.zeros((2, 3), dtype=np.int32)
    dfn = np.zeros((2, 3), dtype=np.int32)
    E.trim_partition_score(part, att, dfn)
    assert att[C.RED].tolist() == [part[C.RED, 1], part[C.RED, 2], part[C.RED, 3]]
    assert dfn[C.RED].tolist() == [part[C.RED, 4], part[C.RED, 5], part[C.RED, 6]]
    assert att[C.BLACK].tolist() == [
        part[C.BLACK, 4],
        part[C.BLACK, 5],
        part[C.BLACK, 6],
    ]
    assert dfn[C.BLACK].tolist() == [
        part[C.BLACK, 1],
        part[C.BLACK, 2],
        part[C.BLACK, 3],
    ]


def test_dynamic_partition_score_follows_guard_and_elephant_counts():
    # 空盘双方无士象：防御值归 0，攻击表按对方士数调整
    st = P.load_position(BARE_KINGS)
    atk, dfn = E.dynamic_partition_score(st)
    assert int(dfn[39]) == int(dfn[40]) == 0  # 红象 0 → 0
    assert int(dfn[41]) == int(dfn[42]) == 0  # 红士 0 → 0
    assert int(atk[35]) == int(atk[36]) == 5  # 红马用黑士数 0 → 5
    assert int(atk[37]) == int(atk[38]) == 2  # 红炮用黑士数 0 → 2
    assert int(atk[19]) == int(atk[20]) == 5  # 黑马用红士数 0 → 5
    assert int(atk[21]) == int(atk[22]) == 2  # 黑炮用红士数 0 → 2
    # 初始局面：士象各 2 → 防御 3；马炮动态值 4
    st2 = P.load_position(INITIAL_FEN)
    atk2, dfn2 = E.dynamic_partition_score(st2)
    assert int(dfn2[23]) == int(dfn2[24]) == 3
    assert int(dfn2[39]) == int(dfn2[41]) == 3
    assert int(atk2[19]) == int(atk2[21]) == 4
    assert int(atk2[35]) == int(atk2[37]) == 4


# ---------------------------------------------------------------- 炮检测


def test_exposed_cannon_detects_first_blocker_gun():
    st = P.load_position("4k4/9/9/9/4C4/9/9/9/9/3K5 w - - 0 1")
    king = int(st.all_chess[16])
    assert king == 4
    row = int(st.bit_row[king // 9])
    col = int(st.bit_col[king % 9])
    assert int(E.exposed_cannon(st, C.RED, king, row, col)) == 40
    assert int(E.rest_chariot(st, C.RED, king, row, col)) == -1


def test_bottom_cannon_uses_two_rest_table():
    st = P.load_position("4k4/4p4/4p4/9/4C4/9/9/9/9/3K5 w - - 0 1")
    king = int(st.all_chess[16])
    row = int(st.bit_row[king // 9])
    col = int(st.bit_col[king % 9])
    assert int(E.exposed_cannon(st, C.RED, king, row, col)) == -1
    assert int(E.bottom_cannon(st, C.RED, king, row, col)) == 40


def test_rest_chariot_detects_second_blocker_chariot():
    st = P.load_position("4k4/4p4/9/9/4R4/9/9/9/9/3K5 w - - 0 1")
    king = int(st.all_chess[16])
    row = int(st.bit_row[king // 9])
    col = int(st.bit_col[king % 9])
    assert int(E.rest_chariot(st, C.RED, king, row, col)) == 40


# ---------------------------------------------------------------- 主评估分支


def test_evaluate_runs_on_mobility_penalty_position():
    """马被围局面：机动性分支被执行，红方分数显著低于马自由局面。"""
    free = P.load_position("4k4/9/9/9/4N4/9/9/9/9/3K5 w - - 0 1")
    blocked = P.load_position("4k4/9/9/4p4/3pNp3/4p4/9/9/9/3K5 w - - 0 1")
    score_free = int(E.evaluate(free, C.RED))
    score_blocked = int(E.evaluate(blocked, C.RED))
    assert score_blocked < score_free
    # 快捷复核：被围马在评估中确实被识别为 0 机动性
    lo, hi = own_mask(blocked, C.RED)
    assert int(E.chess_mobility(blocked, C.RED_KNIGHT, 40, lo, hi)) == 0


def test_evaluate_handles_missing_guards_bonus():
    """缺士局面（对方有马）应比防守完整局面更有利于进攻方。"""
    full = P.load_position("3nk4/9/9/9/9/9/9/9/9/3K5 w - - 0 1")
    # 红方无士 → 黑马对红方 +60；同时红方无马
    _atk, dfn = E.dynamic_partition_score(full)
    assert int(dfn[41]) == 0
    assert int(E.evaluate(full, C.RED)) < 0


def test_evaluate_king_off_center_reduces_defense_partition():
    """红帅偏到 col3 时：黑方对红方左路防御 -1 → 三路攻防差 ×30，再加位置分差。"""
    center = P.load_position("4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1")  # 帅 85(col4)=+20
    side = P.load_position("4k4/9/9/9/9/9/9/9/9/3K5 w - - 0 1")  # 帅 84(col3)=+10
    # 位置分 -10；黑方三路比较 (0 > -1) 得 +30 → 红方视角 -30；合计 -40
    assert int(E.evaluate(side, C.RED)) - int(E.evaluate(center, C.RED)) == -40
