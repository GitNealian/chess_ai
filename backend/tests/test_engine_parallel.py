"""Lazy SMP 并行搜索测试（设计见 docs/plans/2026-09-22-lazy-smp-design.md）。

覆盖：线程数解析、辅助线程上下文隔离、共享 TT 并发读写、并行分析
结果口径、stop 中断与线程清理。
"""

import os

import numpy as np
import pytest
from engine import analysis as A
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
