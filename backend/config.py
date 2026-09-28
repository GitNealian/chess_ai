import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
WEIGHTS_DIR = os.environ.get("WEIGHTS_DIR") or os.path.join(BASE_DIR, "weights")


class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "chess.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD") or None
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 7 * 24 * 3600
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH") or 8 * 1024 * 1024)


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
    SECRET_KEY = "test-secret"
    AUTH_PASSWORD = None  # 显式关闭，隔离宿主环境变量
