def test_parse_preview_does_not_persist(client):
    resp = client.post("/api/games/parse", json={"text": "炮二平五 炮8平5"})
    assert resp.status_code == 200
    assert len(resp.get_json()["moves"]) == 2
    assert client.get("/api/games").get_json()["items"] == []


def test_parse_error_reports_step(client):
    resp = client.post("/api/games/parse", json={"text": "炮二平五 炮8进9"})
    assert resp.status_code == 400
    assert "step" in resp.get_json()


def test_import_pgn(client):
    pgn = '[Event "测试"]\n[Red "甲"]\n\n1. 炮二平五 炮8平5\n'
    resp = client.post("/api/games/import-pgn", json={"pgn": pgn, "category": "中炮"})
    assert resp.status_code == 201
    created = resp.get_json()["created"]
    assert len(created) == 1
    assert created[0]["category"] == "中炮"
