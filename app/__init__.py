"""Stack House kitchen ordering app.

Runs two ways:
- locally / on a normal server:  python run.py   (SQLite file in ./data, reminders from a background thread)
- on Vercel:  index.py + DATABASE_URL pointing at Supabase Postgres (reminders from Supabase pg_cron)
"""
import logging
import os
import urllib.parse
from datetime import timedelta

from flask import Flask, abort, redirect, request, send_from_directory

from . import db, notify, settings
from .api import bp as api_bp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = os.path.join(ROOT, "public")  # page, styles, scripts, icons (Vercel serves these from its CDN)


def _env_flag(name, default=False):
    value = os.environ.get(name)
    return default if value is None else value == "1"


def resolve_database(test_config, env, on_vercel):
    """The database to use: a Postgres URL (Supabase) or a local SQLite file path."""
    database = (test_config.get("DATABASE") or env.get("DATABASE_URL")
                or env.get("POSTGRES_URL") or "").strip().strip('"').strip("'")
    password = env.get("DATABASE_PASSWORD", "").strip()
    if password and "[YOUR-PASSWORD]" in database:
        # Supabase shows the address with a placeholder; the password is pasted separately.
        database = database.replace("[YOUR-PASSWORD]", urllib.parse.quote(password, safe=""))
    if "[YOUR-PASSWORD]" in database:
        raise RuntimeError("DATABASE_URL still contains [YOUR-PASSWORD]. Add DATABASE_PASSWORD in Vercel.")
    if database:
        return database
    if on_vercel:
        raise RuntimeError("DATABASE_URL is not set. Add the Supabase connection string in Vercel.")
    data_dir = test_config.get("DATA_DIR") or env.get("STACKHOUSE_DATA") or os.path.join(ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "stackhouse.db")


def create_app(test_config=None):
    test_config = test_config or {}
    on_vercel = os.environ.get("VERCEL") == "1"
    database = resolve_database(test_config, os.environ, on_vercel)

    db.init_db(database)
    conn = db.connect(database)
    try:
        notify.ensure_vapid_keys(conn)
        secret_key = settings.get_value(conn, "secret_key")
        # Live on Vercel + Supabase: have the database call us every minute for reminders.
        host = os.environ.get("STACKHOUSE_PUBLIC_HOST") or (
            os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") if os.environ.get("VERCEL_ENV") == "production" else None)
        if db.is_postgres(database) and host:
            ok, message = db.ensure_supabase_timer(database, host)
            settings.set_value(conn, "timer_setup", message)
            logging.getLogger("stackhouse").log(logging.INFO if ok else logging.WARNING, message)
    finally:
        conn.close()

    app = Flask(__name__, static_folder=os.path.join(PUBLIC, "static"), static_url_path="/static")
    app.config.update(
        DATABASE=database,
        SECRET_KEY=secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_env_flag("STACKHOUSE_SECURE_COOKIES", on_vercel),
        SESSION_COOKIE_NAME="stackhouse",
        PERMANENT_SESSION_LIFETIME=timedelta(days=90),
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,
        SEND_FILE_MAX_AGE_DEFAULT=0,
        VAPID_SUBJECT=os.environ.get("STACKHOUSE_VAPID_SUBJECT", "https://stackhouse.alsalemkuwait.com"),
        SCHEDULER=not on_vercel,  # on Vercel, Supabase pg_cron calls /api/cron/tick instead
        PUSH_SYNC=on_vercel,      # serverless: send push notifications before the request ends
        PUSH_SENDER=None,
        TRUST_PROXY=_env_flag("STACKHOUSE_TRUST_PROXY", on_vercel),
        FORCE_HTTPS=_env_flag("STACKHOUSE_FORCE_HTTPS", on_vercel),
    )
    app.config.update(test_config)

    if app.config["TRUST_PROXY"]:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.teardown_appcontext(db.close_db)
    app.register_blueprint(api_bp)

    @app.before_request
    def force_https():
        # Behind the hosting proxy, send anyone who typed http:// to the https:// address.
        if app.config["FORCE_HTTPS"] and request.scheme == "http" and request.path != "/healthz":
            return redirect(request.url.replace("http://", "https://", 1), code=301)

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
        db.get_db().execute("SELECT 1").fetchone()
        return {"ok": True}

    # Locally Flask serves the files in public/; on Vercel the CDN serves them before Flask is reached.
    @app.get("/")
    def index():
        return send_from_directory(PUBLIC, "index.html", max_age=0)

    @app.get("/sw.js")
    def service_worker():
        return send_from_directory(PUBLIC, "sw.js", max_age=0)

    @app.get("/manifest.webmanifest")
    def manifest():
        return send_from_directory(PUBLIC, "manifest.webmanifest", mimetype="application/manifest+json")

    @app.get("/uploads/<name>")
    def uploads(name):
        row = db.get_db().execute("SELECT mime, data FROM images WHERE name = ?", (name,)).fetchone()
        if not row:
            abort(404)
        resp = app.response_class(bytes(row["data"]), mimetype=row["mime"])
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"  # names are never reused
        return resp

    if app.config["SCHEDULER"]:
        from . import scheduler
        scheduler.start(app)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return app
