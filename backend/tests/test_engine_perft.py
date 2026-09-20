"""Task 6：初始局面 perft 校验（njit 递归 + 定长缓冲）。

期望值为公开的中国象棋初始局面 perft 序列
（不实现长将禁手；将帅照面按"不可走成"处理）。

两个等价实现：
- `perft`：`gen_legal_moves_into` 先生成合法着法，再对每个着法递归（参考版）；
- `perft_fast`：对伪着法 make → `in_check` → 递归 → unmake（合并版），
  每个着法只 make/unmake 一次，用于 depth 4 性能；
  两者由 `test_perft_fast_matches_reference` 对拍一致。
"""

import time

import numpy as np
import pytest
from numba import njit

from chess_engine.board import INITIAL_FEN
from engine import constants as C
from engine import movegen as MG
from engine import position as P

EXPECTED = {1: 44, 2: 1920, 3: 79666, 4: 3290240}

_FAST_CACHE = {}


@njit(cache=True)
def _perft(st, depth, play, buffers):
    """buffers[d] 为深度 d 节点的定长着法缓冲，避免热路径分配。"""
    if depth == 0:
        return np.int64(1)
    buf = buffers[depth]
    n = MG.gen_legal_moves_into(st, play, buf)
    total = np.int64(0)
    for i in range(n):
        m = buf[i]
        undo = P.make_move(st, m)
        total += _perft(st, depth - 1, 1 - play, buffers)
        P.unmake_move(st, m, undo)
    return total


def perft(st, depth, play):
    buffers = np.empty((depth + 1, MG.MAX_MOVES), dtype=np.int32)
    return int(_perft(st, depth, play, buffers))


@njit(cache=True)
def _perft_fast(st, depth, play, buffers):
    if depth == 0:
        return np.int64(1)
    buf = buffers[depth]
    n = MG.gen_moves_into(st, play, buf, False)
    total = np.int64(0)
    for i in range(n):
        m = buf[i]
        undo = P.make_move(st, m)
        if not MG.in_check(st, play):
            total += _perft_fast(st, depth - 1, 1 - play, buffers)
        P.unmake_move(st, m, undo)
    return total


def perft_fast(st, depth, play):
    buffers = np.empty((depth + 1, MG.MAX_MOVES), dtype=np.int32)
    return int(_perft_fast(st, depth, play, buffers))


def _fast_result(depth):
    """depth 4 由性能测试先行计算并缓存，避免重复跑最贵的一档。"""
    if depth not in _FAST_CACHE:
        _FAST_CACHE[depth] = perft_fast(P.load_position(INITIAL_FEN), depth, C.RED)
    return _FAST_CACHE[depth]


def test_perft_depth4_performance():
    st = P.load_position(INITIAL_FEN)
    perft_fast(st, 2, C.RED)  # 预热 numba 编译
    start = time.perf_counter()
    _FAST_CACHE[4] = perft_fast(st, 4, C.RED)
    elapsed = time.perf_counter() - start
    assert _FAST_CACHE[4] == EXPECTED[4]
    assert elapsed < 2.0


@pytest.mark.parametrize("depth", [1, 2, 3, 4])
def test_initial_perft(depth):
    assert _fast_result(depth) == EXPECTED[depth]


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_initial_perft_reference(depth):
    st = P.load_position(INITIAL_FEN)
    assert perft(st, depth, C.RED) == EXPECTED[depth]


def test_perft_fast_matches_reference():
    st = P.load_position(INITIAL_FEN)
    assert perft(st, 3, C.RED) == perft_fast(st, 3, C.RED)
