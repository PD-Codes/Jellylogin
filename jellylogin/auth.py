import functools
import time
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

from .models import (
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

# Server-side cache for the Jellyfin "recently added" section
_latest_media_cache = {"items": None, "ts": 0.0}
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
    uid = session["user_id"]
    is_admin = session.get("role") == "admin"

    # Categories: hide admin-only categories from non-admins
    categories = Category.query.order_by(Category.order).all()
    if not is_admin:
        categories = [c for c in categories if not c.admin_only]

    uncategorized = (
        LinkCard.query
        .filter_by(category_id=None, is_visible=True)
        .order_by(LinkCard.order)
        .all()
    )
    if not is_admin:
        uncategorized = [c for c in uncategorized if not c.admin_only]

    show_status = _get_setting("show_status", "true") == "true"

    # Favourites — pinned cards for this user (respecting visibility + role)
    fav_ids = {f.link_id for f in Favorite.query.filter_by(user_id=uid).all()}
    favorites = []
    if fav_ids:
        fav_cards = (
            LinkCard.query
            .filter(LinkCard.id.in_(fav_ids), LinkCard.is_visible.is_(True))
            .order_by(LinkCard.order)
            .all()
        )
        favorites = [c for c in fav_cards if _card_visible_to(c, is_admin)]

    # Announcements — live ones, minus those this user dismissed after last edit
    now = datetime.utcnow()
    live = [
        a for a in Announcement.query
        .order_by(Announcement.order, Announcement.created_at.desc())
        .all()
        if a.is_live(now)
    ]
    dismissed = {
        d.announcement_id: d.dismissed_at
        for d in AnnouncementDismissal.query.filter_by(user_id=uid).all()
    }
    announcements = [
        a for a in live
        if not (a.id in dismissed and dismissed[a.id] >= a.updated_at)
    ]

    return render_template(
        "dashboard.html",
        categories=categories,
        uncategorized=uncategorized,
        favorites=favorites,
        favorite_ids=fav_ids,
        latest_media=_get_latest_media(),
        site_name=_get_setting("site_name", "DKS Media Hub"),
        site_description=_get_setting("site_description", ""),
        show_status=show_status,
        announcements=announcements,
        is_admin=is_admin,
        csrf_token=generate_csrf_token(),
        role=session.get("role"),
        username=session.get("username"),
    )


def _card_visible_to(card, is_admin: bool) -> bool:
    """Whether a card is visible to the current user (role + its category)."""
    if card.admin_only and not is_admin:
        return False
    if card.category and card.category.admin_only and not is_admin:
        return False
    return True


def _get_latest_media():
    """Return cached Jellyfin 'recently added' items, refreshing on TTL.

    Each item is a dict with name, subtitle, image_url and link_url.
    Returns an empty list if disabled, unconfigured, or unreachable.
    """
    if _get_setting("show_latest_media", "false") != "true":
        return []

    try:
        ttl = int(_get_setting("latest_media_cache_seconds", "300"))
    except ValueError:
        ttl = 300
    if _latest_media_cache["items"] is not None and \
            time.time() - _latest_media_cache["ts"] < ttl:
        return _latest_media_cache["items"]

    cfg = JellyfinConfig.query.first()
    if not cfg or not cfg.server_url or not cfg.api_key:
        return []

    try:
        count = int(_get_setting("latest_media_count", "8"))
    except ValueError:
        count = 8

    items = []
    try:
        from .jellyfin import JellyfinClient, JellyfinError
        client = JellyfinClient(cfg.server_url, cfg.api_key)
        base = cfg.server_url.rstrip("/")
        for it in client.get_latest(count):
            iid = it.get("Id")
            if not iid:
                continue
            tag = (it.get("ImageTags") or {}).get("Primary")
            image_url = (
                f"{base}/Items/{iid}/Images/Primary?fillHeight=330&quality=90"
                + (f"&tag={tag}" if tag else "")
            ) if tag else None
            name = it.get("SeriesName") or it.get("Name") or "?"
            subtitle = it.get("Name") if it.get("SeriesName") else it.get("Type", "")
            items.append({
                "name": name,
                "subtitle": subtitle,
                "image_url": image_url,
                "link_url": f"{base}/web/#/details?id={iid}",
            })
    except Exception:
        # On any failure, fall back to the last good cache (or empty)
        return _latest_media_cache["items"] or []

    _latest_media_cache["items"] = items
    _latest_media_cache["ts"] = time.time()
    return items
