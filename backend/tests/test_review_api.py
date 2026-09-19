from datetime import date

from models import Game, Review, db


def _game(client, name="g", practice_side="both"):
    return client.post("/api/games", json={"name": name, "practice_side": practice_side}).get_json()["id"]


def test_new_game_appears_in_queue(client):
    _game(client)
    resp = client.get("/api/review/queue")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert len(items) == 1
    assert items[0]["game"]["practice_side"] == "both"
    assert items[0]["is_new"] is True


def test_submit_creates_review_and_schedules(client):
    game_id = _game(client)
    resp = client.post(
        f"/api/review/{game_id}/submit",
        json={"mistake_count": 0, "revealed": False, "duration_ms": 5000},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["review"]["interval"] == 1
    queue = client.get("/api/review/queue").get_json()["items"]
    assert queue == []


def test_stats(client):
    game_id = _game(client)
    client.post(f"/api/review/{game_id}/submit", json={"mistake_count": 0, "revealed": False})
    stats = client.get("/api/stats").get_json()
    assert stats["total"] == 1
    assert stats["reviewed"] == 1
