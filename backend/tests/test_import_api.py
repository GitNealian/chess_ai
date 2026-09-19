def test_parse_preview_does_not_persist(client):
    resp = client.post("/api/games/parse", json={"text": "炮二平五 炮8平5"})
    assert resp.status_code == 200
    assert len(resp.get_json()["moves"]) == 2
    assert client.get("/api/games").get_json()["items"] == []


def test_parse_error_reports_step(client):
    resp = client.post("/api/games/parse", json={"text": "炮二平五 炮8进9"})
    assert resp.status_code == 400
    assert resp.get_json()["step"] == 2


def test_parse_iccs_moves(client):
    resp = client.post("/api/games/parse", json={"text": "h2e2 h7e7"})
    assert resp.status_code == 200
    assert len(resp.get_json()["moves"]) == 2


def test_parse_rejects_non_string_text(client):
    resp = client.post("/api/games/parse", json={"text": 123})
    assert resp.status_code == 400


def test_import_pgn(client):
    pgn = '[Event "测试"]\n[Red "甲"]\n\n1. 炮二平五 炮8平5\n'
    resp = client.post("/api/games/import-pgn", json={"pgn": pgn, "category": "中炮"})
    assert resp.status_code == 201
    created = resp.get_json()["created"]
    assert len(created) == 1
    assert created[0]["category"] == "中炮"


def test_import_pgn_rejects_empty(client):
    resp = client.post("/api/games/import-pgn", json={"pgn": "   "})
    assert resp.status_code == 400


def test_import_pgn_rejects_invalid_practice_side(client):
    pgn = '[Event "测试"]\n\n1. 炮二平五 炮8平5\n'
    resp = client.post(
        "/api/games/import-pgn", json={"pgn": pgn, "practice_side": "white"}
    )
    assert resp.status_code == 400
