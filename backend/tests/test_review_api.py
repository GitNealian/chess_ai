from datetime import date, timedelta

from models import Review, ReviewLog, db


def _game(client, name="g", practice_side="both"):
    return client.post("/api/games", json={"name": name, "practice_side": practice_side}).get_json()["id"]


def _submit(client, game_id, **payload):
    body = {"mistake_count": 0, "revealed": False, "duration_ms": 1000}
    body.update(payload)
    return client.post(f"/api/review/{game_id}/submit", json=body)


def _set_due(game_id, due):
    review = Review.query.filter_by(game_id=game_id).first()
    review.due_date = due
    db.session.commit()


def test_new_game_appears_in_queue(client):
    _game(client)
    resp = client.get("/api/review/queue")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert len(items) == 1
    assert items[0]["game"]["practice_side"] == "both"
    assert items[0]["is_new"] is True


def test_queue_orders_by_due_date_ascending(app, client):
    new_game = _game(client, "new")
    expired = _game(client, "expired")
    soon = _game(client, "soon")
    _submit(client, expired)
    _submit(client, soon)
    _set_due(expired, date.today() - timedelta(days=5))
    _set_due(soon, date.today() - timedelta(days=1))

    items = client.get("/api/review/queue").get_json()["items"]
    assert [item["game"]["id"] for item in items] == [expired, soon, new_game]
    assert [item["is_new"] for item in items] == [False, False, True]
    assert items[0]["due_date"] == (date.today() - timedelta(days=5)).isoformat()


def test_submit_creates_review_and_schedules(client):
    game_id = _game(client)
    resp = _submit(client, game_id, duration_ms=5000)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["review"]["interval"] == 1
    queue = client.get("/api/review/queue").get_json()["items"]
    assert queue == []


def test_expired_review_requeues(app, client):
    game_id = _game(client)
    _submit(client, game_id)
    assert client.get("/api/review/queue").get_json()["items"] == []

    _set_due(game_id, date.today() - timedelta(days=1))
    items = client.get("/api/review/queue").get_json()["items"]
    assert len(items) == 1
    assert items[0]["game"]["id"] == game_id
    assert items[0]["is_new"] is False


def test_interval_progression(client):
    game_id = _game(client)
    intervals = [_submit(client, game_id).get_json()["review"]["interval"] for _ in range(3)]
    assert intervals == [1, 6, 16]


def test_review_logs_accumulate(app, client):
    game_id = _game(client)
    for _ in range(3):
        _submit(client, game_id)
    assert ReviewLog.query.filter_by(game_id=game_id).count() == 3


def test_submit_rejects_string_revealed(client):
    game_id = _game(client)
    resp = _submit(client, game_id, revealed="false")
    assert resp.status_code == 400


def test_submit_rejects_int_revealed(client):
    game_id = _game(client)
    resp = _submit(client, game_id, revealed=1)
    assert resp.status_code == 400


def test_submit_rejects_non_int_mistake_count(client):
    game_id = _game(client)
    resp = _submit(client, game_id, mistake_count="x")
    assert resp.status_code == 400


def test_submit_rejects_non_int_duration_ms(client):
    game_id = _game(client)
    resp = _submit(client, game_id, duration_ms="x")
    assert resp.status_code == 400


def test_submit_rejects_negative_mistake_count(client):
    game_id = _game(client)
    resp = _submit(client, game_id, mistake_count=-1)
    assert resp.status_code == 400


def test_submit_rejects_negative_duration_ms(client):
    game_id = _game(client)
    resp = _submit(client, game_id, duration_ms=-1)
    assert resp.status_code == 400


def test_submit_unknown_game_returns_404(client):
    resp = _submit(client, 9999)
    assert resp.status_code == 404


def test_submit_revealed_true_quality_is_2(client):
    game_id = _game(client)
    resp = _submit(client, game_id, revealed=True)
    assert resp.status_code == 200
    assert resp.get_json()["quality"] == 2


def test_submit_default_revealed_quality_is_5(client):
    game_id = _game(client)
    resp = _submit(client, game_id, mistake_count=0)
    assert resp.status_code == 200
    assert resp.get_json()["quality"] == 5


def test_stats(client):
    game_id = _game(client)
    _submit(client, game_id)
    stats = client.get("/api/stats").get_json()
    assert stats["total"] == 1
    assert stats["reviewed"] == 1


def test_stats_full_counts(client):
    first = _game(client, "first")
    second = _game(client, "second")
    _game(client, "third")
    for _ in range(3):
        _submit(client, first)
    _submit(client, second)

    stats = client.get("/api/stats").get_json()
    assert stats["total"] == 3
    assert stats["reviewed"] == 2
    assert stats["new"] == 1
    assert stats["due"] == 1
    assert stats["mastered"] == 1
