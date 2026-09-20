"""基础预生成表测试：马/象/士/将/兵、危险区、攻击限制表。

测试内独立实现全部走法/腿位参考规则，不依赖 engine.tables 的私有辅助，
以防护"腿位/目标映射写错"。
Java 参考：ChessInitialize.java、SearchEngine.java。
"""

import itertools

import numpy as np

from engine import bitboard
from engine import constants as C
from engine import tables as T


def row_of(site): return site // 9
def col_of(site): return site % 9
def site_of(row, col): return row * 9 + col


def ref_knight_moves(site):
    """独立参考：返回 [(target, leg), ...]；腿位 = 先走一格的直线邻格。"""
    r, c = row_of(site), col_of(site)
    out = []
    for dr, dc in ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)):
        nr, nc = r + dr, c + dc
        if not (0 <= nr < 10 and 0 <= nc < 9):
            continue
        if abs(dr) == 2:
            lr, lc = r + (1 if dr > 0 else -1), c
        else:
            lr, lc = r, c + (1 if dc > 0 else -1)
        if 0 <= lr < 10 and 0 <= lc < 9:
            out.append((nr * 9 + nc, lr * 9 + lc))
    return out


def ref_elephant_moves(site):
    """独立参考：返回 [(target, eye), ...]；象不过河、眼位在界内。"""
    r, c = row_of(site), col_of(site)
    out = []
    for dr, dc in ((-2, -2), (-2, 2), (2, -2), (2, 2)):
        nr, nc = r + dr, c + dc
        if not (0 <= nr < 10 and 0 <= nc < 9):
            continue
        if (r >= 5) != (nr >= 5):
            continue
        er, ec = r + dr // 2, c + dc // 2
        if 0 <= er < 10 and 0 <= ec < 9:
            out.append((nr * 9 + nc, er * 9 + ec))
    return out


def ref_fold_knight(occupied):
    lo, hi = bitboard.mask_from_sites(occupied)
    return int(bitboard.check_sum_knight(lo, hi))


def ref_fold_elephant(occupied):
    lo, hi = bitboard.mask_from_sites(occupied)
    return int(bitboard.check_sum_elephant(lo, hi))


def ref_limit_table(moves, fold_fn):
    """独立参考：枚举被占据腿位的全部子集（含空集与全集），返回 {key: 可达目标}。"""
    parts = list(dict.fromkeys(part for _, part in moves))
    table = {}
    for size in range(len(parts) + 1):
        for occupied in itertools.combinations(parts, size):
            occupied_set = set(occupied)
            table[fold_fn(occupied)] = {t for t, part in moves if part not in occupied_set}
    return table


KNIGHT_REF_SITES = [
    site_of(0, 0), site_of(0, 8), site_of(2, 0), site_of(4, 4),
    site_of(5, 0), site_of(5, 4), site_of(9, 4),
]
ELEPHANT_REF_SITES = [
    site_of(0, 0), site_of(0, 2), site_of(2, 0), site_of(2, 4), site_of(4, 2),
    site_of(5, 2), site_of(7, 0), site_of(7, 4), site_of(9, 2),
]


def test_knight_targets_match_reference():
    for site in range(90):
        got = sorted(T.unpack_sites(*T.knight_targets(site)))
        assert got == sorted(t for t, _ in ref_knight_moves(site)), site


def test_elephant_targets_match_reference():
    for site in range(90):
        got = sorted(T.unpack_sites(*T.elephant_targets(site)))
        assert got == sorted(t for t, _ in ref_elephant_moves(site)), site


def test_knight_attack_limit_matches_independent_reference():
    for site in KNIGHT_REF_SITES:
        moves = ref_knight_moves(site)
        legs = list(dict.fromkeys(leg for _, leg in moves))
        ref = ref_limit_table(moves, ref_fold_knight)
        assert len(ref) == 2 ** len(legs), site
        keys = T.knight_leg_keys(site)
        assert len(keys) == 2 ** len(legs), site
        assert set(keys) == set(ref), site
        for key in keys:
            got = set(T.unpack_sites(*T.knight_targets_limit(site, key)))
            assert got == ref[key], (site, key)
        # 空腿全开 → 全部目标；全部腿位被占据 → 空
        full = {t for t, _ in moves}
        assert set(T.unpack_sites(*T.knight_targets_limit(site, ref_fold_knight(())))) == full
        assert set(T.unpack_sites(*T.knight_targets_limit(site, ref_fold_knight(legs)))) == set()


def test_elephant_attack_limit_matches_independent_reference():
    for site in ELEPHANT_REF_SITES:
        moves = ref_elephant_moves(site)
        eyes = list(dict.fromkeys(eye for _, eye in moves))
        ref = ref_limit_table(moves, ref_fold_elephant)
        assert len(ref) == 2 ** len(eyes), site
        keys = T.elephant_leg_keys(site)
        assert len(keys) == 2 ** len(eyes), site
        assert set(keys) == set(ref), site
        for key in keys:
            got = set(T.unpack_sites(*T.elephant_targets_limit(site, key)))
            assert got == ref[key], (site, key)
        full = {t for t, _ in moves}
        assert set(T.unpack_sites(*T.elephant_targets_limit(site, ref_fold_elephant(())))) == full
        assert set(T.unpack_sites(*T.elephant_targets_limit(site, ref_fold_elephant(eyes)))) == set()


