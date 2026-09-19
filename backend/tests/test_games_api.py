import time

from chess_engine.board import INITIAL_FEN


def _payload(**overrides):
    data = {
        "name": "中炮对屏风马",
        "category": "中炮",
        "moves": [{"x1": 1, "y1": 2, "x2": 4, "y2": 2}],
        "practice_side": "both",
    }
    data.update(overrides)
    return data


def test_create_and_list(client):
    resp = client.post("/api/games", json=_payload())
    assert resp.status_code == 201
    game_id = resp.get_json()["id"]
    listing = client.get("/api/games").get_json()
    assert any(g["id"] == game_id for g in listing["items"])


def test_get_update_delete(client):
    game_id = client.post("/api/games", json=_payload()).get_json()["id"]
    assert client.get(f"/api/games/{game_id}").status_code == 200
    resp = client.put(f"/api/games/{game_id}", json={"name": "改名"})
    assert resp.get_json()["name"] == "改名"
    assert client.delete(f"/api/games/{game_id}").status_code == 204
    assert client.get(f"/api/games/{game_id}").status_code == 404


def test_filter_by_category_and_keyword(client):
    client.post("/api/games", json=_payload(name="A", category="中炮"))
    client.post("/api/games", json=_payload(name="B", category="飞相"))
    assert len(client.get("/api/games?category=中炮").get_json()["items"]) == 1
    assert len(client.get("/api/games?keyword=B").get_json()["items"]) == 1


def test_invalid_practice_side(client):
    resp = client.post("/api/games", json=_payload(practice_side="green"))
    assert resp.status_code == 400


def test_moves_roundtrip_and_default_initial_fen(client):
    moves = [{"x1": 1, "y1": 2, "x2": 4, "y2": 2}, {"x1": 7, "y1": 7, "x2": 7, "y2": 4}]
    resp = client.post("/api/games", json=_payload(moves=moves))
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["moves"] == moves
    assert body["initial_fen"] == INITIAL_FEN


def test_list_orders_by_updated_at_desc(client):
    a_id = client.post("/api/games", json=_payload(name="A")).get_json()["id"]
    client.post("/api/games", json=_payload(name="B"))
    time.sleep(0.01)
    client.put(f"/api/games/{a_id}", json={"name": "A2"})
    items = client.get("/api/games").get_json()["items"]
    assert items[0]["id"] == a_id


def test_update_missing_id_returns_404(client):
    resp = client.put("/api/games/9999", json={"name": "x"})
    assert resp.status_code == 404


def test_create_moves_not_list_returns_400(client):
    resp = client.post("/api/games", json=_payload(moves="not-a-list"))
    assert resp.status_code == 400


def test_update_empty_name_returns_400(client):
    game_id = client.post("/api/games", json=_payload()).get_json()["id"]
    resp = client.put(f"/api/games/{game_id}", json={"name": ""})
    assert resp.status_code == 400


def test_update_moves_not_list_returns_400(client):
    game_id = client.post("/api/games", json=_payload()).get_json()["id"]
    resp = client.put(f"/api/games/{game_id}", json={"moves": "not-a-list"})
    assert resp.status_code == 400
