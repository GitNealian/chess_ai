from models import Game, db


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
