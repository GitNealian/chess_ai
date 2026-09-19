def _create(client, moves):
    return client.post("/api/games", json={"name": "t", "moves": moves}).get_json()["id"]


def test_check_correct_move(client):
    game_id = _create(client, [{"x1": 1, "y1": 2, "x2": 4, "y2": 2}])
    resp = client.post(
        f"/api/games/{game_id}/check-move",
        json={"ply": 0, "move": {"x1": 1, "y1": 2, "x2": 4, "y2": 2}},
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["correct"] is True
    assert body["fen"].startswith("rnbakabnr")


def test_check_wrong_move_returns_expected(client):
    game_id = _create(client, [{"x1": 1, "y1": 2, "x2": 4, "y2": 2}])
    resp = client.post(
        f"/api/games/{game_id}/check-move",
        json={"ply": 0, "move": {"x1": 1, "y1": 2, "x2": 3, "y2": 2}},
    )
    body = resp.get_json()
    assert body["correct"] is False
    assert body["expected"]["x2"] == 4


def test_check_illegal_move(client):
    game_id = _create(client, [{"x1": 1, "y1": 2, "x2": 4, "y2": 2}])
    resp = client.post(
        f"/api/games/{game_id}/check-move",
        json={"ply": 0, "move": {"x1": 0, "y1": 0, "x2": 8, "y2": 8}},
    )
    assert resp.status_code == 400
