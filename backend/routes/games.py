from flask import Blueprint, jsonify, request
from sqlalchemy.orm import joinedload

from chess_engine.board import INITIAL_FEN, Board
from chess_engine.move import Move
from chess_engine.notation import move_to_chinese
from chess_engine.parser import parse_moves, parse_pgn
from chess_engine.variation import (
    VARIATION_MIN_PLY,
    build_steps,
    collection_of,
    fen_key,
)
from models import Game, GameActivity, GameStep, db, _utcnow

games_bp = Blueprint("games", __name__)

VALID_SIDES = {"red", "black", "both"}
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
COLLECTION_PREFIX = "古谱 · "


def _rebuild_variation_index(game):
    """重建单个棋谱的变着索引；非棋谱集则清空其索引后返回。"""
    db.session.query(GameStep).filter_by(game_id=game.id).delete()
    collection = collection_of(game.category)
    if collection is None:
        return
    for row in build_steps(game):
        db.session.add(GameStep(game_id=game.id, collection=collection, **row))


def rebuild_all_game_steps():
    """全量重建所有棋谱集的变着索引（启动回填 / 手动脚本）。"""
    db.session.query(GameStep).delete()
    query = Game.query.filter(Game.category.like(f"{COLLECTION_PREFIX}%"))
    for game in query.yield_per(200):
        collection = collection_of(game.category)
        if collection is None:
            continue
        for row in build_steps(game):
            db.session.add(GameStep(game_id=game.id, collection=collection, **row))
    db.session.commit()


def _collection_children(collection, fen, threshold=VARIATION_MIN_PLY):
    """某局面在某棋谱集内的所有分支与是否构成变着入口。"""
    key = fen_key(fen)
    from_rows = GameStep.query.filter_by(collection=collection, fen_key=key).all()
    to_rows = GameStep.query.filter_by(collection=collection, next_fen=key).all()

    plies_by_game = {}
    for row in from_rows:
        plies_by_game[row.game_id] = min(plies_by_game.get(row.game_id, row.ply), row.ply)
    for row in to_rows:
        reached = row.ply + 1
        plies_by_game[row.game_id] = min(plies_by_game.get(row.game_id, reached), reached)

    if not plies_by_game:
        return {"fen": fen, "branchable": False, "plies": None, "branches": []}

    games = {
        game.id: game for game in Game.query.filter(Game.id.in_(set(plies_by_game))).all()
    }

    grouped = {}
    for row in from_rows:
        if not row.move or row.move.count(",") != 3:
            continue
        node = grouped.setdefault(
            row.move, {"to_fen": row.next_fen, "game_ids": set(), "end_ids": set()}
        )
        node["game_ids"].add(row.game_id)
        game = games.get(row.game_id)
        if game is not None and row.ply + 1 == len(game.moves):
            node["end_ids"].add(row.game_id)

    board = Board()
    board.load_fen(fen)
    branches = []
    for move_text, node in grouped.items():
        coords = [int(part) for part in move_text.split(",")]
        try:
            chinese = move_to_chinese(board, Move(*coords))
        except Exception:
            chinese = ""
        branches.append(
            {
                "move": {
                    "x1": coords[0],
                    "y1": coords[1],
                    "x2": coords[2],
                    "y2": coords[3],
                    "chinese": chinese,
                },
                "to_fen": node["to_fen"],
                "games": [
                    {"id": gid, "name": games[gid].name}
                    for gid in sorted(node["game_ids"])
                    if gid in games
                ],
                "end_games": [
                    {"id": gid, "name": games[gid].name}
                    for gid in sorted(node["end_ids"])
                    if gid in games
                ],
            }
        )
    branches.sort(key=lambda item: (-len(item["games"]), item["move"]["x1"], item["move"]["y1"]))

    plies = list(plies_by_game.values())
    branchable = len(grouped) >= 2 and all(ply > threshold for ply in plies)
    return {
        "fen": fen,
        "branchable": branchable,
        "plies": {"min": min(plies), "max": max(plies)},
        "branches": branches,
    }


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
    scope = request.args.get("scope")
    if scope == "collection":
        collection = request.args.get("collection")
        if not collection:
            return _error("scope=collection 需要 collection 参数")
        query = query.filter(Game.category == f"{COLLECTION_PREFIX}{collection}")
    elif scope == "tournament":
        query = query.filter(
            db.or_(Game.category.is_(None), ~Game.category.like(f"{COLLECTION_PREFIX}%")),
            Game.event.is_not(None),
            Game.event != "",
            Game.event != "NA",
        )
    elif scope == "other":
        query = query.filter(
            db.or_(Game.category.is_(None), ~Game.category.like(f"{COLLECTION_PREFIX}%")),
            db.or_(Game.event.is_(None), Game.event == "", Game.event == "NA"),
        )
    elif scope == "event":
        event = request.args.get("event")
        if not event:
            return _error("scope=event 需要 event 参数")
        query = query.filter(
            db.or_(Game.category.is_(None), ~Game.category.like(f"{COLLECTION_PREFIX}%")),
            Game.event == event,
        )
    elif scope == "recent":
        query = query.join(GameActivity, GameActivity.game_id == Game.id).filter(
            GameActivity.last_opened_at.is_not(None)
        )
    elif scope == "favorite":
        query = query.join(GameActivity, GameActivity.game_id == Game.id).filter(
            GameActivity.favorited_at.is_not(None)
        )
    elif scope:
        return _error("scope 只能是 collection/event/tournament/other/recent/favorite")

    sort = request.args.get("sort")
    if scope == "recent":
        order = (GameActivity.last_opened_at.desc(), Game.id.desc())
    elif scope == "favorite":
        order = (GameActivity.favorited_at.desc(), Game.id.desc())
    elif sort == "created_desc":
        order = (Game.created_at.desc(), Game.id.desc())
    elif sort:
        return _error("sort 只支持 created_desc")
    else:
        order = (Game.updated_at.desc(), Game.id.desc())

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
        query.order_by(*order)
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


