import functools
from datetime import datetime

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .models import JellyfinConfig, LinkCard, Category, Setting, User, db
from .security import (
    check_rate_limit,
    clear_attempts,
    generate_csrf_token,
    record_failed_attempt,
    remaining_lockout,
    validate_csrf,
)

auth_bp = Blueprint("auth", __name__)


def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        if session.get("role") != "admin":
            flash("Kein Administratorzugriff.", "error")
            return redirect(url_for("auth.dashboard"))
        return f(*args, **kwargs)
    return wrapper


def _get_setting(key: str, default: str = "") -> str:
    s = db.session.get(Setting, key)
    return s.value if s else default


@auth_bp.route("/setup", methods=["GET", "POST"])
def setup():
    if _get_setting("setup_complete") == "true":
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        validate_csrf()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        errors = []
        if len(username) < 3:
            errors.append("Benutzername muss mindestens 3 Zeichen haben.")
        if len(password) < 8:
            errors.append("Passwort muss mindestens 8 Zeichen haben.")
        if password != password2:
            errors.append("Passwörter stimmen nicht überein.")
        if User.query.filter_by(username=username).first():
            errors.append("Benutzername bereits vergeben.")

        if not errors:
            user = User(
                username=username,
                password_hash=generate_password_hash(password),
                role="admin",
                auth_type="local",
            )
            db.session.add(user)
            s = db.session.get(Setting, "setup_complete")
            s.value = "true"
            db.session.commit()
            flash("Setup abgeschlossen. Bitte anmelden.", "success")
            return redirect(url_for("auth.login"))

        for err in errors:
            flash(err, "error")

    return render_template("setup.html", csrf_token=generate_csrf_token())


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if _get_setting("setup_complete") != "true":
        return redirect(url_for("auth.setup"))
    if "user_id" in session:
        return redirect(url_for("auth.dashboard"))

    if request.method == "POST":
        validate_csrf()
        ip = request.remote_addr or "unknown"

        if check_rate_limit(ip):
            mins = remaining_lockout(ip) // 60 + 1
            flash(f"Zu viele Fehlversuche. Bitte in {mins} Minute(n) erneut versuchen.", "error")
            return render_template(
                "login.html",
                csrf_token=generate_csrf_token(),
                site_name=_get_setting("site_name", "DKS Media Hub"),
            )

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        user = User.query.filter_by(username=username, is_active=True).first()
        authenticated = False

        if user and user.auth_type == "local" and user.password_hash:
            if check_password_hash(user.password_hash, password):
                authenticated = True

        elif _get_setting("allow_jellyfin_login") == "true":
            jf_cfg = JellyfinConfig.query.first()
            if jf_cfg and jf_cfg.server_url:
                try:
                    from .jellyfin import JellyfinClient, JellyfinAuthError, JellyfinError
                    client = JellyfinClient(jf_cfg.server_url, jf_cfg.api_key)
                    jf_data = client.authenticate(username, password)
                    jf_user_id = jf_data.get("User", {}).get("Id")
                    if jf_user_id:
                        if user and user.auth_type == "jellyfin":
                            authenticated = True
                        elif jf_cfg.auto_create_users and not user:
                            user = User(
                                username=username,
                                role=jf_cfg.default_role,
                                auth_type="jellyfin",
                                jellyfin_user_id=jf_user_id,
                            )
                            db.session.add(user)
                            db.session.commit()
                            authenticated = True
                except Exception:
                    pass

        if authenticated and user:
            clear_attempts(ip)
            session.permanent = remember
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            user.last_login = datetime.utcnow()
            db.session.commit()
            return redirect(url_for("auth.dashboard"))

        record_failed_attempt(ip)
        flash("Ungültige Anmeldedaten.", "error")

    return render_template(
        "login.html",
        csrf_token=generate_csrf_token(),
        site_name=_get_setting("site_name", "DKS Media Hub"),
        login_logo_type=_get_setting("login_logo_type", "icon"),
        login_logo_icon=_get_setting("login_logo_icon", "fas fa-play-circle"),
        login_logo_image=_get_setting("login_logo_image", ""),
        login_title=_get_setting("login_title", ""),
        login_subtitle=_get_setting("login_subtitle", "Melde dich an, um fortzufahren"),
        login_accent_color=_get_setting("login_accent_color", "#8b5cf6"),
        login_card_style=_get_setting("login_card_style", "glass"),
        login_bg_type=_get_setting("login_bg_type", "none"),
        login_bg_value=_get_setting("login_bg_value", ""),
        login_bg_overlay=_get_setting("login_bg_overlay", "0.5"),
    )


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/dashboard")
@login_required
def dashboard():
    categories = Category.query.order_by(Category.order).all()
    uncategorized = (
        LinkCard.query
        .filter_by(category_id=None, is_visible=True)
        .order_by(LinkCard.order)
        .all()
    )
    announcement = _get_setting("announcement", "")
    announcement_type = _get_setting("announcement_type", "info")
    show_status = _get_setting("show_status", "true") == "true"

    return render_template(
        "dashboard.html",
        categories=categories,
        uncategorized=uncategorized,
        site_name=_get_setting("site_name", "DKS Media Hub"),
        site_description=_get_setting("site_description", ""),
        show_status=show_status,
        announcement=announcement,
        announcement_type=announcement_type,
        role=session.get("role"),
        username=session.get("username"),
    )
