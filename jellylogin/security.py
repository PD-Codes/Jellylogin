import hmac
import secrets
import time
from collections import defaultdict
from flask import session, request, abort

_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 900  # 15 Minuten

_attempts: dict = defaultdict(list)


def generate_csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def validate_csrf():
    token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    session_token = session.get("csrf_token", "")
    if not token or not session_token:
        abort(403)
    if not hmac.compare_digest(token.encode(), session_token.encode()):
        abort(403)


def check_rate_limit(ip: str) -> bool:
    now = time.time()
    _attempts[ip] = [t for t in _attempts[ip] if now - t < _WINDOW_SECONDS]
    return len(_attempts[ip]) >= _MAX_ATTEMPTS


def record_failed_attempt(ip: str):
    _attempts[ip].append(time.time())


def clear_attempts(ip: str):
    _attempts.pop(ip, None)


def remaining_lockout(ip: str) -> int:
    now = time.time()
    attempts = [t for t in _attempts.get(ip, []) if now - t < _WINDOW_SECONDS]
    if not attempts or len(attempts) < _MAX_ATTEMPTS:
        return 0
    oldest = min(attempts)
    return max(0, int(_WINDOW_SECONDS - (now - oldest)))


def init_security(app):
    @app.after_request
    def add_headers(response):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com "
            "https://fonts.googleapis.com; "
            "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com; "
            "img-src 'self' data: https: http:; "
            "connect-src 'self';"
        )
        response.headers["Content-Security-Policy"] = csp
        return response
