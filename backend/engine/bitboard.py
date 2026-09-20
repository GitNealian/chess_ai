"""位棋盘原语：90 个 site 打包为两个 int64。

打包约定：site 0..63 在 lo（bit = site），site 64..89 在 hi（bit = site - 64）。

Java 参考实现 BitBoard.java 用 4 个 int：Low(site 0..26)、Mid1(27..53)、
Mid2(54..80)、Hi(81..89)。腿位折叠校验和依赖这套 4 字布局，`_words` 负责
从 (lo, hi) 重建这 4 个字。
"""

import numpy as np
from numba import njit


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
    """返回单个 site 的 (lo, hi) 掩码。"""
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
    """把 (lo, hi) 重建为 Java 的 4×32 位字 (Low, Mid1, Mid2, Hi)。"""
    low = lo & 0x7FFFFFF
    mid1 = (lo >> 27) & 0x7FFFFFF
    mid2 = ((lo >> 54) & 0x3FF) | ((hi & 0x1FFFF) << 10)
    him = (hi >> 17) & 0x1FF
    return low, mid1, mid2, him


@njit(cache=True)
def check_sum_knight(lo, hi):
    low, mid1, mid2, him = _words(lo, hi)
    t = low ^ mid1 ^ mid2 ^ him
    return (t & 0x7F) + ((t >> 6) & 0x7F) + ((t >> 13) & 0x7F) + ((t >> 19) & 0x7F)


@njit(cache=True)
def check_sum_elephant(lo, hi):
    low, mid1, mid2, him = _words(lo, hi)
    t = low ^ mid1 ^ mid2 ^ him
    return (t & 0x7F) + ((t >> 7) & 0x7F) + ((t >> 14) & 0x7F) + ((t >> 21) & 0x7F)


def iter_sites(lo, hi):
    """按 site 升序迭代置位（普通 Python 生成器，供测试与调试）。"""
    lo = int(lo) & 0xFFFFFFFFFFFFFFFF
    hi = int(hi) & 0xFFFFFFFFFFFFFFFF
    while lo:
        bit = lo & -lo
        yield bit.bit_length() - 1
        lo ^= bit
    while hi:
        bit = hi & -hi
        yield 64 + bit.bit_length() - 1
        hi ^= bit
