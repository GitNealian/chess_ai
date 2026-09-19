import json
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

from chess_engine.board import INITIAL_FEN

db = SQLAlchemy()


def _utcnow():
    return datetime.now(timezone.utc)


class Game(db.Model):
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), default="")
    red_player = db.Column(db.String(100), default="")
    black_player = db.Column(db.String(100), default="")
    event = db.Column(db.String(200), default="")
    result = db.Column(db.String(50), default="")
    initial_fen = db.Column(db.String(200), default=INITIAL_FEN)
    _moves = db.Column("moves", db.Text, default="[]")
    practice_side = db.Column(db.String(10), default="both")
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    review = db.relationship("Review", backref="game", uselist=False, cascade="all, delete-orphan")
    logs = db.relationship("ReviewLog", backref="game", cascade="all, delete-orphan")

    @property
    def moves(self):
        return json.loads(self._moves or "[]")

    @moves.setter
    def moves(self, value):
        self._moves = json.dumps(value)

    def to_dict(self):
        review = self.review
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "red_player": self.red_player,
            "black_player": self.black_player,
            "event": self.event,
            "result": self.result,
            "initial_fen": self.initial_fen,
            "moves": self.moves,
            "practice_side": self.practice_side,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "review": None
            if review is None
            else {
                "due_date": review.due_date.isoformat(),
                "interval": review.interval,
                "repetitions": review.repetitions,
                "lapses": review.lapses,
            },
        }


class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False, unique=True)
    due_date = db.Column(db.Date, nullable=False)
    interval = db.Column(db.Integer, default=0)
    ease_factor = db.Column(db.Float, default=2.5)
    repetitions = db.Column(db.Integer, default=0)
    lapses = db.Column(db.Integer, default=0)
    last_reviewed_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "game_id": self.game_id,
            "due_date": self.due_date.isoformat(),
            "interval": self.interval,
            "ease_factor": self.ease_factor,
            "repetitions": self.repetitions,
            "lapses": self.lapses,
            "last_reviewed_at": self.last_reviewed_at.isoformat() if self.last_reviewed_at else None,
        }


class ReviewLog(db.Model):
    __tablename__ = "review_logs"

    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    reviewed_at = db.Column(db.DateTime, default=_utcnow)
    correct = db.Column(db.Boolean, default=True)
    mistake_count = db.Column(db.Integer, default=0)
    duration_ms = db.Column(db.Integer, default=0)
