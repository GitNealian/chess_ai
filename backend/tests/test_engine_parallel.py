"""Lazy SMP 并行搜索测试（设计见 docs/plans/2026-09-22-lazy-smp-design.md）。

覆盖：线程数解析、辅助线程上下文隔离、共享 TT 并发读写、并行分析
结果口径、stop 中断与线程清理。
"""

import os
import threading
import time

import numpy as np
import pytest
from engine import analysis as A
from engine import analyze
from engine import constants as C
from engine import search as S

INITIAL = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
MATE_IN_ONE = "3R5/5k1N1/9/9/9/9/9/9/9/4K1R2 w - - 0 1"


def test_resolve_threads_explicit_wins(monkeypatch):
    monkeypatch.setenv("ENGINE_THREADS", "3")
    assert A._resolve_threads(2) == 2


def test_resolve_threads_env(monkeypatch):
    monkeypatch.setenv("ENGINE_THREADS", "3")
    assert A._resolve_threads(None) == 3


def test_resolve_threads_auto_boundaries(monkeypatch):
    monkeypatch.delenv("ENGINE_THREADS", raising=False)
    for cpus, expected in ((1, 1), (4, 3), (64, 8)):
        monkeypatch.setattr(os, "cpu_count", lambda cpus=cpus: cpus)
        assert A._resolve_threads(None) == expected


def test_resolve_threads_auto_cpu_count_unknown(monkeypatch):
    monkeypatch.delenv("ENGINE_THREADS", raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: None)
    assert A._resolve_threads(None) == 1


