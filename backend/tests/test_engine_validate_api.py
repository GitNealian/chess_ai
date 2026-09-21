"""`POST /api/engine/validate-move` 无状态走子校验接口测试。"""

from chess_engine.board import INITIAL_FEN

# 红车 (0,8) 走 (0,9)：将死黑将（(3,9)/(5,9) 被同一车控制，(4,8) 被 (4,5) 车控制）
MATE_FEN = "4k4/R8/9/9/4R4/9/9/9/9/4K4 w - - 0 1"
# 红走帅 (3,0)→(3,1) 后黑将 (4,9) 无着可走且未被将军（困毙）
STALEMATE_FEN = "4k4/3R1R3/9/9/9/9/9/9/9/3K5 w - - 0 1"
# 红车 (0,8) 走 (0,9) 将军，但黑将可逃 (4,8)
CHECK_FEN = "4k4/R8/9/9/9/9/9/9/9/3K5 w - - 0 1"


def post(client, payload):
    return client.post("/api/engine/validate-move", json=payload)


def test_validate_legal_move_with_default_fen(client):
    resp = post(client, {"move": {"x1": 1, "y1": 2, "x2": 4, "y2": 2}})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["legal"] is True
    assert body["side_to_move"] == "black"
    assert body["chinese"] == "炮八平五"
    assert body["check"] is False
    assert body["game_over"] is None
    assert body["fen"] != INITIAL_FEN


def test_validate_replays_initial_fen_and_moves(client):
    payload = {
        "initial_fen": INITIAL_FEN,
        "moves": [{"x1": 1, "y1": 2, "x2": 4, "y2": 2}],
        "move": {"x1": 7, "y1": 9, "x2": 6, "y2": 7},
    }
    body = post(client, payload).get_json()
    assert body["legal"] is True
    assert body["side_to_move"] == "red"
    assert body["chinese"] == "马8进7"


def test_validate_illegal_move_returns_reason(client):
    body = post(client, {"move": {"x1": 0, "y1": 0, "x2": 1, "y2": 1}}).get_json()
    assert body["legal"] is False
    assert body["reason"] == "该棋子不能这样走"
    assert "fen" not in body


def test_validate_wrong_side_piece(client):
    body = post(client, {"move": {"x1": 0, "y1": 9, "x2": 0, "y2": 8}}).get_json()
    assert body["legal"] is False
    assert body["reason"] == "该棋子不属于行棋方"


def test_validate_empty_origin(client):
    body = post(client, {"move": {"x1": 4, "y1": 4, "x2": 4, "y2": 5}}).get_json()
    assert body["legal"] is False
    assert body["reason"] == "起点没有棋子"


def test_validate_reports_check_and_checkmate(client):
    body = post(
        client, {"initial_fen": CHECK_FEN, "move": {"x1": 0, "y1": 8, "x2": 0, "y2": 9}}
    ).get_json()
    assert body["legal"] is True
    assert body["check"] is True
    assert body["game_over"] is None

    body = post(
        client, {"initial_fen": MATE_FEN, "move": {"x1": 0, "y1": 8, "x2": 0, "y2": 9}}
    ).get_json()
    assert body["check"] is True
    assert body["game_over"] == {"winner": "red", "reason": "checkmate"}


def test_validate_reports_stalemate(client):
    body = post(
        client, {"initial_fen": STALEMATE_FEN, "move": {"x1": 3, "y1": 0, "x2": 3, "y2": 1}}
    ).get_json()
    assert body["legal"] is True
    assert body["check"] is False
    assert body["game_over"] == {"winner": "red", "reason": "stalemate"}


def test_validate_rejects_bad_payloads(client):
    assert client.post("/api/engine/validate-move", json={}).status_code == 400
    assert post(client, {"move": "炮二平五"}).status_code == 400
    assert post(client, {"move": {"x1": 1, "y1": 2}}).status_code == 400
    assert post(client, {"initial_fen": "not-a-fen", "move": {"x1": 1, "y1": 2, "x2": 4, "y2": 2}}).status_code == 400
    assert post(client, {"moves": "x", "move": {"x1": 1, "y1": 2, "x2": 4, "y2": 2}}).status_code == 400


def test_validate_rejects_illegal_replay_sequence(client):
    payload = {
        "moves": [{"x1": 0, "y1": 0, "x2": 1, "y2": 1}],
        "move": {"x1": 1, "y1": 2, "x2": 4, "y2": 2},
    }
    resp = post(client, payload)
    assert resp.status_code == 400
    assert "第 1 步" in resp.get_json()["error"]
