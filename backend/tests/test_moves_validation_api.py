from chess_engine.board import INITIAL_FEN

CANNON_TO_CENTER = {"x1": 1, "y1": 2, "x2": 4, "y2": 2}


def _payload(**overrides):
    data = {"name": "校验测试", "moves": [dict(CANNON_TO_CENTER)]}
    data.update(overrides)
    return data


def test_create_with_legal_moves_succeeds(client):
    resp = client.post("/api/games", json=_payload())
    assert resp.status_code == 201
    assert resp.get_json()["moves"] == [CANNON_TO_CENTER]
    assert resp.get_json()["initial_fen"] == INITIAL_FEN


def test_create_with_illegal_move_returns_400(client):
    moves = [{"x1": 0, "y1": 0, "x2": 8, "y2": 8}]
    resp = client.post("/api/games", json=_payload(moves=moves))
    assert resp.status_code == 400
    assert "第 1 步" in resp.get_json()["detail"]


def test_create_with_second_move_illegal_reports_step(client):
    moves = [dict(CANNON_TO_CENTER), {"x1": 0, "y1": 0, "x2": 8, "y2": 8}]
    resp = client.post("/api/games", json=_payload(moves=moves))
    assert resp.status_code == 400
    assert "第 2 步" in resp.get_json()["detail"]


def test_create_with_missing_field_returns_400(client):
    resp = client.post("/api/games", json=_payload(moves=[{"x1": 1, "y1": 2, "x2": 4}]))
    assert resp.status_code == 400
    assert "第 1 步" in resp.get_json()["detail"]


def test_create_with_string_coordinate_returns_400(client):
    move = {"x1": "1", "y1": 2, "x2": 4, "y2": 2}
    resp = client.post("/api/games", json=_payload(moves=[move]))
    assert resp.status_code == 400
    assert "第 1 步" in resp.get_json()["detail"]


def test_create_with_bool_coordinate_returns_400(client):
    move = {"x1": True, "y1": 2, "x2": 4, "y2": 2}
    resp = client.post("/api/games", json=_payload(moves=[move]))
    assert resp.status_code == 400


def test_create_with_out_of_board_move_returns_400(client):
    moves = [{"x1": 0, "y1": 0, "x2": 0, "y2": 10}]
    resp = client.post("/api/games", json=_payload(moves=moves))
    assert resp.status_code == 400
    assert "第 1 步" in resp.get_json()["detail"]


def test_create_with_invalid_initial_fen_returns_400(client):
    resp = client.post("/api/games", json=_payload(initial_fen="not-a-fen"))
    assert resp.status_code == 400


def test_create_with_non_string_initial_fen_returns_400(client):
    resp = client.post("/api/games", json=_payload(initial_fen=123))
    assert resp.status_code == 400


def test_update_with_illegal_moves_returns_400(client):
    game_id = client.post("/api/games", json=_payload()).get_json()["id"]
    resp = client.put(
        f"/api/games/{game_id}",
        json={"moves": [{"x1": 0, "y1": 0, "x2": 8, "y2": 8}]},
    )
    assert resp.status_code == 400
    assert "第 1 步" in resp.get_json()["detail"]


def test_update_name_does_not_validate_moves(client):
    game_id = client.post("/api/games", json=_payload()).get_json()["id"]
    resp = client.put(f"/api/games/{game_id}", json={"name": "只改名字"})
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "只改名字"


def test_update_initial_fen_making_moves_illegal_returns_400(client):
    game_id = client.post("/api/games", json=_payload()).get_json()["id"]
    empty_fen = "9/9/9/9/9/9/9/9/9/9 w - - 0 1"
    resp = client.put(f"/api/games/{game_id}", json={"initial_fen": empty_fen})
    assert resp.status_code == 400