def test_knight_attack_limit_consistent():
    for site in range(90):
        moves = ref_knight_moves(site)
        full = {t for t, _ in moves}
        keys = T.knight_leg_keys(site)
        assert len(keys) == 2 ** len({leg for _, leg in moves})
        for key in keys:
            assert set(T.unpack_sites(*T.knight_targets_limit(site, key))) <= full


def test_elephant_attack_limit_consistent():
    for site in range(90):
        moves = ref_elephant_moves(site)
        full = {t for t, _ in moves}
        keys = T.elephant_leg_keys(site)
        assert len(keys) == 2 ** len({eye for _, eye in moves})
        for key in keys:
            assert set(T.unpack_sites(*T.elephant_targets_limit(site, key))) <= full


def test_knight_mobility_matches_popcount():
    for site in range(90):
        for key in T.knight_leg_keys(site):
            lo, hi = T.knight_targets_limit(site, key)
            assert int(T.KNIGHT_MOBILITY[site, key]) == int(T.count(lo, hi)), (site, key)


def test_fold_coverage_and_collisions():
    assert T.FOLD_COLLISIONS["knight"] == 0
    for piece, moves_fn in (("knight", ref_knight_moves), ("elephant", ref_elephant_moves)):
        expected = sum(2 ** len({part for _, part in moves_fn(site)}) for site in range(90))
        assert T.FOLD_CHECKED[piece] == expected, piece
    # 象表存在折叠键碰撞（与 Java 同为后写覆盖）：去重键数 = 组合总数 - 碰撞数
    keys = sum(len(set(T.elephant_leg_keys(site))) for site in range(90))
    assert keys == T.FOLD_CHECKED["elephant"] - T.FOLD_COLLISIONS["elephant"]


def test_elephant_stays_on_own_half():
    for site in range(90):
        for dest in T.unpack_sites(*T.elephant_targets(site)):
            dr = row_of(dest)
            if row_of(site) >= 5:
                assert dr >= 5, (site, dest)
            else:
                assert dr <= 4, (site, dest)


def test_guard_and_king_inside_palace():
    for site in range(90):
        for dest in T.unpack_sites(*T.guard_targets(site)):
            r, c = row_of(dest), col_of(dest)
            assert 3 <= c <= 5 and (r <= 2 or r >= 7), (site, dest)
        for dest in T.unpack_sites(*T.king_targets(site)):
            r, c = row_of(dest), col_of(dest)
            assert 3 <= c <= 5 and (r <= 2 or r >= 7), (site, dest)
    # 具体目标数
    assert len(T.unpack_sites(*T.guard_targets(site_of(0, 3)))) == 1     # 黑方九宫角：1 个斜向
    assert len(T.unpack_sites(*T.guard_targets(site_of(1, 4)))) == 4     # 九宫中心：4 个
    assert len(T.unpack_sites(*T.king_targets(site_of(0, 4)))) == 3      # 黑九宫上边中点：3 个
    assert len(T.unpack_sites(*T.king_targets(site_of(4, 4)))) == 0      # 九宫外：0 个
    # 与 Java 硬编码一致：仅九宫内 18 个起点有目标，宫外起点为空（不得从宫外走进宫）
    assert len(T.unpack_sites(*T.king_targets(site_of(0, 2)))) == 0
    assert len(T.unpack_sites(*T.guard_targets(site_of(0, 2)))) == 0
    assert len(T.unpack_sites(*T.guard_targets(site_of(0, 4)))) == 0   # 九宫边中点不是合法士位


def test_soldier_moves_and_king_checked_soldier_sites():
    # 红兵过河（row<=4）可横走
    assert set(T.unpack_sites(*T.soldier_targets(C.RED, site_of(4, 4)))) == {site_of(3, 4), site_of(4, 3), site_of(4, 5)}
    assert set(T.unpack_sites(*T.soldier_targets(C.RED, site_of(5, 4)))) == {site_of(4, 4)}
    # 黑卒过河（row>=5）可横走
    assert set(T.unpack_sites(*T.soldier_targets(C.BLACK, site_of(4, 4)))) == {site_of(5, 4)}
    assert set(T.unpack_sites(*T.soldier_targets(C.BLACK, site_of(5, 4)))) == {site_of(6, 4), site_of(5, 3), site_of(5, 5)}
    # KingCheckedSoldierBitBoards：红方半场站点 → 黑卒攻击位
    assert set(T.unpack_sites(*T.king_checked_soldier_sites(site_of(9, 4)))) == {site_of(8, 4), site_of(9, 3), site_of(9, 5)}
    # 黑方半场中央站点 → 红兵攻击位
    assert set(T.unpack_sites(*T.king_checked_soldier_sites(site_of(4, 4)))) == {site_of(5, 4), site_of(4, 3), site_of(4, 5)}


def test_danger_margin_masks():
    assert set(T.unpack_sites(*T.danger_margin(C.BLACK))) == set(range(0, 27)) | {30, 31, 32}
    # 与 Java SearchEngine.redDangerMarginArray 对齐：row6 的 col3-5（{57,58,59}）+ row7-9
    assert set(T.unpack_sites(*T.danger_margin(C.RED))) == {57, 58, 59} | set(range(63, 90))


def test_mask_site_one_bit_each():
    for site in range(90):
        assert T.unpack_sites(T.MASK_SITE_LO[site], T.MASK_SITE_HI[site]) == [site]


def test_all_tables_readonly():
    names = [name for name in T.__all__ if isinstance(getattr(T, name), np.ndarray)]
    # 25 张基础表 + Task 4 的 22 张车炮行列表
    assert len(names) == 47
    for name in names:
        assert not getattr(T, name).flags.writeable, name
