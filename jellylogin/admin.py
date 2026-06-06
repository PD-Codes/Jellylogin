import os
import re
import secrets
from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    abort,
)
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from .models import Category, JellyfinConfig, LinkCard, Setting, User, db
from .security import generate_csrf_token, validate_csrf

admin_bp = Blueprint("admin", __name__)

_URL_RE = re.compile(r"^https?://")


@admin_bp.before_request
def require_admin():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    if session.get("role") != "admin":
        abort(403)


def _setting(key: str, default: str = "") -> str:
    s = db.session.get(Setting, key)
    return s.value if s else default


def _set_setting(key: str, value: str):
    s = db.session.get(Setting, key)
    if s:
        s.value = value
    else:
        db.session.add(Setting(key=key, value=value))


# ── Overview ────────────────────────────────────────────────────────────────

@admin_bp.route("/")
def index():
    return render_template(
        "admin/index.html",
        total_links=LinkCard.query.count(),
        total_users=User.query.count(),
        total_categories=Category.query.count(),
        recent_links=LinkCard.query.order_by(LinkCard.created_at.desc()).limit(5).all(),
        csrf_token=generate_csrf_token(),
        username=session.get("username"),
        site_name=_setting("site_name", "DKS Media Hub"),
    )


# ── Link Cards ───────────────────────────────────────────────────────────────

@admin_bp.route("/links")
def links():
    cards = LinkCard.query.order_by(LinkCard.category_id, LinkCard.order).all()
    categories = Category.query.order_by(Category.order).all()
    return render_template(
        "admin/links.html",
        cards=cards,
        categories=categories,
        csrf_token=generate_csrf_token(),
        username=session.get("username"),
        site_name=_setting("site_name", "DKS Media Hub"),
    )


@admin_bp.route("/links/create", methods=["POST"])
def create_link():
    validate_csrf()
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()

    if not name or not url:
        flash("Name und URL sind Pflichtfelder.", "error")
        return redirect(url_for("admin.links"))
    if not _URL_RE.match(url):
        flash("URL muss mit http:// oder https:// beginnen.", "error")
        return redirect(url_for("admin.links"))

    bg_image = request.form.get("bg_image", "").strip() or None
    if bg_image and not _URL_RE.match(bg_image):
        bg_image = None

    cat_id = request.form.get("category_id") or None
    if cat_id:
        cat_id = int(cat_id)

    card = LinkCard(
        name=name,
        url=url,
        description=request.form.get("description", "").strip() or None,
        icon=request.form.get("icon", "").strip() or None,
        bg_color=request.form.get("bg_color", "#1e1b4b"),
        bg_image=bg_image,
        style=request.form.get("style", "glass"),
        open_in_new_tab=request.form.get("open_in_new_tab") == "on",
        category_id=cat_id,
        check_status=request.form.get("check_status") == "on",
        is_visible=True,
        order=LinkCard.query.count(),
    )
    db.session.add(card)
    db.session.commit()
    flash(f'Link „{name}" erstellt.', "success")
    return redirect(url_for("admin.links"))


@admin_bp.route("/links/<int:link_id>/edit", methods=["POST"])
def edit_link(link_id: int):
    validate_csrf()
    card = LinkCard.query.get_or_404(link_id)

    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()

    if not name or not url:
        flash("Name und URL sind Pflichtfelder.", "error")
        return redirect(url_for("admin.links"))
    if not _URL_RE.match(url):
        flash("URL muss mit http:// oder https:// beginnen.", "error")
        return redirect(url_for("admin.links"))

    bg_image = request.form.get("bg_image", "").strip() or None
    if bg_image and not _URL_RE.match(bg_image):
        bg_image = None

    cat_id = request.form.get("category_id") or None
    if cat_id:
        cat_id = int(cat_id)

    card.name = name
    card.url = url
    card.description = request.form.get("description", "").strip() or None
    card.icon = request.form.get("icon", "").strip() or None
    card.bg_color = request.form.get("bg_color", "#1e1b4b")
    card.bg_image = bg_image
    card.style = request.form.get("style", "glass")
    card.open_in_new_tab = request.form.get("open_in_new_tab") == "on"
    card.category_id = cat_id
    card.check_status = request.form.get("check_status") == "on"
    card.is_visible = request.form.get("is_visible") == "on"

    db.session.commit()
    flash(f'Link „{name}" aktualisiert.', "success")
    return redirect(url_for("admin.links"))


