from flask import Blueprint, jsonify, request
from sqlalchemy.orm import joinedload

from chess_engine.board import INITIAL_FEN, Board
from chess_engine.move import Move
from chess_engine.parser import parse_moves, parse_pgn
from models import Game, db

games_bp = Blueprint("games", __name__)

VALID_SIDES = {"red", "black", "both"}
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _error(message, detail=None, step=None, status=400):
    payload = {"error": message}
    if detail is not None:
        payload["detail"] = detail
    if step is not None:
        payload["step"] = step
    return jsonify(payload), status


def _valid_move_dict(raw):
    if not isinstance(raw, dict):
        return False
    keys = ("x1", "y1", "x2", "y2")
    return all(
        isinstance(raw.get(k), int) and not isinstance(raw.get(k), bool)
        for k in keys
    )


def _validate_game_moves(initial_fen, moves):
    if not isinstance(initial_fen, str):
        return "initial_fen 必须是字符串"
    board = Board()
    try:
        board.load_fen(initial_fen)
    except ValueError as exc:
        return f"initial_fen 无效：{exc}"
    for index, raw in enumerate(moves, start=1):
        if not _valid_move_dict(raw):
            return f"第 {index} 步着法格式错误"
        move = Move.from_dict(raw)
        if move not in board.legal_moves(board.side_to_move):
            return f"第 {index} 步不是合法着法"
        board.apply_move(move)
    return None


def _parse_positive_int(raw, default, minimum, maximum=None):
    if raw is None or raw == "":
        return default, None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None, "必须是整数"
    if value < minimum:
        return None, f"不能小于 {minimum}"
    if maximum is not None and value > maximum:
        return None, f"不能大于 {maximum}"
    return value, None


@games_bp.get("")
def list_games():
    page, error = _parse_positive_int(request.args.get("page"), 1, 1)
    if error:
        return _error(f"page {error}")
    page_size, error = _parse_positive_int(
        request.args.get("page_size"), DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE
    )
    if error:
        return _error(f"page_size {error}")

    query = Game.query.options(joinedload(Game.review))
    category = request.args.get("category")
    keyword = request.args.get("keyword")
    if category:
        query = query.filter(Game.category.contains(category))
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(
            db.or_(
                Game.name.like(pattern),
                Game.event.like(pattern),
                Game.category.like(pattern),
            )
        )
    total = query.count()
    games = (
        query.order_by(Game.updated_at.desc(), Game.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return jsonify(
        {
            "items": [game.to_dict() for game in games],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@games_bp.post("")
def create_game():
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return _error("缺少棋谱名称")
    if data.get("practice_side", "both") not in VALID_SIDES:
        return _error("practice_side 只能是 red/black/both")
    if "moves" in data and not isinstance(data["moves"], list):
        return _error("moves 必须是数组")
    initial_fen = data.get("initial_fen", INITIAL_FEN)
    error = _validate_game_moves(initial_fen, data.get("moves", []))
    if error:
        return _error("棋谱着法不合法", detail=error)
    game = Game(
        name=data["name"],
        category=data.get("category", ""),
        red_player=data.get("red_player", ""),
        black_player=data.get("black_player", ""),
        event=data.get("event", ""),
        result=data.get("result", ""),
        initial_fen=initial_fen,
        practice_side=data.get("practice_side", "both"),
    )
    game.moves = data.get("moves", [])
    db.session.add(game)
    db.session.commit()
    return jsonify(game.to_dict()), 201


@games_bp.post("/parse")
def parse_preview():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    if not isinstance(text, str):
        return _error("text 必须是字符串")
    if not text.strip():
        return _error("棋谱内容为空")
    initial_fen = data.get("initial_fen", INITIAL_FEN)
    if not isinstance(initial_fen, str):
        return _error("initial_fen 必须是字符串")
    board = Board()
    try:
        board.load_fen(initial_fen)
    except ValueError as exc:
        return _error("初始局面无效", detail=str(exc))
    try:
        moves = parse_moves(board, text)
    except ValueError as exc:
        message = str(exc)
        step = None
        if "第 " in message:
            try:
                step = int(message.split("第 ")[1].split(" ")[0])
            except (IndexError, ValueError):
                step = None
        return _error("棋谱解析失败", detail=message, step=step)
    return jsonify({"moves": [move.as_dict() for move in moves]})


@games_bp.post("/import-pgn")
def import_pgn():
    data = request.get_json(silent=True) or {}
    pgn = data.get("pgn", "")
    if not isinstance(pgn, str):
        return _error("pgn 必须是字符串")
    if not pgn.strip():
        return _error("PGN 内容为空")
    if data.get("practice_side", "both") not in VALID_SIDES:
        return _error("practice_side 只能是 red/black/both")
    try:
        parsed = parse_pgn(pgn)
    except ValueError as exc:
        return _error("PGN 解析失败", detail=str(exc))
    game = Game(
        name=data.get("name") or parsed["event"] or "导入棋谱",
        category=data.get("category", ""),
        red_player=parsed["red_player"],
        black_player=parsed["black_player"],
        event=parsed["event"],
        result=parsed["result"],
        initial_fen=parsed["initial_fen"],
        practice_side=data.get("practice_side", "both"),
    )
    game.moves = [move.as_dict() for move in parsed["moves"]]
    db.session.add(game)
    db.session.commit()
    return jsonify({"created": [game.to_dict()]}), 201


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
    if "name" in data and not data["name"]:
        return _error("缺少棋谱名称")
    if "practice_side" in data and data["practice_side"] not in VALID_SIDES:
        return _error("practice_side 只能是 red/black/both")
    if "moves" in data and not isinstance(data["moves"], list):
        return _error("moves 必须是数组")
    if "moves" in data or "initial_fen" in data:
        final_fen = data.get("initial_fen", game.initial_fen)
        final_moves = data["moves"] if "moves" in data else game.moves
        error = _validate_game_moves(final_fen, final_moves)
        if error:
            return _error("棋谱着法不合法", detail=error)
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


@games_bp.post("/<int:game_id>/check-move")
def check_move(game_id):
    game = db.session.get(Game, game_id)
    if game is None:
        return _error("棋谱不存在", status=404)
    data = request.get_json(silent=True) or {}
    ply = data.get("ply", 0)
    raw = data.get("move") or {}
    moves = game.moves
    if not isinstance(ply, int) or ply < 0 or ply >= len(moves):
        return _error("步数超出范围")
    board = Board()
    try:
        board.load_fen(game.initial_fen)
    except ValueError as exc:
        return _error("初始局面无效", detail=str(exc))
    try:
        for step in moves[:ply]:
            board.apply_move(Move.from_dict(step))
    except (KeyError, TypeError, ValueError):
        return _error("棋谱着法数据有误")
    try:
        user_move = Move.from_dict(raw)
    except (KeyError, TypeError):
        return _error("着法格式错误")
    if user_move not in board.legal_moves(board.side_to_move):
        return _error("着法不合法")
    expected = moves[ply]
    correct = user_move.as_dict() == expected
    board.apply_move(user_move)
    return jsonify(
        {
            "correct": correct,
            "expected": expected,
            "fen": board.to_fen(),
            "side_to_move": board.side_to_move,
        }
    )


@games_bp.delete("/<int:game_id>")
def delete_game(game_id):
    game = db.session.get(Game, game_id)
    if game is None:
        return _error("棋谱不存在", status=404)
    db.session.delete(game)
    db.session.commit()
    return "", 204
