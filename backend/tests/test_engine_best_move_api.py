"""`POST /api/engine/best-move` 引擎走子接口测试。

首次运行含 numba JIT 编译（约 20-35s）。
"""


def post(client, payload):
    return client.post("/api/engine/best-move", json=payload)


def test_best_move_from_initial(client):
    body = post(client, {"level": "easy"}).get_json()
    assert body["legal"] is True
    move = body["move"]
    assert all(isinstance(move[k], int) for k in ("x1", "y1", "x2", "y2"))
    assert body["side_to_move"] == "black"
    assert body["fen"].split()[1] == "b"
    assert body["move"]["chinese"]


def test_best_move_black_to_move(client):
    fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/4C2C1/9/RNBAKABNR b - - 0 1"
    body = post(client, {"fen": fen, "level": "easy"}).get_json()
    assert body["legal"] is True
    assert body["side_to_move"] == "red"


def test_best_move_level_defaults_and_invalid_falls_back(client):
    for payload in ({}, {"level": "unknown"}):
        body = post(client, payload).get_json()
        assert body["legal"] is True


def test_best_move_reports_game_over(client):
    # 红车 (0,8) 走 (0,9) 一步将死黑将
    fen = "4k4/R8/9/9/4R4/9/9/9/9/4K4 w - - 0 1"
    body = post(client, {"fen": fen, "level": "easy"}).get_json()
    assert body["legal"] is True
    assert body["check"] is True
    assert body["game_over"] == {"winner": "red", "reason": "checkmate"}


def test_best_move_no_legal_move(client):
    fen = "4k4/3R1R3/9/9/9/9/9/9/9/3K5 w - - 0 1"
    body = post(client, {"fen": fen, "level": "easy"}).get_json()
    assert body["legal"] is True  # 红仍有合法着法
    # 行棋方改为黑：黑将困毙、无合法着法
    body = post(client, {"fen": fen.replace(" w ", " b "), "level": "easy"}).get_json()
    assert body["legal"] is False


def test_best_move_rejects_bad_payloads(client):
    assert client.post("/api/engine/best-move", json={}).status_code == 200
    assert post(client, {"fen": "not-a-fen"}).status_code == 400
    assert post(client, {"moves": "x"}).status_code == 400


def test_best_move_engine_failure_returns_legal_false(client, monkeypatch):
    from routes import engine as engine_routes

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(engine_routes, "analyze", boom)
    body = post(client, {"level": "easy"}).get_json()
    assert body["legal"] is False
