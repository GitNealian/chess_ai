import numpy as np
from numba import njit

_TABLE = np.arange(16, dtype=np.int64)


@njit(cache=True)
def _lookup(i):
    return _TABLE[i] * 2


@njit(cache=True)
def _sum_state(state):
    total = np.int64(0)
    for i in range(state.shape[0]):
        total += state[i]
    return total


@njit(cache=True)
def _check_stop(flag):
    return flag[0] != 0


def test_njit_global_readonly_array():
    assert _lookup(3) == 6


def test_njit_array_mutation_visible():
    st = np.zeros(4, dtype=np.int64)
    assert _sum_state(st) == 0
    st[1] = 5
    assert _sum_state(st) == 5


def test_njit_stop_flag_pattern():
    flag = np.zeros(1, dtype=np.int8)
    flag[0] = 1
    assert _check_stop(flag) is True
