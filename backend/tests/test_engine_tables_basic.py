"""基础预生成表测试：马/象/士/将/兵、危险区、攻击限制表。

Java 参考：ChessInitialize.java、SearchEngine.java。
"""

import numpy as np
import pytest

from engine import constants as C
from engine import tables as T
from engine.tables import _knight_moves_with_legs, _leg_sites


def row_of(site): return site // 9
def col_of(site): return site % 9
def site_of(row, col): return row * 9 + col


def ref_knight_targets(site):
    r, c = row_of(site), col_of(site)
    deltas = [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
    out = []
    for dr, dc in deltas:
        nr, nc = r + dr, c + dc
        if 0 <= nr < 10 and 0 <= nc < 9:
            out.append(site_of(nr, nc))
    return out


def test_knight_targets_match_reference():
    for site in range(90):
        got = sorted(T.unpack_sites(*T.knight_targets(site)))
        assert got == sorted(ref_knight_targets(site)), site


def test_knight_attack_limit_consistent():
    for site in range(90):
        full = set(T.unpack_sites(*T.knight_targets(site)))
        keys = T.knight_leg_keys(site)
        assert len(keys) == 2 ** len(set(_leg_sites(site)))   # 含空集：2^n 种状态
        for key in keys:
            targets = set(T.unpack_sites(*T.knight_targets_limit(site, key)))
            assert targets <= full
    # 具体用例：中央马，仅一条腿被占
    site = site_of(5, 4)
    legs = sorted(set(_leg_sites(site)))
    assert len(legs) == 4
    for leg in legs:
        key = T.fold_knight_key([leg])   # 辅助：单腿占据的键（内部调用 bitboard.check_sum_knight）
        blocked = [m for m in _knight_moves_with_legs(site) if m[1] == leg]
        expected = set(T.unpack_sites(*T.knight_targets(site))) - {m[0] for m in blocked}
        assert set(T.unpack_sites(*T.knight_targets_limit(site, key))) == expected


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


def test_mask_site_and_readonly():
    for site in range(90):
        assert list(T.unpack_sites(T.MASK_SITE_LO[site], T.MASK_SITE_HI[site])) == [site]
    for name in ("KNIGHT_TARGET_LO", "SOLDIER_TARGET_LO", "DANGER_MARGIN_LO"):
        assert not getattr(T, name).flags.writeable
