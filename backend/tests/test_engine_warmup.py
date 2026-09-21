"""Task 14：`create_app` 的引擎预热线程集成测试。

覆盖：
- `TESTING` 配置下不触发 `engine.warmup()`（避免测试被 JIT 预热拖慢）；
- 非 `TESTING` 配置下启动 daemon 预热线程并执行 `warmup`。

真实 `warmup` 冷启动约 24-34s，测试用 monkeypatch 桩替换，不跑真实预热。
"""

import threading
import time

import engine
from app import create_app
from config import Config, TestConfig


class _ProdLikeConfig(Config):
    """非 TESTING 配置：内存库避免污染 chess.db，仅用于预热线程集成点。"""

    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = False


def _wait_for(predicate, timeout=5.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_create_app_skips_warmup_in_testing(monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "warmup", lambda: calls.append(1))

    app = create_app(TestConfig)
    assert app.config["TESTING"] is True

    time.sleep(0.2)
    assert calls == []


def test_warmup_thread_starts_in_production_config(monkeypatch):
    calls = []
    started = threading.Event()

    def stub():
        calls.append(1)
        started.set()

    monkeypatch.setattr(engine, "warmup", stub)

    app = create_app(_ProdLikeConfig)
    assert not app.config.get("TESTING")

    assert _wait_for(started.is_set), "非 TESTING 配置应启动 engine-warmup 线程"
    assert calls == [1]
