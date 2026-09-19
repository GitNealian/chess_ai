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


MULTI_STEP_MOVES = [
    {"x1": 7, "y1": 2, "x2": 4, "y2": 2},
    {"x1": 7, "y1": 7, "x2": 4, "y2": 7},
    {"x1": 7, "y1": 0, "x2": 6, "y2": 2},
    {"x1": 7, "y1": 9, "x2": 6, "y2": 7},
]


def test_check_multi_step_ply2(client):
    game_id = _create(client, MULTI_STEP_MOVES)
    resp = client.post(
        f"/api/games/{game_id}/check-move",
        json={"ply": 2, "move": {"x1": 7, "y1": 0, "x2": 6, "y2": 2}},
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["correct"] is True
    assert body["side_to_move"] == "black"
    assert body["fen"] == "rnbakabnr/9/1c2c4/p1p1p1p1p/9/9/P1P1P1P1P/1C2C1N2/9/RNBAKAB1R b - - 0 1"


def test_check_move_rejects_out_of_range_ply(client):
    game_id = _create(client, MULTI_STEP_MOVES)
    resp = client.post(
        f"/api/games/{game_id}/check-move",
        json={"ply": 4, "move": {"x1": 7, "y1": 0, "x2": 6, "y2": 2}},
    )
    assert resp.status_code == 400


def test_check_move_rejects_bad_move_format(client):
    game_id = _create(client, MULTI_STEP_MOVES)
    for bad in ("notadict", {}):
        resp = client.post(
            f"/api/games/{game_id}/check-move", json={"ply": 0, "move": bad}
        )
        assert resp.status_code == 400
