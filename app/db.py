"""SQLite storage: connection handling, schema and first-run seed data."""
import sqlite3

from flask import current_app, g

from . import clock

SCHEMA = """
CREATE TABLE IF NOT EXISTS houses (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    color       TEXT NOT NULL DEFAULT '#b4532a',
    people      INTEGER NOT NULL DEFAULT 4,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name            TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('member', 'chef')),
    is_admin        INTEGER NOT NULL DEFAULT 0,
    house_id        INTEGER REFERENCES houses(id) ON DELETE SET NULL,
    kitchen_alerts  INTEGER NOT NULL DEFAULT 0,
    active          INTEGER NOT NULL DEFAULT 1,
    session_version INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    last_login_at   TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    icon        TEXT NOT NULL DEFAULT '🍽️',
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dishes (
    id          INTEGER PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    image       TEXT,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY,
    house_id      INTEGER NOT NULL REFERENCES houses(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL CHECK (kind IN ('scheduled', 'urgent')),
    service_date  TEXT NOT NULL,
    meal          TEXT,
    status        TEXT NOT NULL,
    notes         TEXT NOT NULL DEFAULT '',
    needed_by     TEXT,
    eta           TEXT,
    chef_note     TEXT NOT NULL DEFAULT '',
    created_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS orders_scheduled_unique
    ON orders(house_id, service_date, meal) WHERE kind = 'scheduled';
CREATE INDEX IF NOT EXISTS orders_by_date ON orders(service_date, kind);

CREATE TABLE IF NOT EXISTS order_items (
    id            INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    dish_id       INTEGER REFERENCES dishes(id) ON DELETE SET NULL,
    dish_name     TEXT NOT NULL,
    category_name TEXT NOT NULL,
    servings      INTEGER NOT NULL,
    note          TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS order_items_by_order ON order_items(order_id);

CREATE TABLE IF NOT EXISTS notifications (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    url         TEXT NOT NULL DEFAULT '/',
    kind        TEXT NOT NULL DEFAULT 'info',
    read_at     TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS notifications_by_user ON notifications(user_id, id);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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
"""

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


def connect(path):
    conn = sqlite3.connect(path, timeout=15, isolation_level=None)  # autocommit; explicit BEGIN for transactions
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


class transaction:
    """`with transaction(conn):` - BEGIN IMMEDIATE ... COMMIT / ROLLBACK."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, *_):
        self.conn.execute("ROLLBACK" if exc_type else "COMMIT")
        return False


def init_db(path):
    conn = connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        now = clock.iso_now()
        if conn.execute("SELECT COUNT(*) FROM houses").fetchone()[0] == 0:
            for i, (name, color) in enumerate(DEFAULT_HOUSES):
                conn.execute(
                    "INSERT INTO houses (name, color, people, sort_order, created_at) VALUES (?, ?, 4, ?, ?)",
                    (name, color, i, now),
                )
        if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            for i, (name, icon) in enumerate(DEFAULT_CATEGORIES):
                conn.execute(
                    "INSERT INTO categories (name, icon, sort_order) VALUES (?, ?, ?)", (name, icon, i)
                )
    finally:
        conn.close()


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
