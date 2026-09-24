import pytest

from app import create_app
from config import TestConfig
from models import db


class AuthTestConfig(TestConfig):
    AUTH_PASSWORD = "s3cret"
    SECRET_KEY = "auth-test-secret"


@pytest.fixture
def auth_app():
    app = create_app(AuthTestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def auth_client(auth_app):
    return auth_app.test_client()


def test_login_success_and_me(auth_client):
    resp = auth_client.post("/api/auth/login", json={"password": "s3cret"})
    assert resp.status_code == 200
    me = auth_client.get("/api/auth/me").get_json()
    assert me == {"auth_required": True, "authenticated": True}


def test_login_wrong_password(auth_client):
    resp = auth_client.post("/api/auth/login", json={"password": "wrong"})
    assert resp.status_code == 401
    me = auth_client.get("/api/auth/me").get_json()
    assert me["authenticated"] is False


def test_me_when_auth_disabled(client):
    me = client.get("/api/auth/me").get_json()
    assert me == {"auth_required": False, "authenticated": False}


def test_logout_clears_session(auth_client):
    auth_client.post("/api/auth/login", json={"password": "s3cret"})
    assert auth_client.post("/api/auth/logout").status_code == 200
    me = auth_client.get("/api/auth/me").get_json()
    assert me["authenticated"] is False


def test_api_requires_login_when_enabled(auth_client):
    assert auth_client.get("/api/games").status_code == 401
    assert auth_client.get("/api/stats").status_code == 401


def test_login_grants_api_access(auth_client):
    auth_client.post("/api/auth/login", json={"password": "s3cret"})
    assert auth_client.get("/api/stats").status_code == 200


def test_health_and_auth_endpoints_whitelisted(auth_client):
    assert auth_client.get("/api/health").status_code == 200
    assert auth_client.get("/api/auth/me").status_code == 200
    assert auth_client.post("/api/auth/logout").status_code == 200


def test_non_api_paths_not_blocked(auth_client):
    assert auth_client.get("/some/spa/path").status_code != 401


def test_auth_disabled_apis_open(client):
    assert client.get("/api/stats").status_code == 200
