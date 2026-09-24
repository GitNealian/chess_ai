import hmac

from flask import Blueprint, current_app, jsonify, request, session

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
def login():
    password = current_app.config.get("AUTH_PASSWORD")
    if not password:
        return jsonify({"error": "认证未启用"}), 400
    data = request.get_json(silent=True) or {}
    candidate = data.get("password", "")
    if not isinstance(candidate, str) or not hmac.compare_digest(candidate, password):
        return jsonify({"error": "密码错误"}), 401
    session.permanent = True
    session["authenticated"] = True
    return jsonify({"ok": True})


@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@auth_bp.get("/me")
def me():
    password = current_app.config.get("AUTH_PASSWORD")
    return jsonify(
        {
            "auth_required": bool(password),
            "authenticated": bool(password) and bool(session.get("authenticated")),
        }
    )
