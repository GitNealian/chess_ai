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
