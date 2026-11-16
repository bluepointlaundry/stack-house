"""Stack House kitchen ordering app."""
import logging
import os
import secrets
from datetime import timedelta

from flask import Flask, abort, redirect, request, send_from_directory

from . import db, notify, scheduler
from .api import bp as api_bp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def _secret_key(data_dir):
    path = os.path.join(data_dir, "secret_key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


def create_app(test_config=None):
    test_config = test_config or {}
    data_dir = test_config.get("DATA_DIR") or os.environ.get("STACKHOUSE_DATA") or os.path.join(ROOT, "data")
    os.makedirs(os.path.join(data_dir, "uploads"), exist_ok=True)

    app = Flask(__name__, static_folder=STATIC, static_url_path="/static")
    app.config.update(
        DATA_DIR=data_dir,
        DB_PATH=os.path.join(data_dir, "stackhouse.db"),
        UPLOAD_DIR=os.path.join(data_dir, "uploads"),
        SECRET_KEY=_secret_key(data_dir),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("STACKHOUSE_SECURE_COOKIES") == "1",
        SESSION_COOKIE_NAME="stackhouse",
        PERMANENT_SESSION_LIFETIME=timedelta(days=90),
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,
        SEND_FILE_MAX_AGE_DEFAULT=0,
        VAPID_SUBJECT=os.environ.get("STACKHOUSE_VAPID_SUBJECT", "mailto:admin@example.com"),
        SCHEDULER=True,
        PUSH_SENDER=None,
        TRUST_PROXY=os.environ.get("STACKHOUSE_TRUST_PROXY") == "1",
        FORCE_HTTPS=os.environ.get("STACKHOUSE_FORCE_HTTPS") == "1",
    )
    app.config.update(test_config)

    if app.config["TRUST_PROXY"]:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    @app.before_request
    def force_https():
        # Behind the hosting proxy, send anyone who typed http:// to the https:// address.
        if app.config["FORCE_HTTPS"] and request.scheme == "http" and request.path != "/healthz":
            return redirect(request.url.replace("http://", "https://", 1), code=301)

    db.init_db(app.config["DB_PATH"])
    conn = db.connect(app.config["DB_PATH"])
    try:
        notify.ensure_vapid_keys(conn)
    finally:
        conn.close()

    app.teardown_appcontext(db.close_db)
    app.register_blueprint(api_bp)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if app.config["FORCE_HTTPS"]:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
        )
        return resp

    @app.get("/healthz")
    def healthz():
        conn = db.connect(app.config["DB_PATH"])
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        return {"ok": True}

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html", max_age=0)

    @app.get("/sw.js")
    def service_worker():
        resp = send_from_directory(STATIC, "sw.js", max_age=0)
        resp.headers["Service-Worker-Allowed"] = "/"
        return resp

    @app.get("/manifest.webmanifest")
    def manifest():
        return send_from_directory(STATIC, "manifest.webmanifest", mimetype="application/manifest+json")

    @app.get("/uploads/<name>")
    def uploads(name):
        if "/" in name or "\\" in name or name.startswith("."):
            abort(404)
        return send_from_directory(app.config["UPLOAD_DIR"], name, max_age=365 * 24 * 3600)

    if app.config["SCHEDULER"]:
        scheduler.start(app)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return app
