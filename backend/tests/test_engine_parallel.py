"""Lazy SMP 并行搜索测试（设计见 docs/plans/2026-09-22-lazy-smp-design.md）。

覆盖：线程数解析、辅助线程上下文隔离、共享 TT 并发读写、并行分析
结果口径、stop 中断与线程清理。
"""

import os
import threading

import numpy as np

from engine import analyze
from engine import analysis as A
from engine import constants as C
from engine import search as S

INITIAL = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
MATE_IN_ONE = "3R5/5k1N1/9/9/9/9/9/9/9/4K1R2 w - - 0 1"


def _auto_threads():
    cpus = os.cpu_count() or 1
    return max(1, min(cpus - 1, 8))


def test_resolve_threads_explicit_wins(monkeypatch):
    monkeypatch.setenv("ENGINE_THREADS", "3")
    assert A._resolve_threads(2) == 2


def test_resolve_threads_env(monkeypatch):
    monkeypatch.setenv("ENGINE_THREADS", "3")
    assert A._resolve_threads(None) == 3


def test_resolve_threads_auto(monkeypatch):
    monkeypatch.delenv("ENGINE_THREADS", raising=False)
    assert A._resolve_threads(None) == _auto_threads()


def test_resolve_threads_clamped():
    assert A._resolve_threads(0) == 1
    assert A._resolve_threads(999) == A.MAX_THREADS


def test_resolve_threads_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv("ENGINE_THREADS", "abc")
    assert A._resolve_threads(None) == _auto_threads()
    assert A._resolve_threads("xyz") == _auto_threads()