@admin_bp.route("/links/<int:link_id>/delete", methods=["POST"])
def delete_link(link_id: int):
    validate_csrf()
    card = LinkCard.query.get_or_404(link_id)
    name = card.name
    db.session.delete(card)
    db.session.commit()
    flash(f'Link „{name}" gelöscht.', "success")
    return redirect(url_for("admin.links"))


@admin_bp.route("/links/<int:link_id>/toggle", methods=["POST"])
def toggle_link(link_id: int):
    validate_csrf()
    card = LinkCard.query.get_or_404(link_id)
    card.is_visible = not card.is_visible
    db.session.commit()
    return redirect(url_for("admin.links"))


# ── Categories ───────────────────────────────────────────────────────────────

@admin_bp.route("/categories/create", methods=["POST"])
def create_category():
    validate_csrf()
    name = request.form.get("name", "").strip()
    if not name:
        flash("Name ist ein Pflichtfeld.", "error")
        return redirect(url_for("admin.links"))
    cat = Category(name=name, icon=request.form.get("icon", "").strip() or None, order=Category.query.count())
    db.session.add(cat)
    db.session.commit()
    flash(f'Kategorie „{name}" erstellt.', "success")
    return redirect(url_for("admin.links"))


@admin_bp.route("/categories/<int:cat_id>/delete", methods=["POST"])
def delete_category(cat_id: int):
    validate_csrf()
    cat = Category.query.get_or_404(cat_id)
    name = cat.name
    db.session.delete(cat)
    db.session.commit()
    flash(f'Kategorie „{name}" gelöscht (Links wurden entkategorisiert).', "success")
    return redirect(url_for("admin.links"))


# ── Users ────────────────────────────────────────────────────────────────────

@admin_bp.route("/users")
def users():
    all_users = User.query.order_by(User.created_at).all()
    return render_template(
        "admin/users.html",
        users=all_users,
        csrf_token=generate_csrf_token(),
        username=session.get("username"),
        current_user_id=session.get("user_id"),
        site_name=_setting("site_name", "DKS Media Hub"),
    )


@admin_bp.route("/users/create", methods=["POST"])
def create_user():
    validate_csrf()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "user")

    if len(username) < 3:
        flash("Benutzername muss mindestens 3 Zeichen haben.", "error")
        return redirect(url_for("admin.users"))
    if len(password) < 8:
        flash("Passwort muss mindestens 8 Zeichen haben.", "error")
        return redirect(url_for("admin.users"))
    if User.query.filter_by(username=username).first():
        flash("Benutzername bereits vergeben.", "error")
        return redirect(url_for("admin.users"))

    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
        auth_type="local",
    )
    db.session.add(user)
    db.session.commit()
    flash(f'Benutzer „{username}" erstellt.', "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/toggle", methods=["POST"])
def toggle_user(user_id: int):
    validate_csrf()
    user = User.query.get_or_404(user_id)
    if user.id == session.get("user_id"):
        flash("Du kannst deinen eigenen Account nicht deaktivieren.", "error")
        return redirect(url_for("admin.users"))
    user.is_active = not user.is_active
    db.session.commit()
    state = "aktiviert" if user.is_active else "deaktiviert"
    flash(f'Benutzer „{user.username}" {state}.', "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/role", methods=["POST"])
