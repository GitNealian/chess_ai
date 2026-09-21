"""Task 12：对外分析接口（渐进加深生成器）的测试。

覆盖：
- `analyze` 逐层产出且 depth 单调递增、只在 `>= start_depth` 时产出；
- 时间上限与 stop 停旗语义（中断层丢弃、已完成层照常产出）；
- 红方视角换算、mate 步数上报、PV 为独立拷贝；
- `warmup` 幂等且第二次近似零开销。

首次运行含 numba JIT 编译（约 20-30s），后续用例复用已编译代码。
"""

import time

import numpy as np
import pytest

from engine import constants as C

INITIAL = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

# 红方一步杀（现有 `test_engine_search_main.py` 的穷举用例：3R5/5k1N1... 期望 1 ply）
MATE_IN_ONE = "3R5/5k1N1/9/9/9/9/9/9/9/4K1R2 w - - 0 1"


def test_progressive_depths_increase():
    from engine import analyze

    results = list(analyze(INITIAL, start_depth=6, max_depth=8, time_limit_ms=5000))
    depths = [r.depth for r in results]
    assert depths == sorted(depths)
    assert depths[0] >= 6 and depths[-1] <= 8
    for r in results:
        assert r.pv and all(isinstance(m, int) for m in r.pv)
        assert r.score_red == (r.score_stm if r.side_to_move == C.RED else -r.score_stm)


def test_time_limit_respected():
    from engine import analyze

    t0 = time.perf_counter()
    results = list(analyze(INITIAL, start_depth=6, max_depth=32, time_limit_ms=400))
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 8000  # 首个用例含编译余量；且不允许失控
    assert results and results[0].depth >= 6


def test_stop_flag_aborts_and_marks_incomplete():
    from engine import analyze

    stop = np.zeros(1, dtype=np.int8)
    it = analyze(INITIAL, start_depth=6, max_depth=32, time_limit_ms=60000, stop=stop)
    first = next(it)
    assert first.depth >= 6
    stop[0] = 1
    rest = list(it)
    assert all(r.depth > first.depth for r in rest)  # 已完成的层仍被产出


def test_score_red_perspective():
    from engine import analyze

    results = list(analyze(INITIAL, start_depth=6, max_depth=6, time_limit_ms=5000))
    last = results[-1]
    assert last.side_to_move == C.RED
    assert last.score_red == last.score_stm


def test_score_red_flips_for_black_to_move():
    from engine import analyze

    fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR b - - 0 1"
    results = list(analyze(fen, start_depth=6, max_depth=6, time_limit_ms=5000))
    last = results[-1]
    assert last.side_to_move == C.BLACK
    assert last.score_red == -last.score_stm


def test_mate_reported():
    from engine import analyze
    from engine import movegen as MG
    from engine import position as P

    results = list(analyze(MATE_IN_ONE, start_depth=6, max_depth=6, time_limit_ms=5000))
    last = results[-1]
    assert last.score_red > C.MAX_SCORE - 100
    assert last.mate == 1
    assert len(last.pv) >= 1

    # 穷举校验：PV 首着走完后黑方无合法着法（将杀或困毙）
    assert len(last.pv) <= 8
    st = P.load_position(MATE_IN_ONE)
    undo = P.make_move(st, last.pv[0])
    assert MG.gen_legal_moves(st, C.BLACK).size == 0
    P.unmake_move(st, last.pv[0], undo)


def test_pv_is_independent_copy():
    from engine import analyze

    results = list(analyze(INITIAL, start_depth=6, max_depth=7, time_limit_ms=5000))
    pvs = [r.pv for r in results]
    assert all(isinstance(pv, list) for pv in pvs)
    assert all(type(m) is int for pv in pvs for m in pv)
    # 每层结果持有独立 Python list（不共享 stack.pv 的 numpy buffer）
    for i, a in enumerate(pvs):
        for b in pvs[i + 1 :]:
            assert a is not b
    snapshot = list(pvs[-1])
    pvs[-1].append(12345)
    assert snapshot == results[-1].pv[:-1]


def test_invalid_stop_argument_rejected():
    from engine import analyze

    with pytest.raises(ValueError):
        list(analyze(INITIAL, max_depth=4, stop=np.zeros(1, dtype=np.int64)))


def test_depth_bounds_clamped_and_no_result_when_start_exceeds_max():
    from engine import analyze

    # max_depth 超上限被钳到 32；首个产出层仍是 start_depth，随后立即到时停止
    results = list(analyze(INITIAL, start_depth=6, max_depth=99, time_limit_ms=150))
    assert results and results[-1].depth == 6

    # start_depth > max_depth：不产出且不死循环
    assert list(analyze(INITIAL, start_depth=8, max_depth=6, time_limit_ms=5000)) == []


def test_start_depth_above_max_returns_before_loading_position(monkeypatch):
    """start_depth > max_depth 时应提前返回：不加载局面、不分配 Ctx/Stack 大对象。"""
    from engine import analysis as A
    from engine import analyze

    def fail_load_position(fen):
        raise AssertionError("start_depth > max_depth 时不应加载局面")

    monkeypatch.setattr(A, "load_position", fail_load_position)
    assert list(analyze(INITIAL, start_depth=8, max_depth=6, time_limit_ms=5000)) == []


def test_interrupted_layer_is_dropped_and_no_further_depth(monkeypatch):
    """停旗中断层的确定性回归：第 7 层中途置 stop 并返回垃圾分。

    - 已完成层（6）仍产出；
    - 第 7 层结果不可信，被丢弃、不产出；
    - 第 8 层不再发起（调用序列止于 7）。
    """
    from engine import analyze
    from engine import search as S

    stop = np.zeros(1, dtype=np.int8)
    calls = []
    real_search_depth = S.search_depth

    def fake_search_depth(st, ctx, stack, depth):
        calls.append(depth)
        if depth >= 7:
            stop[0] = 1  # 模拟其他线程在 nogil 搜索中途置位
            return np.int64(999999), np.int64(0)  # 垃圾值，不得产出
        return real_search_depth(st, ctx, stack, depth)

    monkeypatch.setattr(S, "search_depth", fake_search_depth)
    results = list(
        analyze(INITIAL, start_depth=6, max_depth=10, time_limit_ms=60000, stop=stop)
    )
    assert [r.depth for r in results] == [6]
    assert results[0].score_stm != 999999
    assert calls == [4, 5, 6, 7]
    assert stop[0] == 1


def test_generator_close_releases_position():
    from engine import analyze

    it = analyze(INITIAL, start_depth=6, max_depth=32, time_limit_ms=60000)
    first = next(it)
    it.close()  # finally 中释放 ctx/stack/st
    assert first.depth >= 6
    assert list(it) == []


def test_warmup_idempotent():
    from engine import warmup

    warmup()
    t0 = time.perf_counter()
    warmup()  # 不抛异常
    assert (time.perf_counter() - t0) < 0.5  # 已预热，第二次近似零开销
