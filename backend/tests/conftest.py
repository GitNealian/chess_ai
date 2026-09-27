import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from config import TestConfig
from models import db


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def engine_threads_single(monkeypatch):
    """测试默认单线程：并行专项用例显式传 threads 覆盖。"""
    monkeypatch.setenv("ENGINE_THREADS", "1")


@pytest.fixture(autouse=True)
def engine_backend_numba(monkeypatch):
    """既有用例默认走 numba 后端（保持原语义，含对 numba 内部的 mock）；

    Cython 后端专项用例在自身 fixture 中覆盖 `ENGINE_BACKEND=cython`。
    """
    monkeypatch.setenv("ENGINE_BACKEND", "numba")
