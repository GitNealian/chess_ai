"""车炮行列预生成表测试：攻击/平移/压制/重炮/机动性。

参考实现（不调用被测生成逻辑）：把行/列占据掩码解码为该行/列的真实占位 site
集合，再从棋子位置出发按两个方向扫描，独立复刻 Java ChessInitialize
initChariotGunVariedMove（L343-417）与 initGunFackEatMove（L770-826）的规则。

位序约定（重点）：
- 行表第二维是 boardBitRow：bit k ↔ 列 8-k，棋子自身位 = 1<<(8-col)；
- 列表第二维是 boardBitCol：bit k ↔ 行 9-k，棋子自身位 = 1<<(9-row)；
- 掩码不包含棋子自身位时，Java 不写任何条目（结果为空掩码）。

Java 语义与直接扫描的等价性已由外部脚本全量对拍验证（691200/691200）。
"""

import os
import random

import numpy as np
import pytest

from engine import tables as T


def row_of(site): return site // 9
def col_of(site): return site % 9
def site_of(row, col): return row * 9 + col


ROW_MASK_COUNT = 512
COL_MASK_COUNT = 1024
MODES = ("chariot", "move", "gun", "fake", "more")

ROW_TABLES = {
    "chariot": (T.CHARIOT_ATTACK_ROW_LO, T.CHARIOT_ATTACK_ROW_HI),
    "move": (T.MOVE_CHARIOT_GUN_ROW_LO, T.MOVE_CHARIOT_GUN_ROW_HI),
    "gun": (T.GUN_ATTACK_ROW_LO, T.GUN_ATTACK_ROW_HI),
    "fake": (T.GUN_FAKE_ATTACK_ROW_LO, T.GUN_FAKE_ATTACK_ROW_HI),
    "more": (T.GUN_MORE_REST_ATTACK_ROW_LO, T.GUN_MORE_REST_ATTACK_ROW_HI),
}
COL_TABLES = {
    "chariot": (T.CHARIOT_ATTACK_COL_LO, T.CHARIOT_ATTACK_COL_HI),
    "move": (T.MOVE_CHARIOT_GUN_COL_LO, T.MOVE_CHARIOT_GUN_COL_HI),
    "gun": (T.GUN_ATTACK_COL_LO, T.GUN_ATTACK_COL_HI),
    "fake": (T.GUN_FAKE_ATTACK_COL_LO, T.GUN_FAKE_ATTACK_COL_HI),
    "more": (T.GUN_MORE_REST_ATTACK_COL_LO, T.GUN_MORE_REST_ATTACK_COL_HI),
}

NEW_TABLE_NAMES = (
    "CHARIOT_ATTACK_ROW_LO", "CHARIOT_ATTACK_ROW_HI",
    "MOVE_CHARIOT_GUN_ROW_LO", "MOVE_CHARIOT_GUN_ROW_HI",
    "GUN_ATTACK_ROW_LO", "GUN_ATTACK_ROW_HI",
    "GUN_FAKE_ATTACK_ROW_LO", "GUN_FAKE_ATTACK_ROW_HI",
    "GUN_MORE_REST_ATTACK_ROW_LO", "GUN_MORE_REST_ATTACK_ROW_HI",
    "CHARIOT_GUN_MOBILITY_ROW",
    "CHARIOT_ATTACK_COL_LO", "CHARIOT_ATTACK_COL_HI",
    "MOVE_CHARIOT_GUN_COL_LO", "MOVE_CHARIOT_GUN_COL_HI",
    "GUN_ATTACK_COL_LO", "GUN_ATTACK_COL_HI",
    "GUN_FAKE_ATTACK_COL_LO", "GUN_FAKE_ATTACK_COL_HI",
    "GUN_MORE_REST_ATTACK_COL_LO", "GUN_MORE_REST_ATTACK_COL_HI",
    "CHARIOT_GUN_MOBILITY_COL",
)

FULL_RUN = os.environ.get("ENGINE_TABLES_FULL") == "1"


def make_row_mask(occupied_cols):
    """boardBitRow 掩码：col 0 -> bit8。"""
    return sum(1 << (8 - c) for c in occupied_cols)


def make_col_mask(occupied_rows):
    """boardBitCol 掩码：row 0 -> bit9。"""
    return sum(1 << (9 - r) for r in occupied_rows)


def own_row_bit(site):
    return 1 << (8 - col_of(site))


def own_col_bit(site):
    return 1 << (9 - row_of(site))


