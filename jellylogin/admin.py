import json
import os
import re
import secrets
from datetime import datetime

from flask import (
    Blueprint,
    Response,
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

from .models import (
    ANNOUNCEMENT_SEVERITIES,
    Announcement,
    AnnouncementDismissal,
    Category,
    Favorite,
    JellyfinConfig,
    LinkCard,
    Setting,
    User,
    db,
)

# Settings keys that are never exported/imported (secret material)
_CONFIG_SECRET_KEYS = {"plugin_secret", "setup_complete"}
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
        use_favicon=request.form.get("use_favicon") == "on",
        admin_only=request.form.get("admin_only") == "on",
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
    card.use_favicon = request.form.get("use_favicon") == "on"
    card.admin_only = request.form.get("admin_only") == "on"
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
    cat = Category(
        name=name,
        icon=request.form.get("icon", "").strip() or None,
        admin_only=request.form.get("admin_only") == "on",
        order=Category.query.count(),
    )
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


# ── Announcements ────────────────────────────────────────────────────────────

@admin_bp.route("/announcements")
def announcements():
    items = Announcement.query.order_by(
        Announcement.order, Announcement.created_at.desc()
    ).all()
    return render_template(
        "admin/announcements.html",
        announcements=items,
        severities=ANNOUNCEMENT_SEVERITIES,
        now=datetime.utcnow(),
        csrf_token=generate_csrf_token(),
        username=session.get("username"),
        site_name=_setting("site_name", "DKS Media Hub"),
    )


def _clean_severity(value: str) -> str:
    value = (value or "").strip().lower()
    return value if value in ANNOUNCEMENT_SEVERITIES else "info"


def _parse_dt(value: str):
    """Parse an <input type=datetime-local> value into a datetime, or None."""
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


@admin_bp.route("/announcements/create", methods=["POST"])
def create_announcement():
    validate_csrf()
    title = request.form.get("title", "").strip()
    if not title:
        flash("Titel ist ein Pflichtfeld.", "error")
        return redirect(url_for("admin.announcements"))

    item = Announcement(
        title=title[:120],
        body=request.form.get("body", "").strip() or None,
        severity=_clean_severity(request.form.get("severity")),
        is_active=request.form.get("is_active") == "on",
        start_at=_parse_dt(request.form.get("start_at")),
        end_at=_parse_dt(request.form.get("end_at")),
        order=Announcement.query.count(),
    )
    db.session.add(item)
    db.session.commit()
    flash(f'Ankündigung „{title}" erstellt.', "success")
    return redirect(url_for("admin.announcements"))


@admin_bp.route("/announcements/<int:ann_id>/edit", methods=["POST"])
def edit_announcement(ann_id: int):
    validate_csrf()
    item = Announcement.query.get_or_404(ann_id)
    title = request.form.get("title", "").strip()
    if not title:
        flash("Titel ist ein Pflichtfeld.", "error")
        return redirect(url_for("admin.announcements"))

    item.title = title[:120]
    item.body = request.form.get("body", "").strip() or None
    item.severity = _clean_severity(request.form.get("severity"))
    item.is_active = request.form.get("is_active") == "on"
    item.start_at = _parse_dt(request.form.get("start_at"))
    item.end_at = _parse_dt(request.form.get("end_at"))
    db.session.commit()
    flash(f'Ankündigung „{title}" aktualisiert.', "success")
    return redirect(url_for("admin.announcements"))


@admin_bp.route("/announcements/<int:ann_id>/toggle", methods=["POST"])
def toggle_announcement(ann_id: int):
    validate_csrf()
    item = Announcement.query.get_or_404(ann_id)
    item.is_active = not item.is_active
    db.session.commit()
    return redirect(url_for("admin.announcements"))


@admin_bp.route("/announcements/<int:ann_id>/delete", methods=["POST"])
def delete_announcement(ann_id: int):
    validate_csrf()
    item = Announcement.query.get_or_404(ann_id)
    title = item.title
    db.session.delete(item)
    db.session.commit()
    flash(f'Ankündigung „{title}" gelöscht.', "success")
    return redirect(url_for("admin.announcements"))


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


@admin_bp.route("/favicon-cache/clear", methods=["POST"])
def clear_favicon_cache():
    """Delete all cached site favicons; they are re-fetched on next view."""
    validate_csrf()
    cache_dir = os.path.join(current_app.config["DATA_DIR"], "favicons")
    removed = 0
    if os.path.isdir(cache_dir):
        for fname in os.listdir(cache_dir):
            try:
                os.remove(os.path.join(cache_dir, fname))
                removed += 1
            except OSError:
                pass
    flash(f"Favicon-Cache geleert ({removed} Dateien).", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/links/<int:link_id>/favicon-refresh", methods=["POST"])
def refresh_link_favicon(link_id: int):
    """Drop the cached favicon for one link's origin so it is re-fetched."""
    import hashlib
    from .api import _origin

    validate_csrf()
    card = LinkCard.query.get_or_404(link_id)
    cache_dir = os.path.join(current_app.config["DATA_DIR"], "favicons")
    origin = _origin(card.url)
    if origin and os.path.isdir(cache_dir):
        key = hashlib.sha1(origin.encode()).hexdigest()
        for fname in os.listdir(cache_dir):
            if fname == f"{key}.miss" or fname.startswith(f"{key}."):
                try:
                    os.remove(os.path.join(cache_dir, fname))
                except OSError:
                    pass
    flash(f'Favicon für „{card.name}" wird neu geladen.', "success")
    return redirect(url_for("admin.links"))


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


# ── Config Import / Export ───────────────────────────────────────────────────

@admin_bp.route("/config/export")
def export_config():
    """Download all links, categories, announcements and settings as JSON."""
    data = {
        "version": 1,
        "exported_at": datetime.utcnow().isoformat(),
        "categories": [c.to_dict() for c in Category.query.order_by(Category.order).all()],
        "links": [l.to_dict() for l in LinkCard.query.order_by(LinkCard.order).all()],
        "announcements": [
            a.to_dict() for a in Announcement.query.order_by(Announcement.order).all()
        ],
        "settings": {
            s.key: s.value
            for s in Setting.query.all()
            if s.key not in _CONFIG_SECRET_KEYS
        },
    }
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
    return Response(
        payload,
        mimetype="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="jellylogin-config-{stamp}.json"'
        },
    )


@admin_bp.route("/config/import", methods=["POST"])
def import_config():
    """Replace links, categories and announcements from an uploaded JSON file."""
    validate_csrf()
    f = request.files.get("config_file")
    if not f or not f.filename:
        flash("Keine Datei ausgewählt.", "error")
        return redirect(url_for("admin.settings"))

    try:
        data = json.loads(f.read().decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        flash("Ungültige JSON-Datei.", "error")
        return redirect(url_for("admin.settings"))

    if not isinstance(data, dict):
        flash("Unerwartetes Dateiformat.", "error")
        return redirect(url_for("admin.settings"))

    try:
        # Clear dependent per-user data and existing content
        AnnouncementDismissal.query.delete()
        Favorite.query.delete()
        LinkCard.query.delete()
        Category.query.delete()
        Announcement.query.delete()
        db.session.flush()

        # Recreate categories, keeping a map from exported id -> new object
        cat_map = {}
        for c in data.get("categories", []):
            cat = Category(
                name=(c.get("name") or "Unbenannt")[:80],
                icon=c.get("icon") or None,
                order=int(c.get("order", 0) or 0),
                admin_only=bool(c.get("admin_only", False)),
            )
            db.session.add(cat)
            db.session.flush()
            if c.get("id") is not None:
                cat_map[c["id"]] = cat

        # Recreate links, remapping their category reference
        for l in data.get("links", []):
            if not l.get("name") or not l.get("url"):
                continue
            old_cat = l.get("category_id")
            new_cat = cat_map.get(old_cat)
            db.session.add(LinkCard(
                name=l["name"][:80],
                url=l["url"][:512],
                description=(l.get("description") or None),
                icon=(l.get("icon") or None),
                bg_color=l.get("bg_color", "#1e1b4b"),
                bg_image=(l.get("bg_image") or None),
                style=l.get("style", "glass"),
                open_in_new_tab=bool(l.get("open_in_new_tab", True)),
                category_id=new_cat.id if new_cat else None,
                order=int(l.get("order", 0) or 0),
                check_status=bool(l.get("check_status", True)),
                is_visible=bool(l.get("is_visible", True)),
                use_favicon=bool(l.get("use_favicon", True)),
                admin_only=bool(l.get("admin_only", False)),
            ))

        # Recreate announcements
        for a in data.get("announcements", []):
            if not a.get("title"):
                continue
            db.session.add(Announcement(
                title=a["title"][:120],
                body=(a.get("body") or None),
                severity=_clean_severity(a.get("severity")),
                is_active=bool(a.get("is_active", True)),
                order=int(a.get("order", 0) or 0),
                start_at=_parse_iso(a.get("start_at")),
                end_at=_parse_iso(a.get("end_at")),
            ))

        # Upsert settings (skipping secret keys)
        for key, value in (data.get("settings") or {}).items():
            if key in _CONFIG_SECRET_KEYS:
                continue
            _set_setting(key, "" if value is None else str(value))

        db.session.commit()
    except Exception as exc:  # noqa: BLE001 — surface any import failure to the user
        db.session.rollback()
        flash(f"Import fehlgeschlagen: {exc}", "error")
        return redirect(url_for("admin.settings"))

    flash("Konfiguration importiert.", "success")
    return redirect(url_for("admin.settings"))


def _parse_iso(value):
    """Parse an ISO datetime string from an export file, or None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


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
                "bg_type", "bg_value", "bg_overlay",
                "show_latest_media", "latest_media_count", "latest_media_cache_seconds"]
        for key in keys:
            if key in ("show_status", "show_latest_media"):
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
        bg_type=_setting("bg_type", "none"),
        bg_value=_setting("bg_value", ""),
        bg_overlay=_setting("bg_overlay", "0.5"),
        show_latest_media=_setting("show_latest_media", "false") == "true",
        latest_media_count=_setting("latest_media_count", "8"),
        latest_media_cache_seconds=_setting("latest_media_cache_seconds", "300"),
        plugin_secret=_setting("plugin_secret", ""),
        has_favicon=favicon_exists,
        csrf_token=generate_csrf_token(),
        username=session.get("username"),
    )
