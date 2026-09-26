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


def test_list_pagination(client):
    for i in range(25):
        client.post("/api/games", json=_payload(name=f"棋谱{i}"))
    body = client.get("/api/games?page=1&page_size=10").get_json()
    assert body["total"] == 25
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert len(body["items"]) == 10
    body = client.get("/api/games?page=3&page_size=10").get_json()
    assert len(body["items"]) == 5


def test_list_default_page_size(client):
    for i in range(25):
        client.post("/api/games", json=_payload(name=f"棋谱{i}"))
    body = client.get("/api/games").get_json()
    assert len(body["items"]) == 20
    assert body["total"] == 25


def test_list_rejects_bad_pagination(client):
    assert client.get("/api/games?page=0").status_code == 400
    assert client.get("/api/games?page=abc").status_code == 400
    assert client.get("/api/games?page_size=0").status_code == 400
    assert client.get("/api/games?page_size=101").status_code == 400


def test_filter_category_is_fuzzy(client):
    client.post("/api/games", json=_payload(name="A", category="2019年腾讯棋牌全国象棋甲级联赛"))
    assert len(client.get("/api/games?category=甲级联赛").get_json()["items"]) == 1
    assert len(client.get("/api/games?category=个人赛").get_json()["items"]) == 0


def test_search_matches_event(client):
    client.post("/api/games", json=_payload(name="A", event="2019年全国象棋个人赛"))
    assert len(client.get("/api/games?keyword=个人赛").get_json()["items"]) == 1


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


def test_scope_collection_matches_exact(client):
    client.post("/api/games", json=_payload(name="古谱A", category="古谱 · 桔中秘"))
    client.post("/api/games", json=_payload(name="古谱B", category="古谱 · 梅花谱"))
    body = client.get("/api/games?scope=collection&collection=桔中秘").get_json()
    assert [g["name"] for g in body["items"]] == ["古谱A"]


def test_scope_collection_requires_name(client):
    assert client.get("/api/games?scope=collection").status_code == 400


def test_scope_tournament_excludes_old_and_blank(client):
    client.post("/api/games", json=_payload(name="赛事", category="棋手", event="联赛"))
    client.post("/api/games", json=_payload(name="古谱", category="古谱 · 桔中秘", event="桔中秘"))
    client.post("/api/games", json=_payload(name="空", category="棋手", event=""))
    body = client.get("/api/games?scope=tournament").get_json()
    assert [g["name"] for g in body["items"]] == ["赛事"]


def test_scope_other_blank_or_na(client):
    client.post("/api/games", json=_payload(name="空", category="棋手", event=""))
    client.post("/api/games", json=_payload(name="NA", category="棋手", event="NA"))
    client.post("/api/games", json=_payload(name="赛事", category="棋手", event="联赛"))
    body = client.get("/api/games?scope=other").get_json()
    assert sorted(g["name"] for g in body["items"]) == ["NA", "空"]


def test_scope_invalid(client):
    assert client.get("/api/games?scope=xx").status_code == 400


def test_collections_aggregate(client):
    client.post("/api/games", json=_payload(name="a1", category="古谱 · 桔中秘"))
    client.post("/api/games", json=_payload(name="a2", category="古谱 · 桔中秘"))
    client.post("/api/games", json=_payload(name="b1", category="古谱 · 梅花谱"))
    client.post("/api/games", json=_payload(name="c", category="棋手"))
    body = client.get("/api/games/collections").get_json()
    assert body["total"] == 2
    assert body["items"][0] == {"name": "桔中秘", "count": 2}
    assert body["items"][1] == {"name": "梅花谱", "count": 1}


def test_sort_created_desc(client):
    for i in range(3):
        client.post("/api/games", json=_payload(name=f"n{i}"))
        time.sleep(0.01)
    body = client.get("/api/games?sort=created_desc").get_json()
    assert body["items"][0]["name"] == "n2"


def test_scope_event_matches_exact(client):
    client.post("/api/games", json=_payload(name="e1", category="棋手", event="联赛"))
    client.post("/api/games", json=_payload(name="e2", category="棋手", event="杯赛"))
    body = client.get("/api/games?scope=event&event=联赛").get_json()
    assert [g["name"] for g in body["items"]] == ["e1"]


def test_scope_event_requires_name(client):
    assert client.get("/api/games?scope=event").status_code == 400


def test_events_aggregate(client):
    client.post("/api/games", json=_payload(name="a", category="棋手", event="联赛"))
    client.post("/api/games", json=_payload(name="b", category="棋手", event="联赛"))
    client.post("/api/games", json=_payload(name="c", category="棋手", event="杯赛"))
    client.post("/api/games", json=_payload(name="d", category="古谱 · 桔中秘", event="桔中秘"))
    client.post("/api/games", json=_payload(name="e", category="棋手", event=""))
    body = client.get("/api/games/events").get_json()
    assert body["total"] == 2
    assert body["items"][0] == {"name": "联赛", "count": 2}
    assert body["items"][1] == {"name": "杯赛", "count": 1}
