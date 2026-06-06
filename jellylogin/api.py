import hmac
import time
from typing import Optional

import requests
from flask import Blueprint, jsonify, request, session, abort
from werkzeug.security import check_password_hash

from .models import LinkCard, Setting, User, db
from .security import validate_csrf

api_bp = Blueprint("api", __name__)

_status_cache: dict = {}  # link_id -> {"status": str, "latency": int, "ts": float}


def _cache_ttl() -> int:
    s = db.session.get(Setting, "status_cache_seconds")
    try:
        return int(s.value) if s else 60
    except (ValueError, TypeError):
        return 60


def _require_login():
    if "user_id" not in session:
        abort(401)


@api_bp.route("/links")
def get_links():
    _require_login()
    cards = LinkCard.query.filter_by(is_visible=True).order_by(LinkCard.category_id, LinkCard.order).all()
    return jsonify([c.to_dict() for c in cards])


@api_bp.route("/status/<int:link_id>")
def get_status(link_id: int):
    _require_login()
    show = db.session.get(Setting, "show_status")
    if not show or show.value != "true":
        return jsonify({"status": "disabled"})

    card = LinkCard.query.get_or_404(link_id)
    if not card.check_status:
        return jsonify({"status": "disabled"})

    now = time.time()
    cached = _status_cache.get(link_id)
    if cached and now - cached["ts"] < _cache_ttl():
        return jsonify({"status": cached["status"], "latency": cached["latency"]})

    status, latency = _check_url(card.url)
    _status_cache[link_id] = {"status": status, "latency": latency, "ts": now}
    return jsonify({"status": status, "latency": latency})


def _check_url(url: str) -> tuple:
    try:
        start = time.monotonic()
        resp = requests.head(url, timeout=4, allow_redirects=True)
        latency = int((time.monotonic() - start) * 1000)
        if resp.status_code < 500:
            return "online", latency
        return "offline", latency
    except requests.ConnectionError:
        return "offline", 0
    except requests.Timeout:
        return "offline", 4000
    except Exception:
        return "unknown", 0


@api_bp.route("/links/reorder", methods=["POST"])
def reorder_links():
    _require_login()
    if session.get("role") != "admin":
        abort(403)
    validate_csrf()

    data = request.get_json(silent=True)
    if not data or "order" not in data:
        abort(400)

    order: list = data["order"]
    for idx, link_id in enumerate(order):
        card = db.session.get(LinkCard, link_id)
        if card:
            card.order = idx
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/plugin/auth", methods=["POST"])
def plugin_auth():
    """Called by the Jellyfin plugin to validate credentials."""
    secret = request.headers.get("X-Plugin-Secret", "")
    expected = _get_plugin_secret()
    if not expected or not hmac.compare_digest(secret.encode(), expected.encode()):
        abort(401)

    data = request.get_json(silent=True)
    if not data:
        abort(400)

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"authenticated": False}), 401

    user = User.query.filter_by(username=username, is_active=True).first()
    if user and user.auth_type == "local" and user.password_hash:
        if check_password_hash(user.password_hash, password):
            return jsonify({
                "authenticated": True,
                "username": user.username,
                "role": user.role,
            })

    return jsonify({"authenticated": False}), 401


def _get_plugin_secret() -> str:
    s = db.session.get(Setting, "plugin_secret")
    return s.value if s else ""


@api_bp.route("/search")
def search():
    _require_login()
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify([])
    cards = LinkCard.query.filter_by(is_visible=True).all()
    results = [
        c.to_dict() for c in cards
        if q in c.name.lower() or (c.description and q in c.description.lower())
    ]
    return jsonify(results)
