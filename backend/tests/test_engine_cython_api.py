"""Cython 后端（engine.backend + _cycore）端到端测试。

既有用例默认走 numba；本文件覆盖 `ENGINE_BACKEND=cython` 验证新后端。
扩展不可用时整体 skip。
"""

import pytest

FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

pytest.importorskip("engine._cycore")


@pytest.fixture(autouse=True)
def _cython_backend(monkeypatch):
    monkeypatch.setenv("ENGINE_BACKEND", "cython")


def test_resolve_backend_env(monkeypatch):
    from engine import backend

    monkeypatch.setenv("ENGINE_BACKEND", "cython")
    assert backend.resolve_backend() == "cython"
    monkeypatch.setenv("ENGINE_BACKEND", "numba")
    assert backend.resolve_backend() == "numba"


def test_analyze_cython_progressive():
    from engine import analyze

    results = list(analyze(FEN, start_depth=6, max_depth=8, time_limit_ms=10000))
    assert [r.depth for r in results] == [6, 7, 8]
    for r in results:
        assert r.pv and all(isinstance(m, int) for m in r.pv)
        assert r.score_red == (r.score_stm if r.side_to_move == 1 else -r.score_stm)


def test_analyze_cython_depth8_score():
    from engine import analyze

    last = list(analyze(FEN, start_depth=8, max_depth=8, time_limit_ms=10000))[-1]
    assert last.score_stm == 19


def test_cython_hash_size_power_of_two():
    from engine import analyze

    with pytest.raises(ValueError):
        list(analyze(FEN, start_depth=4, max_depth=4, hash_size=100))


def test_cython_intent_events():
    from engine import intent

    events = list(intent.intent_events(FEN, per_line_timeout_ms=3000))
    types = [e["type"] for e in events]
    assert types and types[0] == "rank"
    assert "threat" in types