def change_role(user_id: int):
    validate_csrf()
    user = User.query.get_or_404(user_id)
    if user.id == session.get("user_id"):
        flash("Du kannst deine eigene Rolle nicht ändern.", "error")
        return redirect(url_for("admin.users"))
    new_role = request.form.get("role", "user")
    if new_role not in ("admin", "user"):
        abort(400)
    user.role = new_role
    db.session.commit()
    flash(f'Rolle von „{user.username}" auf {new_role} gesetzt.', "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/password", methods=["POST"])
def change_password(user_id: int):
    validate_csrf()
    user = User.query.get_or_404(user_id)
    password = request.form.get("password", "")
    if len(password) < 8:
        flash("Passwort muss mindestens 8 Zeichen haben.", "error")
        return redirect(url_for("admin.users"))
    user.password_hash = generate_password_hash(password)
    user.auth_type = "local"
    db.session.commit()
    flash(f'Passwort von „{user.username}" geändert.', "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id: int):
    validate_csrf()
    user = User.query.get_or_404(user_id)
    if user.id == session.get("user_id"):
        flash("Du kannst deinen eigenen Account nicht löschen.", "error")
        return redirect(url_for("admin.users"))
    name = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'Benutzer „{name}" gelöscht.', "success")
    return redirect(url_for("admin.users"))


# ── Jellyfin ─────────────────────────────────────────────────────────────────

@admin_bp.route("/jellyfin", methods=["GET", "POST"])
def jellyfin():
    cfg = JellyfinConfig.query.first()
    if not cfg:
        cfg = JellyfinConfig()
        db.session.add(cfg)
        db.session.commit()

    if request.method == "POST":
        validate_csrf()
        action = request.form.get("action", "save")

        if action == "test":
            from .jellyfin import JellyfinClient, JellyfinError
            try:
                client = JellyfinClient(cfg.server_url, cfg.api_key)
                info = client.test_connection()
                flash(f'Verbindung erfolgreich! Server: {info.get("ServerName", "?")} (v{info.get("Version", "?")})', "success")
            except JellyfinError as e:
                flash(str(e), "error")
            return redirect(url_for("admin.jellyfin"))

        if action == "sync":
            from .jellyfin import JellyfinClient, JellyfinError
            try:
                client = JellyfinClient(cfg.server_url, cfg.api_key)
                jf_users = client.get_users()
                created = 0
                for ju in jf_users:
                    jid = ju.get("Id")
                    jname = ju.get("Name")
                    if not jid or not jname:
                        continue
                    if not User.query.filter_by(jellyfin_user_id=jid).first() and not User.query.filter_by(username=jname).first():
                        db.session.add(User(
                            username=jname,
                            role=cfg.default_role,
                            auth_type="jellyfin",
                            jellyfin_user_id=jid,
                        ))
                        created += 1
                db.session.commit()
                flash(f'{created} neue Jellyfin-Benutzer importiert.', "success")
            except JellyfinError as e:
                flash(str(e), "error")
            return redirect(url_for("admin.jellyfin"))

        cfg.server_url = request.form.get("server_url", "").rstrip("/")
        cfg.api_key = request.form.get("api_key", "").strip()
        cfg.auto_create_users = request.form.get("auto_create_users") == "on"
        cfg.default_role = request.form.get("default_role", "user")

        allow_jf = request.form.get("allow_jellyfin_login") == "on"
        _set_setting("allow_jellyfin_login", "true" if allow_jf else "false")

        db.session.commit()
        flash("Jellyfin-Einstellungen gespeichert.", "success")
        return redirect(url_for("admin.jellyfin"))

    allow_jf = _setting("allow_jellyfin_login") == "true"
    return render_template(
        "admin/jellyfin.html",
        cfg=cfg,
        allow_jf=allow_jf,
        csrf_token=generate_csrf_token(),
        username=session.get("username"),
        site_name=_setting("site_name", "DKS Media Hub"),
    )


# ── General Settings ─────────────────────────────────────────────────────────

_ALLOWED_BG_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}
_ALLOWED_FAVICON_EXTS = {"ico", "png", "svg", "jpg", "jpeg"}
_ALLOWED_LOGO_EXTS = {"png", "jpg", "jpeg", "webp", "svg", "gif"}