def row_mask_to_occ(site, mask):
    """行掩码解码为该行真实占位 site 集合（bit k ↔ 列 8-k）。"""
    row = row_of(site)
    return {site_of(row, 8 - k) for k in range(9) if (mask >> k) & 1}


def col_mask_to_occ(site, mask):
    """列掩码解码为该列真实占位 site 集合（bit k ↔ 行 9-k）。"""
    col = col_of(site)
    return {site_of(9 - k, col) for k in range(10) if (mask >> k) & 1}


def ref_scan(site, occ, drow, dcol, mode):
    """单方向扫描参考实现；occ 为整行/整列占位集合。"""
    r, c = row_of(site), col_of(site)
    out = []
    nr, nc = r + drow, c + dcol
    screen = False
    handicap = 0
    while 0 <= nr < 10 and 0 <= nc < 9:
        s = site_of(nr, nc)
        blocked = s in occ
        if mode == "move":
            if blocked:
                break
            out.append(s)
        elif mode == "chariot":
            if blocked:
                out.append(s)
                break
        elif mode == "gun":
            if blocked:
                if screen:
                    out.append(s)
                    break
                screen = True
        elif mode == "more":
            if blocked:
                handicap += 1
                if handicap == 3:
                    out.append(s)
                    break
        elif mode == "fake":
            if blocked:
                if screen:
                    break
                screen = True
            elif screen:
                out.append(s)
        nr += drow
        nc += dcol
    return out


def ref_results(site, mask, axis):
    """一次解码掩码，返回 {mode: 落点集合}（自身位缺失 → 全部为空）。"""
    if axis == 0:
        if not (mask & own_row_bit(site)):
            return {mode: set() for mode in MODES}
        occ = row_mask_to_occ(site, mask)
        dirs = ((0, -1), (0, 1))
    else:
        if not (mask & own_col_bit(site)):
            return {mode: set() for mode in MODES}
        occ = col_mask_to_occ(site, mask)
        dirs = ((-1, 0), (1, 0))
    out = {}
    for mode in MODES:
        hits = set()
        for drow, dcol in dirs:
            hits.update(ref_scan(site, occ, drow, dcol, mode))
        out[mode] = hits
    return out


def table_result(site, mask, mode, axis):
    lo_arr, hi_arr = (ROW_TABLES if axis == 0 else COL_TABLES)[mode]
    return set(T.unpack_sites(int(lo_arr[site, mask]), int(hi_arr[site, mask])))


# 抽样站点：四角、边界、九宫、河界、中心。
SAMPLE_SITES = (0, 8, 9, 13, 22, 36, 40, 44, 45, 49, 53, 54, 58, 67, 71, 76, 80, 81, 85, 89)


def test_sample_sites_all_masks_row_and_col_match_reference():
    """抽样 20 站点 × 全掩码：5 类行表 + 5 类列表 + mobility 逐项对拍。"""
    for site in SAMPLE_SITES:
        for axis, mask_count in ((0, ROW_MASK_COUNT), (1, COL_MASK_COUNT)):
            for mask in range(mask_count):
                ref = ref_results(site, mask, axis)
                for mode in MODES:
                    got = table_result(site, mask, mode, axis)
                    assert got == ref[mode], (site, axis, mask, mode, ref[mode], got)
                lo_arr, hi_arr = (ROW_TABLES if axis == 0 else COL_TABLES)["move"]
                want_mob = (
                    (int(lo_arr[site, mask]) & 0xFFFFFFFFFFFFFFFF).bit_count()
                    + (int(hi_arr[site, mask]) & 0xFFFFFFFFFFFFFFFF).bit_count()
                )
                mob = T.CHARIOT_GUN_MOBILITY_ROW if axis == 0 else T.CHARIOT_GUN_MOBILITY_COL
                assert int(mob[site, mask]) == want_mob, (site, axis, mask)


def _sampled_masks(rng, site, bit_count, axis, n_random=15):
    own = own_row_bit(site) if axis == 0 else own_col_bit(site)
    others = [1 << k for k in range(bit_count) if (1 << k) != own]
    masks = {0, own}
    for _ in range(n_random):
        masks.add(own | sum(rng.sample(others, rng.randrange(0, 4))))
    for _ in range(n_random):
        masks.add(rng.randrange(1 << bit_count))
    return sorted(masks)


def test_all_sites_sampled_masks_match_reference():
    """全部 90 站点 × 抽样掩码（含自身位/多阻挡/自身位缺失）对拍。"""
    rng = random.Random(20260921)
    for site in range(90):
        for axis, bit_count in ((0, 9), (1, 10)):
            for mask in _sampled_masks(rng, site, bit_count, axis):
                ref = ref_results(site, mask, axis)
                for mode in MODES:
                    got = table_result(site, mask, mode, axis)
                    assert got == ref[mode], (site, axis, mask, mode, ref[mode], got)


