from flask import Blueprint, jsonify, request

from chess_engine.board import INITIAL_FEN
from models import Game, db

games_bp = Blueprint("games", __name__)

VALID_SIDES = {"red", "black", "both"}


def _error(message, detail=None, step=None, status=400):
    payload = {"error": message}
    if detail is not None:
        payload["detail"] = detail
    if step is not None:
        payload["step"] = step
    return jsonify(payload), status


@games_bp.get("")
def list_games():
    query = Game.query
    category = request.args.get("category")
    keyword = request.args.get("keyword")
    if category:
        query = query.filter(Game.category == category)
    if keyword:
        query = query.filter(Game.name.contains(keyword))
    games = query.order_by(Game.updated_at.desc()).all()
    return jsonify({"items": [game.to_dict() for game in games]})


@games_bp.post("")
def create_game():
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return _error("缺少棋谱名称")
    if data.get("practice_side", "both") not in VALID_SIDES:
        return _error("practice_side 只能是 red/black/both")
    game = Game(
        name=data["name"],
        category=data.get("category", ""),
        red_player=data.get("red_player", ""),
        black_player=data.get("black_player", ""),
        event=data.get("event", ""),
        result=data.get("result", ""),
        initial_fen=data.get("initial_fen", INITIAL_FEN),
        practice_side=data.get("practice_side", "both"),
    )
    game.moves = data.get("moves", [])
    db.session.add(game)
    db.session.commit()
    return jsonify(game.to_dict()), 201


@games_bp.get("/<int:game_id>")
def get_game(game_id):
    game = db.session.get(Game, game_id)
    if game is None:
        return _error("棋谱不存在", status=404)
    return jsonify(game.to_dict())


@games_bp.put("/<int:game_id>")
def update_game(game_id):
    game = db.session.get(Game, game_id)
    if game is None:
        return _error("棋谱不存在", status=404)
    data = request.get_json(silent=True) or {}
    if "practice_side" in data and data["practice_side"] not in VALID_SIDES:
        return _error("practice_side 只能是 red/black/both")
    for field in (
        "name",
        "category",
        "red_player",
        "black_player",
        "event",
        "result",
        "initial_fen",
        "practice_side",
    ):
        if field in data:
            setattr(game, field, data[field])
    if "moves" in data:
        game.moves = data["moves"]
    db.session.commit()
    return jsonify(game.to_dict())


@games_bp.delete("/<int:game_id>")
def delete_game(game_id):
    game = db.session.get(Game, game_id)
    if game is None:
        return _error("棋谱不存在", status=404)
    db.session.delete(game)
    db.session.commit()
    return "", 204
