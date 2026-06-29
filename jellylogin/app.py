import os
import secrets

from flask import Flask, redirect, url_for, session, jsonify, send_file, abort

from .models import db, Setting
from .security import init_security

_BG_EXTENSIONS = ("jpg", "jpeg", "png", "webp", "gif")
_FAVICON_EXTENSIONS = ("ico", "png", "svg", "jpg", "jpeg")
_LOGIN_LOGO_EXTENSIONS = ("png", "jpg", "jpeg", "webp", "svg", "gif")


def create_app() -> Flask:
    app = Flask(__name__)

    data_dir = os.path.abspath(
        os.environ.get("JELLYLOGIN_DATA", os.path.join(os.getcwd(), "data"))
    )
    os.makedirs(data_dir, exist_ok=True)

    secret_key_file = os.path.join(data_dir, ".secret_key")
    if os.path.exists(secret_key_file):
        with open(secret_key_file) as f:
            secret_key = f.read().strip()
    else:
        secret_key = secrets.token_hex(32)
        with open(secret_key_file, "w") as f:
            f.write(secret_key)

    app.config.update(
        SECRET_KEY=secret_key,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{os.path.join(data_dir, 'jellylogin.db')}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_SECURE=os.environ.get("JELLYLOGIN_HTTPS", "0") == "1",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=86400 * 7,
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,  # 10 MB upload limit
        DATA_DIR=data_dir,
    )

    db.init_app(app)
    init_security(app)

    from .auth import auth_bp
    from .admin import admin_bp
    from .api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()
        _run_migrations()
        _seed_defaults()

        # Favicon cache directory for fetched site favicons
        os.makedirs(os.path.join(data_dir, "favicons"), exist_ok=True)

    @app.context_processor
    def inject_site_bg():
        from .models import Setting
        def _gs(key, default=""):
            s = db.session.get(Setting, key)
            return s.value if s else default
        has_upload = _bg_image_path(data_dir) is not None
        has_favicon = _favicon_path(data_dir) is not None
        return {
            "site_bg_type":      _gs("bg_type", "none"),
            "site_bg_value":     _gs("bg_value", ""),
            "site_bg_overlay":   _gs("bg_overlay", "0.5"),
            "has_bg_upload":     has_upload,
            "has_favicon":       has_favicon,
        }

    @app.route("/")
    def index():
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return redirect(url_for("auth.dashboard"))

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "version": "1.0.0"})

    @app.route("/favicon.ico")
    def favicon():
        path = _favicon_path(data_dir)
        if path:
            ext = path.rsplit(".", 1)[-1].lower()
            mime = {
                "ico": "image/x-icon", "png": "image/png",
                "svg": "image/svg+xml", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            }.get(ext, "image/x-icon")
            return send_file(path, mimetype=mime)
        abort(404)

    @app.route("/login-logo")
    def serve_login_logo():
        path = _login_logo_path(data_dir)
        if path:
            return send_file(path)
        abort(404)

    @app.route("/bg-image")
    def serve_bg_image():
        path = _bg_image_path(data_dir)
        if path:
            return send_file(path)
        abort(404)

    @app.errorhandler(413)
    def too_large(e):
        from flask import flash, redirect, url_for
        flash("Datei zu groß. Maximum: 10 MB.", "error")
        return redirect(url_for("admin.settings"))

    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template
        return render_template("error.html", code=403, message="Kein Zugriff."), 403

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template("error.html", code=404, message="Seite nicht gefunden."), 404

    return app


def _bg_image_path(data_dir: str):
    """Return path of the stored background image, or None."""
    for ext in _BG_EXTENSIONS:
        p = os.path.join(data_dir, f"background.{ext}")
        if os.path.exists(p):
            return p
    return None


def _favicon_path(data_dir: str):
    """Return path of the stored favicon, or None."""
    for ext in _FAVICON_EXTENSIONS:
        p = os.path.join(data_dir, f"favicon.{ext}")
        if os.path.exists(p):
            return p
    return None


def _login_logo_path(data_dir: str):
    """Return path of the stored login-page logo, or None."""
    for ext in _LOGIN_LOGO_EXTENSIONS:
        p = os.path.join(data_dir, f"login_logo.{ext}")
        if os.path.exists(p):
            return p
    return None


def _run_migrations():
    """Apply lightweight schema migrations for existing SQLite databases.

    SQLAlchemy's create_all() creates missing tables but never alters existing
    ones, so new columns on already-created tables are added here by hand.
    """
    from sqlalchemy import text, inspect

    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    def _cols(table):
        return {c["name"] for c in inspector.get_columns(table)}

    def _add(table, ddl):
        db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
        db.session.commit()

    # link_cards: favicon + role-visibility columns
    if "link_cards" in tables:
        cols = _cols("link_cards")
        if "use_favicon" not in cols:
            _add("link_cards", "use_favicon BOOLEAN NOT NULL DEFAULT 1")
        if "admin_only" not in cols:
            _add("link_cards", "admin_only BOOLEAN NOT NULL DEFAULT 0")

    # categories: role-visibility column
    if "categories" in tables and "admin_only" not in _cols("categories"):
        _add("categories", "admin_only BOOLEAN NOT NULL DEFAULT 0")

    # announcements: scheduling window columns
    if "announcements" in tables:
        cols = _cols("announcements")
        if "start_at" not in cols:
            _add("announcements", "start_at DATETIME")
        if "end_at" not in cols:
            _add("announcements", "end_at DATETIME")


def _seed_defaults():
    defaults = {
        "site_name": "DKS Media Hub",
        "site_description": "Dein zentraler Medien-Launchpad",
        "show_status": "true",
        "status_cache_seconds": "60",
        "allow_jellyfin_login": "false",
        "setup_complete": "false",
        "plugin_secret": "",
        "bg_type": "none",
        "bg_value": "",
        "bg_overlay": "0.5",
        # Jellyfin "recently added" section on the dashboard
        "show_latest_media": "false",
        "latest_media_count": "8",
        "latest_media_cache_seconds": "300",
        # Login-page designer
        "login_logo_type": "icon",
        "login_logo_icon": "fas fa-play-circle",
        "login_logo_image": "",
        "login_title": "",
        "login_subtitle": "Melde dich an, um fortzufahren",
        "login_accent_color": "#8b5cf6",
        "login_card_style": "glass",
        "login_bg_type": "none",
        "login_bg_value": "",
        "login_bg_overlay": "0.5",
    }
    for key, value in defaults.items():
        if db.session.get(Setting, key) is None:
            db.session.add(Setting(key=key, value=value))
    db.session.commit()

    ps = db.session.get(Setting, "plugin_secret")
    if ps and not ps.value:
        ps.value = secrets.token_hex(32)
        db.session.commit()


def main():
    import argparse
    from waitress import serve

    parser = argparse.ArgumentParser(description="DKS JellyLogin — Media Hub")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000, help="Port (default: 5000)")
    parser.add_argument("--data", default=None, help="Data directory")
    args = parser.parse_args()

    if args.data:
        os.environ["JELLYLOGIN_DATA"] = args.data

    app = create_app()
    print(f"DKS JellyLogin läuft auf  http://{args.host}:{args.port}")
    print(f"Daten-Verzeichnis:         {os.path.abspath(os.environ.get('JELLYLOGIN_DATA', 'data'))}")
    serve(app, host=args.host, port=args.port, threads=4)
