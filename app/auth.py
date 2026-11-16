"""Login sessions, password hashing and permission checks."""
import re
import threading
import time
from functools import wraps

from flask import g, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")
MIN_PASSWORD = 6


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(hash_: str, password: str) -> bool:
    try:
        return check_password_hash(hash_, password)
    except Exception:
        return False


def check_new_password(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise ApiError(400, f"Password must be at least {MIN_PASSWORD} characters.")
    if len(password) > 200:
        raise ApiError(400, "Password is too long.")


def clean_username(username):
    u = str(username or "").strip().lower()
    if not USERNAME_RE.match(u):
        raise ApiError(400, "Username must be 2–32 characters: letters, numbers, dot, dash or underscore.")
    return u


def current_user():
    if "user" not in g:
        g.user = None
        uid, ver = session.get("uid"), session.get("sv")
        if uid:
            row = get_db().execute("SELECT * FROM users WHERE id = ? AND active = 1", (uid,)).fetchone()
            if row and row["session_version"] == ver:
                g.user = row
    return g.user


def login_user(row):
    session.clear()
    session.permanent = True
    session["uid"] = row["id"]
    session["sv"] = row["session_version"]
    g.user = row


def logout_user():
    session.clear()
    g.user = None


def is_kitchen(user) -> bool:
    return bool(user) and (user["role"] == "chef" or bool(user["is_admin"]))


def require_login(admin=False, kitchen=False):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                raise ApiError(401, "Please log in.")
            if admin and not user["is_admin"]:
                raise ApiError(403, "Admins only.")
            if kitchen and not is_kitchen(user):
                raise ApiError(403, "Kitchen staff only.")
            return fn(*args, **kwargs)

        return wrapper

    return deco


# --- simple in-memory login throttling ---------------------------------------
_attempts = {}
_attempts_lock = threading.Lock()
WINDOW_SECONDS = 300
MAX_FAILURES = 8


def _key():
    # remote_addr is the real client when STACKHOUSE_TRUST_PROXY enables ProxyFix behind a proxy.
    return request.remote_addr or "?"


def check_throttle():
    now = time.time()
    with _attempts_lock:
        recent = [t for t in _attempts.get(_key(), []) if now - t < WINDOW_SECONDS]
        _attempts[_key()] = recent
        if len(recent) >= MAX_FAILURES:
            raise ApiError(429, "Too many failed attempts. Try again in a few minutes.")


def record_failure():
    with _attempts_lock:
        _attempts.setdefault(_key(), []).append(time.time())


def clear_failures():
    with _attempts_lock:
        _attempts.pop(_key(), None)
