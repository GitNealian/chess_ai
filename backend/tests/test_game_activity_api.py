import time


def _payload(**overrides):
    data = {
        "name": "对局",
        "category": "棋手",
        "moves": [{"x1": 1, "y1": 2, "x2": 4, "y2": 2}],
        "practice_side": "both",
    }
    data.update(overrides)
    return data


def _create(client, **overrides):
    return client.post("/api/games", json=_payload(**overrides)).get_json()["id"]


def test_open_records_and_updates_time(client):
    gid = _create(client)
    first = client.post(f"/api/games/{gid}/open").get_json()
    assert first["last_opened_at"] is not None
    assert first["favorited"] is False
    time.sleep(0.01)
    second = client.post(f"/api/games/{gid}/open").get_json()
    assert second["last_opened_at"] >= first["last_opened_at"]


def test_open_missing_returns_404(client):
    assert client.post("/api/games/9999/open").status_code == 404


def test_favorite_toggles(client):
    gid = _create(client)
    on = client.post(f"/api/games/{gid}/favorite").get_json()
    assert on["favorited"] is True
    assert on["favorited_at"] is not None
    off = client.post(f"/api/games/{gid}/favorite").get_json()
    assert off["favorited"] is False
    assert off["favorited_at"] is None


def test_favorite_missing_returns_404(client):
    assert client.post("/api/games/9999/favorite").status_code == 404


def test_scope_recent_orders_by_opened(client):
    a = _create(client, name="A")
    b = _create(client, name="B")
    client.post(f"/api/games/{a}/open")
    time.sleep(0.01)
    client.post(f"/api/games/{b}/open")
    body = client.get("/api/games?scope=recent").get_json()
    assert [g["name"] for g in body["items"]] == ["B", "A"]


def test_scope_recent_excludes_unopened(client):
    _create(client, name="X")
    assert client.get("/api/games?scope=recent").get_json()["total"] == 0


def test_scope_favorite_orders_by_favorited(client):
    a = _create(client, name="A")
    b = _create(client, name="B")
    client.post(f"/api/games/{a}/favorite")
    time.sleep(0.01)
    client.post(f"/api/games/{b}/favorite")
    body = client.get("/api/games?scope=favorite").get_json()
    assert [g["name"] for g in body["items"]] == ["B", "A"]


def test_to_dict_includes_favorited(client):
    gid = _create(client)
    client.post(f"/api/games/{gid}/favorite")
    assert client.get(f"/api/games/{gid}").get_json()["favorited"] is True