def test_resolve_threads_clamped(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    assert A._resolve_threads(0) == 1
    assert A._resolve_threads(999) == A.MAX_THREADS


def test_resolve_threads_env_edges(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    cases = (("", 7), ("0", 1), ("-3", 1), ("999", A.MAX_THREADS), ("3.5", 7))
    for raw, expected in cases:
        monkeypatch.setenv("ENGINE_THREADS", raw)
        assert A._resolve_threads(None) == expected


def test_resolve_threads_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv("ENGINE_THREADS", "abc")
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    assert A._resolve_threads(None) == 7
    assert A._resolve_threads("xyz") == 7


def test_resolve_threads_non_finite_float_falls_back(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    assert A._resolve_threads(float("inf")) == 7
    assert A._resolve_threads(float("nan")) == 7


def test_worker_context_shares_tt_isolates_rest():
    shared_stop = np.zeros(1, dtype=np.int8)
    base = S.new_context(hash_size=1 << 10)._replace(stop=shared_stop)
    worker = S.new_worker_context(base, shared_stop)

    independent = (
        "killer",
        "history",
        "nodes",
        "root_moves",
        "root_scores",
        "root_count",
        "root_inited",
    )
    assert set(S.Ctx._fields) == set(S._TT_FIELDS) | set(independent) | {"stop"}

    for field in S._TT_FIELDS:
        assert getattr(worker, field) is getattr(base, field)
    for field in independent:
        w = getattr(worker, field)
        b = getattr(base, field)
        assert w is not b
        assert w.dtype == b.dtype
        assert w.shape == b.shape

    assert worker.stop is shared_stop
    assert worker.nodes[0] == 0
    worker.nodes[0] = 5
    assert base.nodes[0] == 0
    worker.root_count[0] = 3
    assert base.root_count[0] == 0
    worker.history[0, 0] = 7
    assert base.history[0, 0] == 0


def test_worker_context_rejects_non_int8_stop():
    shared_stop = np.zeros(1, dtype=np.int8)
    base = S.new_context(hash_size=1 << 10)._replace(stop=shared_stop)
    with pytest.raises(ValueError):
        S.new_worker_context(base, np.zeros(1, dtype=np.int32))


def test_worker_context_rejects_foreign_stop():
    shared_stop = np.zeros(1, dtype=np.int8)
    base = S.new_context(hash_size=1 << 10)._replace(stop=shared_stop)
    with pytest.raises(ValueError):
        S.new_worker_context(base, np.zeros(1, dtype=np.int8))


def test_concurrent_tt_no_foreign_values():
    """4 线程并发读写同一 TT：不崩、命中分数不越界、命中值归属正确。

    覆盖边界：验证不崩溃、分数在合法域、命中时值确为自己写入的条目，并确认
    复核没有过度保守到命中塌陷；受调度不确定性限制，本用例不直接证明
    「无任何脏读」（残余窗口见 Lazy SMP 设计文档）。

    `got == value` 是强归属断言（每个随机 key 只写一次，命中即应为自己的
    值）；理论上的残余窗口（写者数据已写、key 未写）可能触发它，实测压力下
    概率 < 1e-6/运行，一旦触发应按防护缺陷调查而非放宽断言。
    """
    ctx = S.new_context(hash_size=1 << 12)
    errors = []
    hits = []

    def hammer(seed):
        rng = np.random.default_rng(seed)
        for _ in range(4000):
            play = int(rng.integers(0, 2))
            z32 = int(rng.integers(0, 1 << 20))
            z64 = int(rng.integers(1, 1 << 62))
            value = int(rng.integers(-9999, 9999))
            try:
                S.set_tt(ctx, play, z32, z64, S.HASH_PV, value, 6, C.pack_move(0, 1))
                hit, got, _ = S.get_tt(ctx, play, z32, z64, 6, -9999, 9999)
                if hit:
                    got = int(got)
                    assert -20000 <= got <= 20000
                    assert got == value
                    hits.append(1)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=hammer, args=(seed,)) for seed in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert sum(hits) > 0


def test_parallel_analysis_produces_results():
    results = list(
        analyze(INITIAL, start_depth=6, max_depth=8, time_limit_ms=5000, threads=3)
    )
    depths = [r.depth for r in results]
    assert depths == sorted(depths)
    assert depths[0] >= 6 and depths[-1] <= 8
    assert all(r.pv for r in results)
    for r in results:
        assert r.score_red == (
            r.score_stm if r.side_to_move == C.RED else -r.score_stm
        )


def test_parallel_mate_consistent_across_thread_counts():
    for threads in (1, 2, 4):
        results = list(
            analyze(
                MATE_IN_ONE,
                start_depth=6,
                max_depth=6,
                time_limit_ms=5000,
                threads=threads,
            )
        )
        last = results[-1]
        assert last.mate == 1, threads
        assert last.score_red > C.MAX_SCORE - 100, threads


def test_parallel_stop_leaves_no_worker_threads():
    stop = np.zeros(1, dtype=np.int8)
    it = analyze(
        INITIAL,
        start_depth=6,
        max_depth=32,
        time_limit_ms=60000,
        stop=stop,
        threads=4,
    )
    first = next(it)
    assert first.depth >= 6
    stop[0] = 1
    list(it)
    leftovers = [
        t
        for t in threading.enumerate()
        if t.name.startswith("engine-helper-") or t.name == "engine-stop-forward"
    ]
    assert leftovers == []


def test_parallel_start_failure_cleans_up(monkeypatch):
    real_start = threading.Thread.start

    def flaky_start(self):
        if self.name == "engine-helper-2":
            raise RuntimeError("start failed")
        return real_start(self)

    monkeypatch.setattr(threading.Thread, "start", flaky_start)
    stop = np.zeros(1, dtype=np.int8)
    it = analyze(
        INITIAL,
        start_depth=6,
        max_depth=32,
        time_limit_ms=60000,
        stop=stop,
        threads=4,
    )
    with pytest.raises(RuntimeError):
        next(it)
    time.sleep(0.05)
    leftovers = [
        t
        for t in threading.enumerate()
        if t.name.startswith("engine-helper-") or t.name == "engine-stop-forward"
    ]
    assert leftovers == []


def test_parallel_generator_close_leaves_no_worker_threads():
    it = analyze(
        INITIAL,
        start_depth=6,
        max_depth=32,
        time_limit_ms=60000,
        threads=4,
    )
    first = next(it)
    assert first.depth >= 6
    it.close()
    time.sleep(0.05)
    leftovers = [
        t
        for t in threading.enumerate()
        if t.name.startswith("engine-helper-") or t.name == "engine-stop-forward"
    ]
    assert leftovers == []


def test_single_thread_starts_no_workers():
    it = analyze(
        INITIAL, start_depth=6, max_depth=6, time_limit_ms=5000, threads=1
    )
    next(it)
    names = [t.name for t in threading.enumerate()]
    assert not any(
        n.startswith("engine-helper-") or n == "engine-stop-forward" for n in names
    )
    list(it)


def test_warmup_is_thread_safe(monkeypatch):
    """4 线程并发 warmup：预热体只执行一次（无锁实现此断言在压力下会失败）。"""
    from engine import warmup

    monkeypatch.setattr(A, "_WARMED", False)
    calls = []
    real_load_position = A.load_position

    def counting_load_position(fen):
        calls.append(fen)
        return real_load_position(fen)

    monkeypatch.setattr(A, "load_position", counting_load_position)
    errors = []
    barrier = threading.Barrier(4)

    def run():
        try:
            barrier.wait()
            warmup()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert A._WARMED is True
    assert len(calls) == 1


def test_warmup_lock_reset_helper_replaces_lock():
    old = A._WARMUP_LOCK
    A._reset_warmup_lock_after_fork()
    assert A._WARMUP_LOCK is not old
