import hashlib
import hmac
import os
import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    request,
    send_file,
    session,
)
from werkzeug.security import check_password_hash

from .models import (
    Announcement,
    AnnouncementDismissal,
    Favorite,
    LinkCard,
    Setting,
    User,
    db,
)
from .security import validate_csrf

api_bp = Blueprint("api", __name__)

_status_cache: dict = {}  # link_id -> {"status": str, "latency": int, "ts": float}

# Favicon cache lifetimes (seconds)
_FAVICON_TTL = 7 * 24 * 3600   # refresh a stored favicon after a week
_FAVICON_MISS_TTL = 24 * 3600  # retry a failed lookup after a day
_FAVICON_EXT_BY_CTYPE = {
    "image/png": "png",
    "image/x-icon": "ico",
    "image/vnd.microsoft.icon": "ico",
    "image/svg+xml": "svg",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
}
# <link rel="... icon ..." href="..."> extraction
_ICON_LINK_RE = re.compile(
    r'<link[^>]+rel=["\'][^"\']*icon[^"\']*["\'][^>]*>', re.IGNORECASE
)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)


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


# ── Favicon proxy (fetch + cache) ─────────────────────────────────────────────

@api_bp.route("/favicon/<int:link_id>")
def favicon(link_id: int):
    """Serve the target site's favicon, fetched and cached on disk.

    Falls back to the bundled default icon when the site has no reachable
    favicon. Cached per-origin so multiple cards on the same host share a file.
    """
    _require_login()
    card = LinkCard.query.get_or_404(link_id)

    cache_dir = os.path.join(current_app.config["DATA_DIR"], "favicons")
    os.makedirs(cache_dir, exist_ok=True)

    origin = _origin(card.url)
    if not origin:
        return _default_favicon()

    key = hashlib.sha1(origin.encode()).hexdigest()
    cached = _find_cached_favicon(cache_dir, key)

    if cached:
        path, age = cached
        fresh = age < (_FAVICON_MISS_TTL if path.endswith(".miss") else _FAVICON_TTL)
        if fresh:
            if path.endswith(".miss"):
                return _default_favicon()
            return send_file(path)

    # Cache miss or stale → try to (re)fetch
    result = _fetch_favicon(origin)
    if result is None:
        # Record a negative result so we do not hammer the origin
        _clear_cached_favicon(cache_dir, key)
        open(os.path.join(cache_dir, f"{key}.miss"), "w").close()
        return _default_favicon()

    content, ext = result
    _clear_cached_favicon(cache_dir, key)
    out_path = os.path.join(cache_dir, f"{key}.{ext}")
    with open(out_path, "wb") as fh:
        fh.write(content)
    return send_file(out_path)


def _origin(url: str) -> Optional[str]:
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.netloc:
            return None
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return None


def _find_cached_favicon(cache_dir: str, key: str):
    """Return (path, age_seconds) of the newest cached file for key, or None."""
    newest = None
    for fname in os.listdir(cache_dir):
        if fname == f"{key}.miss" or fname.startswith(f"{key}."):
            path = os.path.join(cache_dir, fname)
            mtime = os.path.getmtime(path)
            if newest is None or mtime > newest[1]:
                newest = (path, mtime)
    if newest is None:
        return None
    return newest[0], time.time() - newest[1]


def _clear_cached_favicon(cache_dir: str, key: str):
    for fname in os.listdir(cache_dir):
        if fname == f"{key}.miss" or fname.startswith(f"{key}."):
            try:
                os.remove(os.path.join(cache_dir, fname))
            except OSError:
                pass


def _fetch_favicon(origin: str):
    """Return (content_bytes, ext) for the site's favicon, or None on failure."""
    candidates = []
    # 1) Parse the homepage for declared icon links
    try:
        resp = requests.get(
            origin, timeout=5, allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 JellyLogin"},
        )
        if resp.ok and resp.text:
            html = resp.text[:200_000]
            for tag in _ICON_LINK_RE.findall(html):
                m = _HREF_RE.search(tag)
                if m:
                    candidates.append(urljoin(resp.url, m.group(1)))
    except requests.RequestException:
        pass

    # 2) Always try the conventional /favicon.ico location last
    candidates.append(urljoin(origin + "/", "favicon.ico"))

    seen = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        got = _download_image(url)
        if got:
            return got
    return None


def _download_image(url: str):
    """Download url and return (bytes, ext) if it is a non-empty image."""
    try:
        resp = requests.get(
            url, timeout=5, allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 JellyLogin"},
        )
    except requests.RequestException:
        return None
    if not resp.ok or not resp.content:
        return None

    ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
    ext = _FAVICON_EXT_BY_CTYPE.get(ctype)
    if ext is None:
        # Fall back to the URL extension for servers with a wrong/missing type
        tail = urlparse(url).path.rsplit(".", 1)[-1].lower()
        ext = tail if tail in ("png", "ico", "svg", "jpg", "jpeg", "gif", "webp") else None
    if ext is None:
        return None
    if ext == "jpeg":
        ext = "jpg"
    # Guard against HTML error pages served with a 200
    if resp.content[:15].lstrip().lower().startswith(b"<!doctype") or \
       resp.content[:6].lower() == b"<html>":
        return None
    return resp.content, ext


def _default_favicon():
    path = os.path.join(
        current_app.root_path, "static", "img", "favicon-default.svg"
    )
    return send_file(path, mimetype="image/svg+xml")


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


@api_bp.route("/announcements/reorder", methods=["POST"])
def reorder_announcements():
    _require_login()
    if session.get("role") != "admin":
        abort(403)
    validate_csrf()

    data = request.get_json(silent=True)
    if not data or "order" not in data:
        abort(400)

    for idx, ann_id in enumerate(data["order"]):
        ann = db.session.get(Announcement, ann_id)
        if ann:
            ann.order = idx
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/announcements/<int:ann_id>/dismiss", methods=["POST"])
def dismiss_announcement(ann_id: int):
    """Mark an announcement as dismissed for the current user."""
    _require_login()
    validate_csrf()

    ann = db.session.get(Announcement, ann_id)
    if not ann:
        abort(404)

    uid = session["user_id"]
    existing = AnnouncementDismissal.query.filter_by(
        user_id=uid, announcement_id=ann_id
    ).first()
    if existing:
        existing.dismissed_at = datetime.utcnow()
    else:
        db.session.add(
            AnnouncementDismissal(user_id=uid, announcement_id=ann_id)
        )
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/favorites/<int:link_id>/toggle", methods=["POST"])
def toggle_favorite(link_id: int):
    """Add or remove a link from the current user's favourites."""
    _require_login()
    validate_csrf()

    card = db.session.get(LinkCard, link_id)
    if not card:
        abort(404)

    uid = session["user_id"]
    fav = Favorite.query.filter_by(user_id=uid, link_id=link_id).first()
    if fav:
        db.session.delete(fav)
        favorited = False
    else:
        db.session.add(Favorite(user_id=uid, link_id=link_id))
        favorited = True
    db.session.commit()
    return jsonify({"ok": True, "favorited": favorited})


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