@games_bp.get("/collections")
def list_collections():
    page, error = _parse_positive_int(request.args.get("page"), 1, 1)
    if error:
        return _error(f"page {error}")
    page_size, error = _parse_positive_int(
        request.args.get("page_size"), DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE
    )
    if error:
        return _error(f"page_size {error}")

    name = db.func.replace(Game.category, COLLECTION_PREFIX, "").label("name")
    grouped = (
        db.session.query(name, db.func.count().label("count"))
        .filter(Game.category.like(f"{COLLECTION_PREFIX}%"))
        .group_by(name)
        .subquery()
    )
    total = db.session.query(db.func.count()).select_from(grouped).scalar()
    rows = (
        db.session.query(grouped.c.name, grouped.c.count)
        .order_by(grouped.c.count.desc(), grouped.c.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return jsonify(
        {
            "items": [{"name": n, "count": c} for n, c in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@games_bp.post("/collections/children")
def collection_children():
    data = request.get_json(silent=True) or {}
    collection = data.get("collection")
    fen = data.get("fen")
    if not isinstance(collection, str) or not collection:
        return _error("collection 不能为空")
    if not isinstance(fen, str) or not fen:
        return _error("fen 不能为空")
    board = Board()
    try:
        board.load_fen(fen)
    except ValueError as exc:
        return _error("fen 无效", detail=str(exc))
    return jsonify(_collection_children(collection, board.to_fen()))


@games_bp.get("/events")
def list_events():
    page, error = _parse_positive_int(request.args.get("page"), 1, 1)
    if error:
        return _error(f"page {error}")
    page_size, error = _parse_positive_int(
        request.args.get("page_size"), DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE
    )
    if error:
        return _error(f"page_size {error}")

    name = Game.event.label("name")
    grouped = (
        db.session.query(name, db.func.count().label("count"))
        .filter(
            db.or_(Game.category.is_(None), ~Game.category.like(f"{COLLECTION_PREFIX}%")),
            Game.event.is_not(None),
            Game.event != "",
            Game.event != "NA",
        )
        .group_by(name)
        .subquery()
    )
    total = db.session.query(db.func.count()).select_from(grouped).scalar()
    rows = (
        db.session.query(grouped.c.name, grouped.c.count)
        .order_by(grouped.c.count.desc(), grouped.c.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return jsonify(
        {
            "items": [{"name": n, "count": c} for n, c in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


def _activity_for(game_id):
    activity = db.session.get(GameActivity, game_id)
    if activity is None:
        activity = GameActivity(game_id=game_id)
        db.session.add(activity)
    return activity


@games_bp.post("/<int:game_id>/open")
def open_game(game_id):
    if db.session.get(Game, game_id) is None:
        return _error("棋谱不存在", status=404)
    activity = _activity_for(game_id)
    activity.last_opened_at = _utcnow()
    db.session.commit()
    return jsonify(
        {
            "last_opened_at": activity.last_opened_at.isoformat(),
            "favorited": bool(activity.favorited_at),
        }
    )


@games_bp.post("/<int:game_id>/favorite")
def favorite_game(game_id):
    if db.session.get(Game, game_id) is None:
        return _error("棋谱不存在", status=404)
    activity = _activity_for(game_id)
    activity.favorited_at = None if activity.favorited_at else _utcnow()
    db.session.commit()
    return jsonify(
        {
            "favorited": bool(activity.favorited_at),
            "favorited_at": activity.favorited_at.isoformat() if activity.favorited_at else None,
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
    _rebuild_variation_index(game)
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
    _rebuild_variation_index(game)
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
    if "moves" in data or "initial_fen" in data or "category" in data:
        _rebuild_variation_index(game)
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
    db.session.query(GameStep).filter_by(game_id=game_id).delete()
    db.session.delete(game)
    db.session.commit()
    return "", 204
