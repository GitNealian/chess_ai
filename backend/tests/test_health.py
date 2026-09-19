def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_json_does_not_escape_chinese(app):
    with app.test_request_context():
        from flask import jsonify

        resp = jsonify({"msg": "炮二平五"})
        assert "炮二平五" in resp.get_data(as_text=True)
        assert "\\u" not in resp.get_data(as_text=True)
