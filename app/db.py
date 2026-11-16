"""Database access for SQLite (local runs, tests) and PostgreSQL (Supabase, when live).

The rest of the app writes plain SQL with `?` placeholders and gets rows that work
both like dicts (row["name"]) and like tuples (row[0]); this module hides the
differences between the two databases.
"""
import re
import secrets
import sqlite3
import urllib.parse
from contextlib import contextmanager

from flask import current_app, g

from . import clock

SCHEMA = """
CREATE TABLE IF NOT EXISTS houses (
    id          {ID},
    name        TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT '#b4532a',
    people      INTEGER NOT NULL DEFAULT 4,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS houses_name_unique ON houses (lower(name));

CREATE TABLE IF NOT EXISTS users (
    id              {ID},
    username        TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('member', 'chef')),
    is_admin        INTEGER NOT NULL DEFAULT 0,
    house_id        BIGINT REFERENCES houses(id) ON DELETE SET NULL,
    kitchen_alerts  INTEGER NOT NULL DEFAULT 0,
    active          INTEGER NOT NULL DEFAULT 1,
    session_version INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    last_login_at   TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    id          {ID},
    name        TEXT NOT NULL,
    icon        TEXT NOT NULL DEFAULT '🍽️',
    sort_order  INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS categories_name_unique ON categories (lower(name));

CREATE TABLE IF NOT EXISTS dishes (
    id          {ID},
    category_id BIGINT NOT NULL REFERENCES categories(id),
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image       TEXT,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id            {ID},
    house_id      BIGINT NOT NULL REFERENCES houses(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL CHECK (kind IN ('scheduled', 'urgent')),
    service_date  TEXT NOT NULL,
    meal          TEXT,
    status        TEXT NOT NULL,
    notes         TEXT NOT NULL DEFAULT '',
    needed_by     TEXT,
    eta           TEXT,
    chef_note     TEXT NOT NULL DEFAULT '',
    created_by    BIGINT REFERENCES users(id) ON DELETE SET NULL,
    updated_by    BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS orders_scheduled_unique
    ON orders (house_id, service_date, meal) WHERE kind = 'scheduled';
CREATE INDEX IF NOT EXISTS orders_by_date ON orders (service_date, kind);

CREATE TABLE IF NOT EXISTS order_items (
    id            {ID},
    order_id      BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    dish_id       BIGINT REFERENCES dishes(id) ON DELETE SET NULL,
    dish_name     TEXT NOT NULL,
    category_name TEXT NOT NULL,
    servings      INTEGER NOT NULL,
    note          TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS order_items_by_order ON order_items (order_id);

CREATE TABLE IF NOT EXISTS notifications (
    id          {ID},
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    url         TEXT NOT NULL DEFAULT '/',
    kind        TEXT NOT NULL DEFAULT 'info',
    read_at     TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS notifications_by_user ON notifications (user_id, id);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id          {ID},
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint    TEXT NOT NULL UNIQUE,
    p256dh      TEXT NOT NULL,
    auth        TEXT NOT NULL,
    user_agent  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_runs (
    key    TEXT PRIMARY KEY,
    ran_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS images (
    name        TEXT PRIMARY KEY,
    mime        TEXT NOT NULL,
    data        {BLOB} NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_failures (
    id     {ID},
    ip     TEXT NOT NULL,
    at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS login_failures_by_ip ON login_failures (ip, at);
"""

TABLES = ["houses", "users", "categories", "dishes", "orders", "order_items", "notifications",
          "push_subscriptions", "settings", "job_runs", "images", "login_failures"]

DEFAULT_HOUSES = [
    ("Mohammed", "#b4532a"),
    ("Salem", "#2f6f8f"),
    ("Ayman", "#5b7f2b"),
    ("Sabeeh", "#8a4fa3"),
]

DEFAULT_CATEGORIES = [
    ("Starters", "🥟"),
    ("Soups", "🍲"),
    ("Salads", "🥗"),
    ("Main dish", "🍛"),
    ("Desserts", "🍮"),
]

SAMPLE_DISHES = {
    "Starters": [
        ("Hummus", "Chickpea dip with tahini, lemon and olive oil"),
        ("Mutabbal", "Smoky roasted eggplant with tahini"),
        ("Vegetable samosa", "Crispy pastry with spiced potato and peas"),
        ("Cheese sambousek", "Baked pastries filled with white cheese"),
    ],
    "Soups": [
        ("Lentil soup", "Red lentils with cumin and lemon"),
        ("Chicken soup", "Chicken, vegetables and vermicelli"),
        ("Harees", "Slow-cooked wheat and meat"),
    ],
    "Salads": [
        ("Fattoush", "Mixed greens, vegetables and crispy bread"),
        ("Tabbouleh", "Parsley, bulgur, tomato and lemon"),
        ("Greek salad", "Tomato, cucumber, olives and feta"),
    ],
    "Main dish": [
        ("Chicken machboos", "Spiced rice with chicken"),
        ("Lamb biryani", "Layered basmati rice with lamb"),
        ("Grilled hammour", "Grilled fish with rice and salad"),
        ("Pasta with chicken", "Creamy pasta with grilled chicken"),
        ("Mixed grill", "Kebab, tikka and shish tawook"),
    ],
    "Desserts": [
        ("Umm Ali", "Warm bread pudding with nuts"),
        ("Kunafa", "Cheese kunafa with syrup"),
        ("Fruit salad", "Fresh seasonal fruit"),
    ],
}


def is_postgres(target: str) -> bool:
    return target.startswith(("postgres://", "postgresql://"))


