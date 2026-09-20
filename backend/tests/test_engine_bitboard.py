import random

import numpy as np
import pytest

from engine import bitboard as bb


def test_site_bit_roundtrip():
    for site in range(90):
        lo, hi = bb.site_mask(site)
        assert bb.has_site(lo, hi, site)
        for other in (0, 1, 63, 64, 89):
            if other != site:
                assert not bb.has_site(lo, hi, other)


def test_site_mask_bounds():
    with pytest.raises(AssertionError):
        bb.site_mask(-1)
    with pytest.raises(AssertionError):
        bb.site_mask(90)


def test_has_site_out_of_range_is_false():
    lo, hi = bb.site_mask(45)
    assert bb.has_site(lo, hi, -1) is False
    assert bb.has_site(lo, hi, 90) is False


def test_word_reconstruction():
    # 每个站点掩码在 4 字重建下应落在正确字上
    assert bb._words(*bb.site_mask(0))[0] == 1
    assert bb._words(*bb.site_mask(26))[0] == 1 << 26
    assert bb._words(*bb.site_mask(27))[1] == 1
    assert bb._words(*bb.site_mask(53))[1] == 1 << 26
    assert bb._words(*bb.site_mask(54))[2] == 1
    assert bb._words(*bb.site_mask(80))[2] == 1 << 26
    assert bb._words(*bb.site_mask(81))[3] == 1
    assert bb._words(*bb.site_mask(89))[3] == 1 << 8


def test_lowest_site_order():
    lo = np.int64((1 << 3) | (1 << 40))
    hi = np.int64((1 << 0) | (1 << 25))
    assert bb.lowest_site(lo, hi) == 3
    assert bb.lowest_site(np.int64(0), hi) == 64
    # numpy 2.x 不接受 np.int64(1 << 63) 直接转换，使用等位模式负数
    assert bb.lowest_site(np.int64(-(1 << 63)), np.int64(0)) == 63
    assert bb.lowest_site(np.int64(0), np.int64(0)) == -1


def test_pop_lowest():
    lo = np.int64((1 << 3) | (1 << 40))
    hi = np.int64(1 << 25)
    lo2, hi2, site = bb.pop_lowest(lo, hi)
    assert site == 3
    assert not bb.has_site(lo2, hi2, 3)
    assert bb.has_site(lo2, hi2, 40) and bb.has_site(lo2, hi2, 89)


def test_pop_lowest_empty():
    lo, hi, site = bb.pop_lowest(np.int64(0), np.int64(0))
    assert site == -1
    assert lo == 0 and hi == 0


def test_popcount_and_empty():
    lo = np.int64((1 << 1) | (1 << 2)) | np.int64(-(1 << 63))
    hi = np.int64(1 << 5)
    assert bb.count(lo, hi) == 4
    assert bb.empty(0, 0)
    assert not bb.empty(lo, 0)


def test_complement_full_board():
    assert bb.count(*bb.complement(0, 0)) == 90
    for site in (0, 26, 27, 53, 54, 80, 81, 89):
        slo, shi = bb.site_mask(site)
        clo, chi = bb.complement(slo, shi)
        assert bb.count(clo, chi) == 89
        assert not bb.has_site(clo, chi, site)
    lo, hi = bb.mask_from_sites(np.array([3, 40, 89], dtype=np.int32))
    clo, chi = bb.complement(lo, hi)
    assert bb.count(clo, chi) == 87
    rlo, rhi = bb.complement(clo, chi)
    assert rlo == lo and rhi == hi


def test_mask_from_sites():
    sites = np.array([0, 40, 64, 89, -1, 90], dtype=np.int32)
    lo, hi = bb.mask_from_sites(sites)
    assert bb.count(lo, hi) == 4
    assert bb.has_site(lo, hi, 0)
    assert bb.has_site(lo, hi, 40)
    assert bb.has_site(lo, hi, 64)
    assert bb.has_site(lo, hi, 89)
    empty_lo, empty_hi = bb.mask_from_sites(np.array([], dtype=np.int32))
    assert bb.empty(empty_lo, empty_hi)


