from datetime import date

from models import Game, Review, ReviewLog, db


def test_create_game(app):
    game = Game(name="中炮对屏风马", category="中炮", moves=[], practice_side="both")
    db.session.add(game)
    db.session.commit()
    assert game.id is not None
    assert game.initial_fen


def test_game_moves_json_round_trip(app):
    game = Game(name="测试", moves=[{"x1": 1, "y1": 2, "x2": 4, "y2": 2}])
    db.session.add(game)
    db.session.commit()
    loaded = db.session.get(Game, game.id)
    assert loaded.moves[0]["x2"] == 4


def test_cascade_delete_removes_review_and_logs(app):
    game = Game(name="级联删除")
    review = Review(game=game, due_date=date.today())
    log = ReviewLog(game=game)
    db.session.add(game)
    db.session.commit()
    review_id = review.id
    log_id = log.id

    db.session.delete(game)
    db.session.commit()

    assert db.session.get(Review, review_id) is None
    assert db.session.get(ReviewLog, log_id) is None


def test_review_defaults(app):
    game = Game(name="复习默认值")
    review = Review(game=game, due_date=date.today())
    db.session.add(game)
    db.session.commit()

    assert review.ease_factor == 2.5
    assert review.interval == 0
    assert review.repetitions == 0
    assert review.lapses == 0


def test_review_log_defaults(app):
    game = Game(name="日志默认值")
    log = ReviewLog(game=game)
    db.session.add(game)
    db.session.commit()

    assert log.correct is True
    assert log.mistake_count == 0
    assert log.duration_ms == 0


def test_game_to_dict_keys(app):
    game = Game(name="键完整性")
    db.session.add(game)
    db.session.commit()

    assert set(game.to_dict().keys()) == {
        "id",
        "name",
        "category",
        "red_player",
        "black_player",
        "event",
        "result",
        "initial_fen",
        "moves",
        "practice_side",
        "favorited",
        "created_at",
        "updated_at",
        "review",
    }


def test_game_to_dict_review_none_without_review(app):
    game = Game(name="无复习")
    db.session.add(game)
    db.session.commit()

    assert game.to_dict()["review"] is None


def test_game_to_dict_review_summary(app):
    game = Game(name="有复习")
    review = Review(game=game, due_date=date(2026, 3, 1), interval=6, repetitions=2, lapses=1)
    db.session.add(game)
    db.session.commit()

    summary = game.to_dict()["review"]
    assert summary == {
        "due_date": "2026-03-01",
        "interval": 6,
        "repetitions": 2,
        "lapses": 1,
    }


def test_review_to_dict_contains_id(app):
    game = Game(name="复习字典")
    review = Review(game=game, due_date=date.today())
    db.session.add(game)
    db.session.commit()

    assert review.to_dict()["id"] == review.id