def _login_logo_exists(data_dir: str) -> bool:
    for ext in _ALLOWED_LOGO_EXTS:
        if os.path.exists(os.path.join(data_dir, f"login_logo.{ext}")):
            return True
    return False


@admin_bp.route("/settings/upload-bg", methods=["POST"])
def upload_bg():
    validate_csrf()
    ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    f = request.files.get("bg_file")
    if not f or not f.filename:
        if ajax:
            return jsonify({"error": "Keine Datei ausgewählt."}), 400
        flash("Keine Datei ausgewählt.", "error")
        return redirect(url_for("admin.settings"))

    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in _ALLOWED_BG_EXTS:
        if ajax:
            return jsonify({"error": "Ungültiges Format. Erlaubt: JPG, PNG, WebP, GIF."}), 400
        flash("Ungültiges Format. Erlaubt: JPG, PNG, WebP, GIF.", "error")
        return redirect(url_for("admin.settings"))

    data_dir = current_app.config["DATA_DIR"]

    for old_ext in _ALLOWED_BG_EXTS:
        old = os.path.join(data_dir, f"background.{old_ext}")
        if os.path.exists(old):
            os.remove(old)

    f.save(os.path.join(data_dir, f"background.{ext}"))

    _set_setting("bg_type", "image")
    _set_setting("bg_value", "/bg-image")
    db.session.commit()

    if ajax:
        return jsonify({"ok": True})
    flash("Hintergrundbild hochgeladen.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/settings/upload-favicon", methods=["POST"])
def upload_favicon():
    validate_csrf()
    ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    f = request.files.get("favicon_file")
    if not f or not f.filename:
        if ajax:
            return jsonify({"error": "Keine Datei ausgewählt."}), 400
        flash("Keine Datei ausgewählt.", "error")
        return redirect(url_for("admin.settings"))

    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in _ALLOWED_FAVICON_EXTS:
        if ajax:
            return jsonify({"error": "Format nicht erlaubt. Erlaubt: ICO, PNG, SVG, JPG."}), 400
        flash("Format nicht erlaubt.", "error")
        return redirect(url_for("admin.settings"))

    data_dir = current_app.config["DATA_DIR"]
    for old_ext in _ALLOWED_FAVICON_EXTS:
        old = os.path.join(data_dir, f"favicon.{old_ext}")
        if os.path.exists(old):
            os.remove(old)

    f.save(os.path.join(data_dir, f"favicon.{ext}"))

    if ajax:
        return jsonify({"ok": True})
    flash("Favicon hochgeladen.", "success")
    return redirect(url_for("admin.settings"))


# ── Login-Page Designer ──────────────────────────────────────────────────────

@admin_bp.route("/login-design/upload-logo", methods=["POST"])
def upload_login_logo():
    validate_csrf()
    ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    f = request.files.get("logo_file")
    if not f or not f.filename:
        if ajax:
            return jsonify({"error": "Keine Datei ausgewählt."}), 400
        flash("Keine Datei ausgewählt.", "error")
        return redirect(url_for("admin.login_design"))

    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in _ALLOWED_LOGO_EXTS:
        if ajax:
            return jsonify({"error": "Format nicht erlaubt. Erlaubt: PNG, JPG, WebP, SVG, GIF."}), 400
        flash("Format nicht erlaubt.", "error")
        return redirect(url_for("admin.login_design"))

    data_dir = current_app.config["DATA_DIR"]
    for old_ext in _ALLOWED_LOGO_EXTS:
        old = os.path.join(data_dir, f"login_logo.{old_ext}")
        if os.path.exists(old):
            os.remove(old)

    f.save(os.path.join(data_dir, f"login_logo.{ext}"))
    _set_setting("login_logo_type", "image")
    _set_setting("login_logo_image", "/login-logo")
    db.session.commit()

    if ajax:
        return jsonify({"ok": True, "url": f"/login-logo?t={secrets.token_hex(4)}"})
    flash("Logo hochgeladen.", "success")
    return redirect(url_for("admin.login_design"))


