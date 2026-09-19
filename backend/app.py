import os

from flask import Flask, abort, jsonify, send_from_directory

from config import BASE_DIR, Config
from models import db

FRONTEND_DIST = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend", "dist"))


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

    from routes.games import games_bp
    from routes.review import review_bp

    app.register_blueprint(games_bp, url_prefix="/api/games")
    app.register_blueprint(review_bp, url_prefix="/api")

    _register_frontend(app)

    with app.app_context():
        db.create_all()

    return app


if __name__ == "__main__":
    application = create_app()
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    application.run(host=host, port=port, debug=debug)
