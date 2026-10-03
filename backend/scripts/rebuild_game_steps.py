"""全量重建棋谱变着索引（game_steps）。

用法：
    cd backend && .venv/bin/python scripts/rebuild_game_steps.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from flask import Flask

from config import Config
from models import db
from routes.games import rebuild_all_game_steps


def main():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        rebuild_all_game_steps()
        print("变着索引重建完成")


if __name__ == "__main__":
    main()
