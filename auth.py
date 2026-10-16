"""
auth.py - authentication and authorization helpers for the Flask API.

Design
  * Passwords: werkzeug.security.generate_password_hash / check_password_hash.
    Login verifies the entered password against the stored hash (it is never
    re-hashed). Hashes written by an earlier release (bcrypt) keep working and
    are transparently upgraded to the werkzeug format on the next sign-in.
  * Sign-in: email address + password. Emails are normalised (trim + lower case)
    before lookup so casing/spacing never creates a second account.
  * Sessions: opaque random token in an HttpOnly cookie. Only its SHA-256 hash
    is stored server-side (auth_sessions), so a database leak cannot be replayed
    as a live session. Logout deletes the row -> the cookie is dead immediately.
  * CSRF: a per-session token must be sent in the X-CSRF-Token header on every
    state-changing request. Combined with SameSite=Lax cookies this blocks
    cross-site form posts.
  * Authorization: @require_auth and @require_roles(...). Roles are read from
    the server-side session, never from client input.

Configuration (environment variables, see .env.example)
  SECRET_KEY            Flask secret (used for signing/no cache helpers)
  SESSION_COOKIE_NAME   cookie name, default "loan_session"
  SESSION_LIFETIME_HOURS  session TTL, default 12
  COOKIE_SECURE         "1"/"true" to add the Secure flag (enable in production)
"""
from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from functools import wraps

from flask import g, jsonify, request

import db

COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "loan_session")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes")
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Login/register cannot carry a CSRF token yet (no session exists).
# /api/score is a read-only preview that stores nothing.
CSRF_EXEMPT = {"/api/auth/login", "/api/auth/register", "/api/score"}


# --------------------------------------------------------------- request -----
def load_current_user() -> None:
    """Populate flask.g.user / g.session from the session cookie (or None)."""
    token = request.cookies.get(COOKIE_NAME)
    session = db.get_session(token) if token else None
    g.session = session
    g.user = ({k: session[k] for k in ("user_id", "username", "email", "role", "full_name")}
              if session else None)


def current_user():
    return getattr(g, "user", None)


def current_csrf() -> str | None:
    session = getattr(g, "session", None)
    return session["csrf_token"] if session else None


def csrf_ok() -> bool:
    session = getattr(g, "session", None)
    if not session:
        return False
    sent = request.headers.get("X-CSRF-Token", "")
    return bool(sent) and hmac.compare_digest(sent, session["csrf_token"])


def public_user(user: dict) -> dict:
    """Serialize an account for the client (never includes the password hash)."""
    return {"user_id": user["user_id"], "username": user["username"],
            "email": user.get("email"), "role": user["role"],
            "full_name": user.get("full_name")}


# ---------------------------------------------------------------- cookies ----
def set_session_cookie(response, token: str, expires_at: str):
    try:
        ttl = int((datetime.fromisoformat(expires_at) - datetime.now(timezone.utc)).total_seconds())
    except ValueError:
        ttl = db.DEFAULT_SESSION_HOURS * 3600
    response.set_cookie(COOKIE_NAME, token, max_age=max(ttl, 60), httponly=True,
                        samesite="Lax", secure=COOKIE_SECURE, path="/")
    return response


def clear_session_cookie(response):
    response.delete_cookie(COOKIE_NAME, httponly=True, samesite="Lax",
                           secure=COOKIE_SECURE, path="/")
    return response


def session_token() -> str | None:
    return request.cookies.get(COOKIE_NAME)


# ------------------------------------------------------------- decorators ----
def require_auth(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return jsonify(error="Authentication required."), 401
        return view(*args, **kwargs)
    return wrapper


def require_roles(*roles):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify(error="Authentication required."), 401
            if user["role"] not in roles:
                audit("unauthorized", f"{request.method} {request.path} (role={user['role']})")
                return jsonify(error="You do not have permission to do that."), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator


# ------------------------------------------------------------------ audit ----
def audit(action: str, detail: str = "", user_id: int | None = None, actor: str | None = None):
    """Record a security-relevant event. Never pass passwords or tokens here."""
    user = current_user()
    if user_id is None and user:
        user_id = user["user_id"]
    if actor is None and user:
        actor = user["username"]
    db.log_audit(user_id=user_id, actor=actor, action=action, detail=detail,
                 ip=request.remote_addr if request else None)