def test_mobility_matches_move_popcount_all_sites_all_masks():
    """机动性 = 平移落点数（popcount），全量验证。"""
    unsigned = 0xFFFFFFFFFFFFFFFF
    for site in range(90):
        for mask in range(ROW_MASK_COUNT):
            want = (
                (int(T.MOVE_CHARIOT_GUN_ROW_LO[site, mask]) & unsigned).bit_count()
                + (int(T.MOVE_CHARIOT_GUN_ROW_HI[site, mask]) & unsigned).bit_count()
            )
            assert int(T.CHARIOT_GUN_MOBILITY_ROW[site, mask]) == want, (site, mask)
        for mask in range(COL_MASK_COUNT):
            want = (
                (int(T.MOVE_CHARIOT_GUN_COL_LO[site, mask]) & unsigned).bit_count()
                + (int(T.MOVE_CHARIOT_GUN_COL_HI[site, mask]) & unsigned).bit_count()
            )
            assert int(T.CHARIOT_GUN_MOBILITY_COL[site, mask]) == want, (site, mask)


def test_handcrafted_row_cases():
    """人工手推：空行、单阻挡、双阻挡、炮架、压制、隔两子、自身位缺失。"""
    site = site_of(4, 4)
    other = site_of(4, 3)

    # 自身位缺失 → 五类全空
    for mode in MODES:
        assert table_result(site, 0, mode, 0) == set(), mode

    # 无阻挡（掩码只有自身位）：车吃子无落点；平移占满整行其余 8 格
    own = make_row_mask([4])
    assert table_result(site, own, "chariot", 0) == set()
    assert table_result(site, own, "gun", 0) == set()
    assert table_result(site, own, "fake", 0) == set()
    assert table_result(site, own, "more", 0) == set()
    assert table_result(site, own, "move", 0) == {
        site_of(4, c) for c in range(9) if c != 4
    }

    # 单阻挡（左侧 col2）：车吃掉该子；平移停在 col3；炮无炮架后的目标；压制位为架后空位
    one = make_row_mask([4, 2])
    assert table_result(site, one, "chariot", 0) == {site_of(4, 2)}
    assert table_result(site, one, "move", 0) == {
        site_of(4, 3), site_of(4, 5), site_of(4, 6), site_of(4, 7), site_of(4, 8)
    }
    assert table_result(site, one, "gun", 0) == set()
    assert table_result(site, one, "fake", 0) == {site_of(4, 1), site_of(4, 0)}
    assert table_result(site, one, "more", 0) == set()
    assert other not in table_result(site, one, "chariot", 0)

    # 双阻挡（col2 与 col6）：车两方向各吃一个；平移只剩 col3/col5；压制为两侧架后空位
    two = make_row_mask([4, 2, 6])
    assert table_result(site, two, "chariot", 0) == {site_of(4, 2), site_of(4, 6)}
    assert table_result(site, two, "move", 0) == {site_of(4, 3), site_of(4, 5)}
    assert table_result(site, two, "gun", 0) == set()
    assert table_result(site, two, "fake", 0) == {
        site_of(4, 1), site_of(4, 0), site_of(4, 7), site_of(4, 8)
    }
    assert table_result(site, two, "more", 0) == set()

    # 炮隔一子吃子：炮架 col2、目标 col0
    gun_eat = make_row_mask([4, 2, 0])
    assert table_result(site, gun_eat, "gun", 0) == {site_of(4, 0)}
    assert table_result(site, gun_eat, "fake", 0) == {site_of(4, 1)}

    # 隔两子：col2/col1 为前两子，col0 为第三个阻挡
    more = make_row_mask([4, 2, 1, 0])
    assert table_result(site, more, "more", 0) == {site_of(4, 0)}
    assert table_result(site, more, "gun", 0) == {site_of(4, 1)}

    # 双炮架：隔两子右侧命中（col6/col7 为架、col8 为目标）
    more_right = make_row_mask([4, 6, 7, 8])
    assert table_result(site, more_right, "more", 0) == {site_of(4, 8)}


