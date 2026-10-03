import os
import threading

from flask import Flask, abort, jsonify, request, send_from_directory, session
from sqlalchemy import inspect, text

from config import BASE_DIR, Config
from models import db

FRONTEND_DIST = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend", "dist"))


def _ensure_schema():
    inspector = inspect(db.engine)
    if "games" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("games")}
    if "source" not in columns:
        db.session.execute(text("ALTER TABLE games ADD COLUMN source VARCHAR(50) DEFAULT ''"))
    if "source_hash" not in columns:
        db.session.execute(text("ALTER TABLE games ADD COLUMN source_hash VARCHAR(40)"))
        db.session.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_games_source_hash ON games (source_hash)")
        )
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_games_updated_at_id "
            "ON games (updated_at DESC, id DESC)"
        )
    )
    if "game_steps" in inspector.get_table_names():
        db.session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_game_steps_collection_fen "
                "ON game_steps (collection, fen_key)"
            )
        )
        db.session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_game_steps_collection_next "
                "ON game_steps (collection, next_fen)"
            )
        )
        db.session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_game_steps_game "
                "ON game_steps (game_id)"
            )
        )
    db.session.commit()


def _backfill_variation_index(app):
    """首启回填古谱集的变着索引；已有数据则跳过。"""
    from models import Game, GameStep, db
    from routes.games import rebuild_all_game_steps

    with app.app_context():
        if db.session.query(GameStep.id).first() is not None:
            return
        if Game.query.filter(Game.category.like("古谱 · %")).first() is None:
            return
        rebuild_all_game_steps()


def _register_frontend(app):
    if not os.path.isdir(FRONTEND_DIST):
        return

    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIST, "index.html")

    @app.get("/<path:path>")
    def assets(path):
        if path == "api" or path.startswith("api/"):
            abort(404)
        full = os.path.abspath(os.path.join(FRONTEND_DIST, path))
        if full.startswith(FRONTEND_DIST + os.sep) and os.path.isfile(full):
            return send_from_directory(FRONTEND_DIST, path)
        return send_from_directory(FRONTEND_DIST, "index.html")


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    db.init_app(app)
    app.json.ensure_ascii = False

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.errorhandler(413)
    def payload_too_large(_error):
        return jsonify({"error": "图片过大，请压缩后重试"}), 413

    from routes.auth import auth_bp
    from routes.engine import engine_bp
    from routes.games import games_bp
    from routes.recognize import recognize_bp
    from routes.review import review_bp

    app.register_blueprint(games_bp, url_prefix="/api/games")
    app.register_blueprint(engine_bp, url_prefix="/api/engine")
    app.register_blueprint(review_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(recognize_bp, url_prefix="/api/recognize")

    public_api_paths = {
        "/api/health",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/me",
    }

    @app.before_request
    def _require_auth():
        if not app.config.get("AUTH_PASSWORD"):
            return None
        path = request.path
        if not path.startswith("/api/") or path in public_api_paths:
            return None
        if session.get("authenticated"):
            return None
        return jsonify({"error": "未登录"}), 401

    _register_frontend(app)

    with app.app_context():
        db.create_all()
        _ensure_schema()

    if not app.config.get("TESTING"):
        from engine import warmup

        threading.Thread(target=warmup, name="engine-warmup", daemon=True).start()
        threading.Thread(
            target=_backfill_variation_index,
            args=(app,),
            name="variation-backfill",
            daemon=True,
        ).start()

    return app


if __name__ == "__main__":
    application = create_app()
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    application.run(host=host, port=port, debug=debug)
