from datetime import date, datetime, timezone

from flask import Blueprint, jsonify, request

from models import Game, Review, ReviewLog, db
from srs import quality_from_result, schedule

review_bp = Blueprint("review", __name__)


def _parse_int(data, key, default=0):
    if key not in data or data[key] is None:
        return default, None
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        return None, f"{key} 必须是整数"
    return value, None


def _parse_bool(data, key, default=False):
    if key not in data or data[key] is None:
        return default, None
    value = data[key]
    if not isinstance(value, bool):
        return None, f"{key} 必须是布尔值"
    return value, None


@review_bp.get("/review/queue")
def review_queue():
    today = date.today()
    games = Game.query.order_by(Game.updated_at.asc()).all()
    items = []
    for game in games:
        review = game.review
        if review is None or review.due_date <= today:
            items.append(
                {
                    "game": game.to_dict(),
                    "due_date": review.due_date.isoformat() if review else today.isoformat(),
                    "is_new": review is None,
                }
            )
    return jsonify({"items": items, "count": len(items)})


@review_bp.post("/review/<int:game_id>/submit")
def submit_review(game_id):
    game = db.session.get(Game, game_id)
    if game is None:
        return jsonify({"error": "棋谱不存在"}), 404
    data = request.get_json(silent=True) or {}
    mistake_count, error = _parse_int(data, "mistake_count")
    if error:
        return jsonify({"error": error}), 400
    duration_ms, error = _parse_int(data, "duration_ms")
    if error:
        return jsonify({"error": error}), 400
    revealed, error = _parse_bool(data, "revealed")
    if error:
        return jsonify({"error": error}), 400
    quality = quality_from_result(mistake_count, revealed)

    review = game.review
    if review is None:
        review = Review(
            game_id=game.id,
            due_date=date.today(),
            interval=0,
            ease_factor=2.5,
            repetitions=0,
            lapses=0,
        )
        db.session.add(review)
    result = schedule(
        ease_factor=review.ease_factor,
        interval=review.interval,
        repetitions=review.repetitions,
        lapses=review.lapses,
        quality=quality,
    )
    review.ease_factor = result["ease_factor"]
    review.interval = result["interval"]
    review.repetitions = result["repetitions"]
    review.lapses = result["lapses"]
    review.due_date = result["due_date"]
    review.last_reviewed_at = datetime.now(timezone.utc)

    db.session.add(
        ReviewLog(
            game_id=game.id,
            correct=(quality >= 3),
            mistake_count=mistake_count,
            duration_ms=duration_ms,
        )
    )
    db.session.commit()
    return jsonify({"quality": quality, "review": review.to_dict()})


@review_bp.get("/stats")
def stats():
    total = Game.query.count()
    review_count = Review.query.count()
    due = Review.query.filter(Review.due_date <= date.today()).count()
    new_count = total - review_count
    mastered = Review.query.filter(Review.repetitions >= 3).count()
    return jsonify(
        {
            "total": total,
            "reviewed": review_count,
            "new": new_count,
            "due": due + new_count,
            "mastered": mastered,
        }
    )
