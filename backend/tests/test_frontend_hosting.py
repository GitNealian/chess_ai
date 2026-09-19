import app as app_module
from app import create_app
from config import TestConfig
from models import Game


def test_create_app_creates_tables():
    application = create_app(TestConfig)
    with application.app_context():
        assert Game.query.count() == 0


def _make_client(monkeypatch, dist_dir):
    monkeypatch.setattr(app_module, "FRONTEND_DIST", str(dist_dir))
    return create_app(TestConfig).test_client()


def test_root_404_when_dist_missing(monkeypatch, tmp_path):
    missing = tmp_path / "no-dist"
    client = _make_client(monkeypatch, missing)
    assert client.get("/").status_code == 404


def test_api_routes_still_work_when_dist_missing(monkeypatch, tmp_path):
    missing = tmp_path / "no-dist"
    client = _make_client(monkeypatch, missing)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_root_serves_index(monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("<h1>chess</h1>", encoding="utf-8")
    client = _make_client(monkeypatch, tmp_path)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "chess" in resp.get_data(as_text=True)


def test_existing_asset_is_served(monkeypatch, tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "foo.js").write_text("console.log(1)", encoding="utf-8")
    client = _make_client(monkeypatch, tmp_path)
    resp = client.get("/assets/foo.js")
    assert resp.status_code == 200
    assert "console.log(1)" in resp.get_data(as_text=True)


def test_unknown_asset_falls_back_to_index(monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("<h1>chess</h1>", encoding="utf-8")
    client = _make_client(monkeypatch, tmp_path)
    resp = client.get("/assets/missing.js")
    assert resp.status_code == 200
    assert "chess" in resp.get_data(as_text=True)


def test_unknown_api_returns_404(monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("<h1>chess</h1>", encoding="utf-8")
    client = _make_client(monkeypatch, tmp_path)
    resp = client.get("/api/unknown")
    assert resp.status_code == 404
    assert "chess" not in resp.get_data(as_text=True)


def test_bare_api_returns_404(monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("<h1>chess</h1>", encoding="utf-8")
    client = _make_client(monkeypatch, tmp_path)
    resp = client.get("/api")
    assert resp.status_code == 404
    assert "chess" not in resp.get_data(as_text=True)


def test_path_traversal_blocked(monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>chess</h1>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("top-secret", encoding="utf-8")
    client = _make_client(monkeypatch, dist)
    resp = client.get("/../secret.txt")
    assert resp.status_code == 200
    assert "chess" in resp.get_data(as_text=True)
    assert "top-secret" not in resp.get_data(as_text=True)
