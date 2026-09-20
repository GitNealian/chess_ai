"""位棋盘原语：90 个 site 打包为两个 int64。

打包约定：site 0..63 在 lo（bit = site），site 64..89 在 hi（bit = site - 64）。
hi 只有 bit0..25 有效；取 90 位补集必须使用 complement()，不可直接对 hi 取反，
否则会引入 bit26..63 的无效位。

Java 参考实现 BitBoard.java 用 4 个 int：Low(site 0..26)、Mid1(27..53)、
Mid2(54..80)、Hi(81..89)。腿位折叠校验和依赖这套 4 字布局，`_words` 负责
从 (lo, hi) 重建这 4 个字。
"""

import numpy as np
from numba import njit

LO_MASK = (1 << 64) - 1
HI_MASK = (1 << 26) - 1

__all__ = [
    "LO_MASK",
    "HI_MASK",
    "site_mask",
    "mask_from_sites",
    "has_site",
    "empty",
    "count",
    "lowest_site",
    "pop_lowest",
    "complement",
    "check_sum_knight",
    "check_sum_elephant",
    "iter_sites",
]


@njit(cache=True)
def _popcount64(x):
    x = x - ((x >> 1) & 0x5555555555555555)
    x = (x & 0x3333333333333333) + ((x >> 2) & 0x3333333333333333)
    x = (x + (x >> 4)) & 0x0F0F0F0F0F0F0F0F
    return (x * 0x0101010101010101) >> 56


@njit(cache=True)
def _ctz64(x):
    return _popcount64((x & -x) - 1)


@njit(cache=True)
def site_mask(site):
    """返回单个 site 的 (lo, hi) 掩码；site 越界抛 AssertionError。"""
    assert 0 <= site < 90
    if site < 64:
        return np.int64(1) << np.int64(site), np.int64(0)
    return np.int64(0), np.int64(1) << np.int64(site - 64)


def mask_from_sites(sites):
    """从 int32/int64 数组构建掩码，非法 site（<0 或 >=90）忽略。"""
    lo = np.int64(0)
    hi = np.int64(0)
    for site in sites:
        site = int(site)
        if 0 <= site < 64:
            lo |= np.int64(1) << np.int64(site)
        elif 64 <= site < 90:
            hi |= np.int64(1) << np.int64(site - 64)
    return lo, hi


@njit(cache=True)
def has_site(lo, hi, site):
    """site 越界返回 False。"""
    if site < 0 or site >= 90:
        return False
    if site < 64:
        return (lo & (np.int64(1) << np.int64(site))) != 0
    return (hi & (np.int64(1) << np.int64(site - 64))) != 0


@njit(cache=True)
def empty(lo, hi):
    return (lo | hi) == 0


@njit(cache=True)
def count(lo, hi):
    return _popcount64(lo) + _popcount64(hi)


@njit(cache=True)
def complement(lo, hi):
    """返回 90 位补集，hi 只保留有效位 bit0..25。"""
    return (~lo) & LO_MASK, (~hi) & HI_MASK


@njit(cache=True)
def lowest_site(lo, hi):
    """最低置位对应的 site，按 site 升序（lo 低位优先，再 hi 低位）；空掩码返回 -1。"""
    if lo != 0:
        return _ctz64(lo)
    if hi != 0:
        return 64 + _ctz64(hi)
    return -1


@njit(cache=True)
def pop_lowest(lo, hi):
    """取出最低 site 并从掩码中移除，返回 (lo, hi, site)。"""
    site = lowest_site(lo, hi)
    if site < 0:
        return lo, hi, np.int64(-1)
    if site < 64:
        lo = lo & (lo - 1)
    else:
        hi = hi & (hi - 1)
    return lo, hi, site


@njit(cache=True)
def _words(lo, hi):
    """仅供内部折叠与测试使用：把 (lo, hi) 重建为 Java 的 4×32 位字。"""
    low = lo & 0x7FFFFFF
    mid1 = (lo >> 27) & 0x7FFFFFF
    mid2 = ((lo >> 54) & 0x3FF) | ((hi & 0x1FFFF) << 10)
    him = (hi >> 17) & 0x1FF
    return low, mid1, mid2, him


@njit(cache=True)
def check_sum_knight(lo, hi):
    """对应 BitBoard.java:90-94，位移 0/7/14/21。"""
    low, mid1, mid2, him = _words(lo, hi)
    t = low ^ mid1 ^ mid2 ^ him
    return (t & 0x7F) + ((t >> 7) & 0x7F) + ((t >> 14) & 0x7F) + ((t >> 21) & 0x7F)


@njit(cache=True)
def check_sum_elephant(lo, hi):
    """对应 BitBoard.java:83-88，位移 0/6/13/19。"""
    low, mid1, mid2, him = _words(lo, hi)
    t = low ^ mid1 ^ mid2 ^ him
    return (t & 0x7F) + ((t >> 6) & 0x7F) + ((t >> 13) & 0x7F) + ((t >> 19) & 0x7F)


def iter_sites(lo, hi):
    """按 site 升序迭代置位（普通 Python 生成器，供测试与调试）。"""
    lo = int(lo) & LO_MASK
    hi = int(hi) & LO_MASK
    while lo:
        bit = lo & -lo
        yield bit.bit_length() - 1
        lo ^= bit
    while hi:
        bit = hi & -hi
        yield 64 + bit.bit_length() - 1
        hi ^= bit
