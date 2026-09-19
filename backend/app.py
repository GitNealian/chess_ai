from flask import Flask, jsonify

from config import Config
from models import db


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

    return app


if __name__ == "__main__":
    application = create_app()
    with application.app_context():
        db.create_all()
    application.run(debug=True, port=5000)