def test_check_sum_matches_java_words():
    for site in range(90):
        lo, hi = bb.site_mask(site)
        low, mid1, mid2, him = bb._words(lo, hi)
        t = low ^ mid1 ^ mid2 ^ him
        expected_knight = (t & 0x7F) + ((t >> 7) & 0x7F) + ((t >> 14) & 0x7F) + ((t >> 21) & 0x7F)
        expected_elephant = (t & 0x7F) + ((t >> 6) & 0x7F) + ((t >> 13) & 0x7F) + ((t >> 19) & 0x7F)
        assert bb.check_sum_knight(lo, hi) == expected_knight
        assert bb.check_sum_elephant(lo, hi) == expected_elephant
    # 90 站点单独掩码的最大键应远小于 200（原 Java 表维度）
    keys = [bb.check_sum_knight(*bb.site_mask(s)) for s in range(90)]
    assert max(keys) < 200


def test_iter_sites_ascending():
    lo = np.int64((1 << 10) | (1 << 2))
    hi = np.int64(1 << 1)  # site 65
    assert list(bb.iter_sites(lo, hi)) == [2, 10, 65]
    # 负数 lo（site 63 置位）不得因 Python 补码语义死循环
    assert list(bb.iter_sites(np.int64(-(1 << 63)), np.int64(0))) == [63]


def _java_site_words(site):
    # BitBoard.java L67-77 单站点 4×int 拆分，独立参考实现
    if site < 27:
        return 1 << site, 0, 0, 0
    if site < 54:
        return 0, 1 << (site - 27), 0, 0
    if site < 81:
        return 0, 0, 1 << (site - 54), 0
    return 0, 0, 0, 1 << (site - 81)


def _java_check_sum_elephant(low, mid1, mid2, him):
    # BitBoard.java L83-88：位移 0/6/13/19
    t = low ^ mid1 ^ mid2 ^ him
    return (t & 0x7F) + ((t >> 6) & 0x7F) + ((t >> 13) & 0x7F) + ((t >> 19) & 0x7F)


def _java_check_sum_knight(low, mid1, mid2, him):
    # BitBoard.java L90-94：位移 0/7/14/21
    t = low ^ mid1 ^ mid2 ^ him
    return (t & 0x7F) + ((t >> 7) & 0x7F) + ((t >> 14) & 0x7F) + ((t >> 21) & 0x7F)


def _pack_site(site):
    # 手工构造 (lo, hi) 位模式，不调用 bitboard 任何函数
    if site < 64:
        v = 1 << site
        if v >= 1 << 63:
            v -= 1 << 64
        return np.int64(v), np.int64(0)
    return np.int64(0), np.int64(1 << (site - 64))


def test_check_sum_independent_java_reference():
    knight_keys = []
    elephant_keys = []
    for site in range(90):
        ref_knight = _java_check_sum_knight(*_java_site_words(site))
        ref_elephant = _java_check_sum_elephant(*_java_site_words(site))
        lo, hi = _pack_site(site)
        assert bb.check_sum_knight(lo, hi) == ref_knight, site
        assert bb.check_sum_elephant(lo, hi) == ref_elephant, site
        knight_keys.append(ref_knight)
        elephant_keys.append(ref_elephant)
    # Java 语义下 90 个单站点掩码的键值上界（马窗口步长 7 不重叠、象步长 6 重叠）
    assert max(knight_keys) == 64
    assert max(elephant_keys) == 65
    assert max(knight_keys) < 200 and max(elephant_keys) < 200


def _java_words_from_sites(sites):
    # Java assignXor 语义：多站点掩码按 4×int 逐字合并（站点不重复时等价 OR）
    low = mid1 = mid2 = him = 0
    for site in sites:
        w = _java_site_words(site)
        low ^= w[0]
        mid1 ^= w[1]
        mid2 ^= w[2]
        him ^= w[3]
    return low, mid1, mid2, him


def _pack_sites(sites):
    # 手工构造多站点 (lo, hi)，不调用 bitboard 任何函数
    lo = np.int64(0)
    hi = np.int64(0)
    for site in sites:
        slo, shi = _pack_site(site)
        lo |= slo
        hi |= shi
    return lo, hi


def test_check_sum_multi_site_java_reference():
    rng = random.Random(20260921)
    cases = [
        [0, 26, 27, 53, 54, 80, 81, 89],
        [5, 40, 70],
        [63, 64],
    ]
    for _ in range(3):
        cases.append(rng.sample(range(90), rng.randint(2, 40)))
    for sites in cases:
        low, mid1, mid2, him = _java_words_from_sites(sites)
        lo, hi = _pack_sites(sites)
        assert bb.check_sum_knight(lo, hi) == _java_check_sum_knight(low, mid1, mid2, him), sites
        assert bb.check_sum_elephant(lo, hi) == _java_check_sum_elephant(low, mid1, mid2, him), sites
