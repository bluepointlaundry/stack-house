"""Bulk menu import from pasted text.

Format (what people naturally type):

    Appetizers
    1. chicken and mushroom pot pie
    2. fried shrimps

    Main Dishes
    1. chicken machbous
    chicken fajitas wrap          <- unnumbered lines still count as dishes

A line is a *section* when the next non-empty line is a numbered dish, when it ends
with ":" or starts with "#", or when it is the very first line. Everything else is a
dish of the current section. "Name - description" adds a description.
"""
import re

from . import clock
from .auth import ApiError
from .db import transaction

NUMBERED = re.compile(r"^\s*(\d{1,3}\s*[.)\-:]|[-*•·]\s)\s*")
MAX_DISHES = 400

ICONS = [
    (("appetizer", "starter", "mezze", "mazza"), "🥟"),
    (("main",), "🍛"),
    (("fatayer", "pastr", "manakish", "manaeesh", "bakery"), "🫓"),
    (("sandwich",), "🥪"),
    (("wrap", "shawarma"), "🌯"),
    (("soup",), "🍲"),
    (("salad",), "🥗"),
    (("dessert", "sweet", "cake"), "🍰"),
    (("drink", "juice", "beverage", "tea", "coffee"), "🥤"),
    (("breakfast",), "🍳"),
    (("pizza",), "🍕"),
    (("pasta",), "🍝"),
    (("rice",), "🍚"),
    (("fish", "seafood"), "🐟"),
    (("grill", "bbq", "kabab", "kebab"), "🍢"),
    (("kid", "child"), "🧒"),
]


def icon_for(section_name):
    low = section_name.lower()
    for words, icon in ICONS:
        if any(w in low for w in words):
            return icon
    return "🍽️"


def _tidy(text):
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1].upper() + text[1:]


def parse_menu(text):
    """Return [(section_name, [(dish_name, description), ...]), ...] in the order given."""
    lines = [ln.rstrip() for ln in str(text or "").splitlines()]
    lines = [ln for ln in lines if ln.strip()]
    if not lines:
        raise ApiError(400, "Paste your menu first.")
    sections = []
    for i, raw in enumerate(lines):
        numbered = bool(NUMBERED.match(raw))
        line = NUMBERED.sub("", raw).strip()
        if not line:
            continue
        explicit_header = raw.strip().startswith("#") or raw.strip().endswith(":")
        next_numbered = i + 1 < len(lines) and bool(NUMBERED.match(lines[i + 1]))
        is_header = not numbered and (explicit_header or next_numbered or not sections)
        if is_header:
            name = _tidy(line.strip("#: "))
            if len(name) > 40:
                raise ApiError(400, f"Section name is too long (max 40 characters): {name[:40]}…")
            existing = next((s for s in sections if s[0].lower() == name.lower()), None)
            if existing is None:
                sections.append((name, []))
            else:  # same section listed twice: continue adding to it
                sections.remove(existing)
                sections.append(existing)
            continue
        parts = re.split(r"\s+[-–—]\s+", line, maxsplit=1)
        name, desc = _tidy(parts[0]), (parts[1].strip() if len(parts) > 1 else "")
        if len(name) > 80:
            raise ApiError(400, f"Dish name is too long (max 80 characters): {name[:40]}…")
        dishes = sections[-1][1]
        if name.lower() not in {d[0].lower() for d in dishes}:
            dishes.append((name, desc[:300]))
    sections = [s for s in sections if s[1]]
    if not sections:
        raise ApiError(400, "No dishes found. Put a section name on one line and its dishes underneath.")
    if sum(len(d) for _, d in sections) > MAX_DISHES:
        raise ApiError(400, f"At most {MAX_DISHES} dishes at once.")
    return sections


def plan_import(conn, text, replace):
    """Work out what an import would do, without changing anything."""
    sections = parse_menu(text)
    cats = {r["name"].lower(): r for r in conn.execute("SELECT * FROM categories ORDER BY sort_order, id")}
    dishes = list(conn.execute("SELECT id, category_id, name FROM dishes"))
    wanted = {name.lower() for name, _ in sections}
    plan = {"sections": [], "added": 0, "skipped": 0,
            "removeDishes": len(dishes) if replace else 0,
            "removeSections": [r["name"] for k, r in cats.items() if replace and k not in wanted]}
    for name, items in sections:
        cat = cats.get(name.lower())
        have = set() if replace or not cat else {d["name"].lower() for d in dishes if d["category_id"] == cat["id"]}
        new_items = [n for n, _ in items if n.lower() not in have]
        plan["sections"].append({"name": cat["name"] if cat else name, "isNew": cat is None,
                                 "icon": cat["icon"] if cat else icon_for(name),
                                 "dishes": [n for n, _ in items], "new": new_items})
        plan["added"] += len(new_items)
        plan["skipped"] += len(items) - len(new_items)
    return sections, plan


def apply_import(conn, text, replace, delete_image, once_key=None):
    """Import a pasted menu. With `once_key`, it runs only the first time that key is seen."""
    sections, plan = plan_import(conn, text, replace)
    now = clock.iso_now()
    with transaction(conn):
        if once_key and conn.execute(
                "INSERT INTO job_runs (key, ran_at) VALUES (?, ?) ON CONFLICT (key) DO NOTHING RETURNING key",
                (once_key, now)).fetchone() is None:
            return None  # already applied earlier
        if replace:
            for d in conn.execute("SELECT image FROM dishes WHERE image IS NOT NULL").fetchall():
                delete_image(d["image"])
            conn.execute("DELETE FROM dishes")  # past orders keep the dish names they were placed with
        cats = {r["name"].lower(): r["id"] for r in conn.execute("SELECT id, name FROM categories")}
        order = []
        for name, items in sections:
            cat_id = cats.get(name.lower())
            if cat_id is None:
                cat_id = conn.execute("INSERT INTO categories (name, icon, sort_order) VALUES (?, ?, 0) RETURNING id",
                                      (name, icon_for(name))).fetchone()["id"]
            order.append(cat_id)
            have = {r["name"].lower(): r["sort_order"] for r in conn.execute(
                "SELECT name, sort_order FROM dishes WHERE category_id = ?", (cat_id,))}
            next_pos = max(have.values(), default=-1) + 1
            for dish_name, desc in items:
                if dish_name.lower() in have:
                    continue
                conn.execute("INSERT INTO dishes (category_id, name, description, sort_order, created_at, updated_at) "
                             "VALUES (?, ?, ?, ?, ?, ?)", (cat_id, dish_name, desc, next_pos, now, now))
                have[dish_name.lower()] = next_pos
                next_pos += 1
        # imported sections first, in the pasted order; then any others as they were
        rest = [r["id"] for r in conn.execute("SELECT id FROM categories ORDER BY sort_order, id") if r["id"] not in order]
        if replace:
            for cid in rest:
                conn.execute("DELETE FROM categories WHERE id = ?", (cid,))
            rest = []
        for pos, cid in enumerate(order + rest):
            conn.execute("UPDATE categories SET sort_order = ? WHERE id = ?", (pos, cid))
    return plan
