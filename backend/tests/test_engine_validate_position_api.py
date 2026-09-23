"""`POST /api/engine/validate-position` 摆子规则校验接口测试。"""


def post(client, payload):
    return client.post("/api/engine/validate-position", json=payload)


def test_valid_position_returns_fen(client):
    body = post(
        client,
        {
            "pieces": [
                {"x": 4, "y": 0, "side": "red", "kind": "K"},
                {"x": 3, "y": 9, "side": "black", "kind": "K"},
                {"x": 0, "y": 3, "side": "red", "kind": "P"},
            ],
            "side_to_move": "black",
        },
    ).get_json()
    assert body["valid"] is True
    assert body["fen"].split()[1] == "b"
    assert body["fen"].startswith("3k5/9/9/9/9/9/P8/9/9/4K4")


def test_invalid_position_returns_errors(client):
    body = post(
        client,
        {
            "pieces": [
                {"x": 4, "y": 5, "side": "red", "kind": "K"},
                {"x": 4, "y": 9, "side": "black", "kind": "K"},
            ],
            "side_to_move": "red",
        },
    ).get_json()
    assert body["valid"] is False
    assert any("红方" in e for e in body["errors"])


def test_empty_pieces_is_invalid(client):
    body = post(client, {"pieces": [], "side_to_move": "red"}).get_json()
    assert body["valid"] is False
    assert len(body["errors"]) >= 2


def test_kings_facing_rejected(client):
    body = post(
        client,
        {
            "pieces": [
                {"x": 4, "y": 0, "side": "red", "kind": "K"},
                {"x": 4, "y": 9, "side": "black", "kind": "K"},
            ],
            "side_to_move": "red",
        },
    ).get_json()
    assert body["valid"] is False
    assert any("照面" in e for e in body["errors"])


def test_stalemate_side_rejected(client):
    # 黑将 (4,9) 未被将军但无着法（红车控制 (3,9)/(5,9)/(4,8)）→ 行棋方困毙
    body = post(
        client,
        {
            "pieces": [
                {"x": 4, "y": 9, "side": "black", "kind": "K"},
                {"x": 3, "y": 8, "side": "red", "kind": "R"},
                {"x": 5, "y": 8, "side": "red", "kind": "R"},
                {"x": 3, "y": 0, "side": "red", "kind": "K"},
            ],
            "side_to_move": "black",
        },
    ).get_json()
    assert body["valid"] is False
    assert any("无合法着法" in e for e in body["errors"])


def test_rejects_bad_payloads(client):
    assert client.post("/api/engine/validate-position", json={}).status_code == 400
    assert post(client, {"pieces": "x"}).status_code == 400
    assert (
        post(client, {"pieces": [{"x": 9, "y": 0, "side": "red", "kind": "K"}]}).status_code
        == 400
    )
    assert (
        post(client, {"pieces": [{"x": 4, "y": 0, "side": "green", "kind": "K"}]}).status_code
        == 400
    )
    assert (
        post(client, {"pieces": [{"x": 4, "y": 0, "side": "red", "kind": "X"}]}).status_code
        == 400
    )
    assert post(client, {"pieces": [], "side_to_move": "blue"}).status_code == 400
    assert (
        post(
            client,
            {
                "pieces": [
                    {"x": 4, "y": 0, "side": "red", "kind": "K"},
                    {"x": 4, "y": 0, "side": "black", "kind": "K"},
                ]
            },
        ).status_code
        == 400
    )
    many = [
        {"x": i % 9, "y": i // 9, "side": "red", "kind": "P"} for i in range(33)
    ]
    assert post(client, {"pieces": many}).status_code == 400