def clean_postgres_url(url: str) -> str:
    """Keep only connection options libpq understands (Supabase/Vercel URLs can carry extras)."""
    parts = urllib.parse.urlsplit(url)
    keep = {"sslmode", "connect_timeout", "application_name", "options", "target_session_attrs"}
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if k in keep]
    host = parts.hostname or ""
    if not any(k == "sslmode" for k, _ in query) and host not in ("localhost", "127.0.0.1", "::1"):
        query.append(("sslmode", "require"))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


class Row(dict):
    """A result row usable as row["column"] and row[0]."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return dict.__getitem__(self, key)


def _sqlite_row(cursor, values):
    return Row(zip([d[0] for d in cursor.description], values))


def _pg_row_factory(cursor):
    names = [c.name for c in cursor.description] if cursor.description else []
    return lambda values: Row(zip(names, values))


class Connection:
    """Thin wrapper giving SQLite and PostgreSQL the same small interface."""

    def __init__(self, target):
        self.postgres = is_postgres(target)
        if self.postgres:
            import psycopg

            self.raw = psycopg.connect(
                clean_postgres_url(target), autocommit=True, prepare_threshold=None,
                connect_timeout=10, row_factory=_pg_row_factory)
        else:
            self.raw = sqlite3.connect(target, timeout=15, isolation_level=None)
            self.raw.row_factory = _sqlite_row
            self.raw.execute("PRAGMA foreign_keys = ON")
            self.raw.execute("PRAGMA busy_timeout = 15000")

    def execute(self, sql, params=()):
        if self.postgres:
            return self.raw.execute(sql.replace("?", "%s"), tuple(params) or None)
        return self.raw.execute(sql, tuple(params))

    def script(self, sql):
        if self.postgres:
            self.raw.execute(sql)
        else:
            self.raw.executescript(sql)

    @contextmanager
    def transaction(self):
        if self.postgres:
            with self.raw.transaction():
                yield self
        else:
            self.raw.execute("BEGIN IMMEDIATE")
            try:
                yield self
            except BaseException:
                self.raw.execute("ROLLBACK")
                raise
            self.raw.execute("COMMIT")

    def close(self):
        self.raw.close()


def connect(target):
    return Connection(target)


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def transaction(conn):
    """`with transaction(conn):` - all-or-nothing block of writes."""
    return conn.transaction()


def init_db(target):
    """Create tables and first-run data. Safe to run on every start, even concurrently."""
    conn = connect(target)
    try:
        if conn.postgres:
            schema = SCHEMA.format(ID="BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY", BLOB="BYTEA")
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(7731001)")  # one starter at a time
                conn.script(schema)
                for t in TABLES:
                    # Only the app's own server login may touch these tables. Supabase's public
                    # API roles get nothing: RLS on, no policies, privileges revoked.
                    conn.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
                conn.script("""
                    DO $$ BEGIN
                      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                        EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated';
                        EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated';
                      END IF;
                    END $$;""")
                _seed(conn)
        else:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.script(SCHEMA.format(ID="INTEGER PRIMARY KEY", BLOB="BLOB"))
            with conn.transaction():
                _seed(conn)
    finally:
        conn.close()


_HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?(:\d{1,5})?$")


def ensure_supabase_timer(target, host):
    """Make Supabase call https://<host>/api/cron/tick every minute (pg_cron + pg_net).

    Returns (ok, message). Never raises: if the database can't do it, the admin page says so.
    """
    host = (host or "").strip().lower()
    if not _HOST_RE.match(host):
        return False, f"Invalid site address: {host!r}"
    command = (
        "select net.http_post("
        f"url := 'https://{host}/api/cron/tick', "
        "headers := jsonb_build_object('Content-Type', 'application/json', 'Authorization', "
        "'Bearer ' || (select value from public.settings where key = 'cron_secret')), "
        "body := '{}'::jsonb, timeout_milliseconds := 25000)"
    )
    conn = connect(target)
    try:
        conn.execute("CREATE EXTENSION IF NOT EXISTS pg_net")
        conn.execute("CREATE EXTENSION IF NOT EXISTS pg_cron")
        current = conn.execute("SELECT command FROM cron.job WHERE jobname = 'stackhouse-tick'").fetchone()
        if not current or current["command"] != command:
            conn.execute("SELECT cron.schedule(?, ?, ?)", ("stackhouse-tick", "* * * * *", command))
        return True, f"Supabase calls https://{host}/api/cron/tick every minute"
    except Exception as e:  # e.g. extensions not available on this database
        return False, f"Could not start the reminder timer: {e}".strip()[:300]
    finally:
        conn.close()


def _seed(conn):
    now = clock.iso_now()
    if conn.execute("SELECT COUNT(*) FROM houses").fetchone()[0] == 0:
        for i, (name, color) in enumerate(DEFAULT_HOUSES):
            conn.execute("INSERT INTO houses (name, color, people, sort_order, created_at) VALUES (?, ?, 4, ?, ?)",
                         (name, color, i, now))
    if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        for i, (name, icon) in enumerate(DEFAULT_CATEGORIES):
            conn.execute("INSERT INTO categories (name, icon, sort_order) VALUES (?, ?, ?)", (name, icon, i))
    for key in ("secret_key", "cron_secret"):
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO NOTHING",
                     (key, secrets.token_urlsafe(32)))


def add_sample_dishes(conn):
    now = clock.iso_now()
    cats = {r["name"].lower(): r["id"] for r in conn.execute("SELECT id, name FROM categories")}
    for cat_name, dishes in SAMPLE_DISHES.items():
        cat_id = cats.get(cat_name.lower())
        if cat_id is None:
            continue
        for name, desc in dishes:
            conn.execute(
                "INSERT INTO dishes (category_id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (cat_id, name, desc, now, now),
            )