@admin_bp.route("/login-design", methods=["GET", "POST"])
def login_design():
    if request.method == "POST":
        validate_csrf()
        action = request.form.get("action", "save")
        if action == "delete_logo":
            data_dir = current_app.config["DATA_DIR"]
            for ext in _ALLOWED_LOGO_EXTS:
                old = os.path.join(data_dir, f"login_logo.{ext}")
                if os.path.exists(old):
                    os.remove(old)
            _set_setting("login_logo_type", "icon")
            _set_setting("login_logo_image", "")
            db.session.commit()
            flash("Logo gelöscht.", "success")
            return redirect(url_for("admin.login_design"))

        login_keys = [
            "login_logo_type", "login_logo_icon", "login_logo_image",
            "login_title", "login_subtitle",
            "login_accent_color", "login_card_style",
            "login_bg_type", "login_bg_value", "login_bg_overlay",
        ]
        for key in login_keys:
            _set_setting(key, request.form.get(key, "").strip())
        db.session.commit()
        flash("Login-Design gespeichert.", "success")
        return redirect(url_for("admin.login_design"))

    data_dir = current_app.config["DATA_DIR"]
    return render_template(
        "admin/login_design.html",
        login_logo_type=_setting("login_logo_type", "icon"),
        login_logo_icon=_setting("login_logo_icon", "fas fa-play-circle"),
        login_logo_image=_setting("login_logo_image", ""),
        login_title=_setting("login_title", ""),
        login_subtitle=_setting("login_subtitle", "Melde dich an, um fortzufahren"),
        login_accent_color=_setting("login_accent_color", "#8b5cf6"),
        login_card_style=_setting("login_card_style", "glass"),
        login_bg_type=_setting("login_bg_type", "none"),
        login_bg_value=_setting("login_bg_value", ""),
        login_bg_overlay=_setting("login_bg_overlay", "0.5"),
        has_login_logo=_login_logo_exists(data_dir),
        site_name=_setting("site_name", "DKS Media Hub"),
        csrf_token=generate_csrf_token(),
        username=session.get("username"),
    )


@admin_bp.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        validate_csrf()
        action = request.form.get("action", "save")

        if action == "regenerate_secret":
            _set_setting("plugin_secret", secrets.token_hex(32))
            db.session.commit()
            flash("Plugin-Secret wurde neu generiert.", "success")
            return redirect(url_for("admin.settings"))

        keys = ["site_name", "site_description", "show_status", "status_cache_seconds",
                "announcement", "announcement_type",
                "bg_type", "bg_value", "bg_overlay"]
        for key in keys:
            if key in ("show_status",):
                _set_setting(key, "true" if request.form.get(key) == "on" else "false")
            else:
                _set_setting(key, request.form.get(key, "").strip())
        db.session.commit()
        flash("Einstellungen gespeichert.", "success")
        return redirect(url_for("admin.settings"))

    data_dir = current_app.config["DATA_DIR"]
    favicon_exists = any(
        os.path.exists(os.path.join(data_dir, f"favicon.{ext}"))
        for ext in _ALLOWED_FAVICON_EXTS
    )
    return render_template(
        "admin/settings.html",
        site_name=_setting("site_name", "DKS Media Hub"),
        site_description=_setting("site_description", ""),
        show_status=_setting("show_status", "true") == "true",
        status_cache_seconds=_setting("status_cache_seconds", "60"),
        announcement=_setting("announcement", ""),
        announcement_type=_setting("announcement_type", "info"),
        bg_type=_setting("bg_type", "none"),
        bg_value=_setting("bg_value", ""),
        bg_overlay=_setting("bg_overlay", "0.5"),
        plugin_secret=_setting("plugin_secret", ""),
        has_favicon=favicon_exists,
        csrf_token=generate_csrf_token(),
        username=session.get("username"),
    )