def test_handcrafted_col_cases():
    """人工手推：空列、单/双阻挡、炮架列、自身位缺失。"""
    site = site_of(4, 4)

    # 自身位缺失
    for mode in MODES:
        assert table_result(site, 0, mode, 1) == set(), mode

    # 无阻挡：车吃子空，平移占满整列其余 9 格
    own = make_col_mask([4])
    assert table_result(site, own, "chariot", 1) == set()
    assert table_result(site, own, "move", 1) == {
        site_of(r, 4) for r in range(10) if r != 4
    }

    # 双阻挡（row1 与 row7）：车吃子两个；平移中间空位；炮无目标
    two = make_col_mask([4, 1, 7])
    assert table_result(site, two, "chariot", 1) == {site_of(1, 4), site_of(7, 4)}
    assert table_result(site, two, "move", 1) == {
        site_of(3, 4), site_of(2, 4), site_of(5, 4), site_of(6, 4)
    }
    assert table_result(site, two, "gun", 1) == set()

    # 炮隔一子吃子：炮架 row2、目标 row0（上方）
    gun_eat = make_col_mask([4, 2, 0])
    assert table_result(site, gun_eat, "gun", 1) == {site_of(0, 4)}
    assert table_result(site, gun_eat, "fake", 1) == {site_of(1, 4)}

    # 隔两子：row2/row1 为前两子，row0 为第三个阻挡
    more = make_col_mask([4, 2, 1, 0])
    assert table_result(site, more, "more", 1) == {site_of(0, 4)}
    assert table_result(site, more, "gun", 1) == {site_of(1, 4)}


def test_attack_tables_cover_only_first_blocker():
    """车吃子/炮吃子落点必在掩码占位内；平移/压制落点必在空位内。"""
    for site in SAMPLE_SITES:
        for axis, mask_count in ((0, ROW_MASK_COUNT), (1, COL_MASK_COUNT)):
            for mask in range(0, mask_count, 7):
                occ = row_mask_to_occ(site, mask) if axis == 0 else col_mask_to_occ(site, mask)
                if not occ:
                    continue
                chariot = table_result(site, mask, "chariot", axis)
                assert chariot <= occ, (site, axis, mask)
                move = table_result(site, mask, "move", axis)
                gun = table_result(site, mask, "gun", axis)
                fake = table_result(site, mask, "fake", axis)
                assert move.isdisjoint(occ)
                assert gun <= occ
                assert fake.isdisjoint(occ)


def test_self_bit_required_everywhere():
    """行/列掩码不包含自身位时五类表全空（Java 的 (j & site) > 0 条件）。"""
    for site in SAMPLE_SITES:
        for axis, full_mask in ((0, 0x1FF), (1, 0x3FF)):
            own = 1 << ((8 - col_of(site)) if axis == 0 else (9 - row_of(site)))
            mask = full_mask & ~own
            for mode in MODES:
                assert table_result(site, mask, mode, axis) == set(), (site, axis, mode)


def test_shapes_dtypes_and_pairing():
    for name in NEW_TABLE_NAMES:
        assert name in T.__all__, name
        arr = getattr(T, name)
        assert isinstance(arr, np.ndarray), name
        assert not arr.flags.writeable, name
    for mode in MODES:
        for suffix, mask_count in (("ROW", ROW_MASK_COUNT), ("COL", COL_MASK_COUNT)):
            base = ROW_TABLES if suffix == "ROW" else COL_TABLES
            lo, hi = base[mode]
            assert lo.shape == (90, mask_count) and hi.shape == (90, mask_count)
            assert lo.dtype == np.int64 and hi.dtype == np.int64
    assert T.CHARIOT_GUN_MOBILITY_ROW.shape == (90, ROW_MASK_COUNT)
    assert T.CHARIOT_GUN_MOBILITY_COL.shape == (90, COL_MASK_COUNT)
    assert T.CHARIOT_GUN_MOBILITY_ROW.dtype == np.int16
    assert T.CHARIOT_GUN_MOBILITY_COL.dtype == np.int16
    # 掩码范围外的位不应泄漏到 90 位掩码的无效位（hi 只允许 bit0..25）
    assert int(T.CHARIOT_ATTACK_ROW_HI.max()) < (1 << 26)
    assert int(T.GUN_FAKE_ATTACK_COL_HI.max()) < (1 << 26)


@pytest.mark.skipif(
    not FULL_RUN,
    reason="慢速全量对拍，默认跳过（ENGINE_TABLES_FULL=1 时运行）",
)
def test_full_tables_match_reference():
    for site in range(90):
        for axis, mask_count in ((0, ROW_MASK_COUNT), (1, COL_MASK_COUNT)):
            for mask in range(mask_count):
                ref = ref_results(site, mask, axis)
                for mode in MODES:
                    got = table_result(site, mask, mode, axis)
                    assert got == ref[mode], (site, axis, mask, mode)
