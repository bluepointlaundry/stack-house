"""Order data: loading, saving meal plans and urgent orders, kitchen summaries."""
from datetime import date

from . import clock, rules, settings
from .auth import ApiError
from .db import transaction

URGENT_ACTIVE = ("pending", "accepted", "ready")
URGENT_FLOW = {
    "pending": {"accepted", "ready", "declined", "cancelled"},
    "accepted": {"ready", "delivered", "declined"},
    "ready": {"delivered"},
}
MAX_ITEMS = 40
MAX_SERVINGS = 99


def bump_version(conn):
    current = int(settings.get_value(conn, "orders_version") or 0)
    settings.set_value(conn, "orders_version", str(current + 1))


def get_version(conn):
    return int(settings.get_value(conn, "orders_version") or 0)


# --- loading ------------------------------------------------------------------------

def load_orders(conn, where, params=()):
    rows = conn.execute(
        f"""SELECT o.*, h.name AS house_name, h.color AS house_color,
                   cu.name AS created_by_name, uu.name AS updated_by_name
            FROM orders o
            JOIN houses h ON h.id = o.house_id
            LEFT JOIN users cu ON cu.id = o.created_by
            LEFT JOIN users uu ON uu.id = o.updated_by
            WHERE {where}
            ORDER BY o.service_date, o.created_at""",
        params,
    ).fetchall()
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    items = {}
    for it in conn.execute(
        f"SELECT * FROM order_items WHERE order_id IN ({','.join('?' * len(ids))}) ORDER BY id", ids
    ):
        items.setdefault(it["order_id"], []).append({
            "dishId": it["dish_id"], "name": it["dish_name"], "category": it["category_name"],
            "servings": it["servings"], "note": it["note"],
        })
    out = []
    for r in rows:
        its = items.get(r["id"], [])
        out.append({
            "id": r["id"], "houseId": r["house_id"], "houseName": r["house_name"], "houseColor": r["house_color"],
            "kind": r["kind"], "date": r["service_date"], "meal": r["meal"], "status": r["status"],
            "notes": r["notes"], "neededBy": r["needed_by"], "eta": r["eta"], "chefNote": r["chef_note"],
            "createdBy": r["created_by_name"], "updatedBy": r["updated_by_name"],
            "createdAt": r["created_at"], "updatedAt": r["updated_at"],
            "items": its, "totalServings": sum(i["servings"] for i in its),
        })
    return out


def day_orders(conn, house_id, d: date):
    """Scheduled orders of one house for one day, keyed by meal."""
    found = load_orders(conn, "o.kind = 'scheduled' AND o.house_id = ? AND o.service_date = ?",
                        (house_id, d.isoformat()))
    return {o["meal"]: o for o in found}


def is_set(orders_by_meal, meals):
    return all(m in orders_by_meal and orders_by_meal[m]["status"] in ("ordered", "skipped") for m in meals)


def describe_meal(order):
    if not order:
        return "not set"
    if order["status"] == "skipped":
        return "not needed"
    return ", ".join(f"{i['name']} ×{i['servings']}" for i in order["items"])


# --- validation ---------------------------------------------------------------------

def _clean_text(value, limit, field):
    text = str(value or "").strip()
    if len(text) > limit:
        raise ApiError(400, f"{field} is too long (max {limit} characters).")
    return text


def clean_items(conn, raw_items, allow_inactive=()):
    """Validate [{dishId, servings, note}] against the menu. Returns item dicts sorted by category."""
    if not isinstance(raw_items, list):
        raise ApiError(400, "Items must be a list.")
    if len(raw_items) > MAX_ITEMS:
        raise ApiError(400, f"At most {MAX_ITEMS} dishes per order.")
    wanted = {}
    for raw in raw_items:
        try:
            dish_id = int(raw.get("dishId"))
            servings = int(raw.get("servings"))
        except (TypeError, ValueError, AttributeError):
            raise ApiError(400, "Each dish needs a dish and a number of people.")
        if not 1 <= servings <= MAX_SERVINGS:
            raise ApiError(400, f"Number of people must be between 1 and {MAX_SERVINGS}.")
        wanted[dish_id] = {"servings": servings, "note": _clean_text(raw.get("note"), 200, "Dish note")}
    if not wanted:
        return []
    ids = list(wanted)
    dishes = {r["id"]: r for r in conn.execute(
        f"""SELECT d.id, d.name, d.active, c.name AS category, c.sort_order
            FROM dishes d JOIN categories c ON c.id = d.category_id
            WHERE d.id IN ({','.join('?' * len(ids))})""", ids)}
    out = []
    for dish_id, extra in wanted.items():
        d = dishes.get(dish_id)
        if d is None:
            raise ApiError(400, "One of the dishes no longer exists. Please refresh the menu.")
        if not d["active"] and dish_id not in allow_inactive:
            raise ApiError(400, f"{d['name']} is not available right now.")
        out.append({"dish_id": dish_id, "name": d["name"], "category": d["category"],
                    "sort": (d["sort_order"], d["name"].lower()), **extra})
    out.sort(key=lambda i: i["sort"])
    return out


def _signature(order):
    if not order:
        return None
    return (order["status"], order["notes"],
            tuple((i["dishId"], i["servings"], i["note"]) for i in order["items"]))


def _write_items(conn, order_id, items):
    conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
    for it in items:
        conn.execute(
            "INSERT INTO order_items (order_id, dish_id, dish_name, category_name, servings, note) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, it["dish_id"], it["name"], it["category"], it["servings"], it["note"]),
        )


# --- meal plans (scheduled orders) ----------------------------------------------------

def check_plannable(cfg, d: date, user):
    """Raise unless `user` may change the plan for date `d`. Returns True when it's an admin late edit."""
    if d < rules.today(cfg) or d > rules.last_plannable(cfg):
        raise ApiError(400, f"You can plan from today up to {cfg['daysAhead']} days ahead.")
    if not rules.is_service_day(cfg, d):
        raise ApiError(400, "The kitchen is closed on this day.")
    if rules.is_locked(cfg, d):
        if not user["is_admin"]:
            raise ApiError(409, "Orders for this day are locked. Use “Order now” for anything urgent.")
        return True
    return False


def save_plan(conn, cfg, user, house_id, d: date, meals_payload):
    """Save a house's plan for one day. Returns (before, after, late) maps of meal -> order."""
    late = check_plannable(cfg, d, user)
    if not isinstance(meals_payload, dict):
        raise ApiError(400, "Missing meals.")
    enabled = rules.enabled_meals(cfg)
    before = day_orders(conn, house_id, d)
    now = clock.iso_now()

    cleaned = {}
    for meal, data in meals_payload.items():
        if meal not in enabled:
            raise ApiError(400, f"{meal.title()} is not served.")
        if data is None:
            cleaned[meal] = None  # clear the choice entirely
            continue
        if not isinstance(data, dict) or not isinstance(data.get("need"), bool):
            raise ApiError(400, f"Choose whether you need {meal}.")
        notes = _clean_text(data.get("notes"), 500, "Notes")
        if data["need"]:
            existing = {i["dishId"] for i in (before.get(meal) or {}).get("items", [])}
            items = clean_items(conn, data.get("items", []), allow_inactive=existing)
            if not items:
                raise ApiError(400, f"Pick at least one dish for {meal}, or choose “No {meal}”.")
            cleaned[meal] = ("ordered", items, notes)
        else:
            cleaned[meal] = ("skipped", [], notes)

    with transaction(conn):
        for meal, value in cleaned.items():
            old = before.get(meal)
            if value is None:
                if old:
                    conn.execute("DELETE FROM orders WHERE id = ?", (old["id"],))
                continue
            status, items, notes = value
            if old:
                conn.execute(
                    "UPDATE orders SET status = ?, notes = ?, updated_by = ?, updated_at = ? WHERE id = ?",
                    (status, notes, user["id"], now, old["id"]),
                )
                order_id = old["id"]
            else:
                order_id = conn.execute(
                    "INSERT INTO orders (house_id, kind, service_date, meal, status, notes, created_by, updated_by, "
                    "created_at, updated_at) VALUES (?, 'scheduled', ?, ?, ?, ?, ?, ?, ?, ?)",
                    (house_id, d.isoformat(), meal, status, notes, user["id"], user["id"], now, now),
                ).lastrowid
            _write_items(conn, order_id, items)
        bump_version(conn)

    after = day_orders(conn, house_id, d)
    return before, after, late


def plan_changed(before, after):
    keys = set(before) | set(after)
    return any(_signature(before.get(k)) != _signature(after.get(k)) for k in keys)


# --- urgent orders --------------------------------------------------------------------

def create_urgent(conn, cfg, user, house_id, raw_items, notes, needed_by):
    status = rules.kitchen_status(cfg)
    if cfg["urgentOnlyWhenOpen"] and not status["open"]:
        raise ApiError(409, "The kitchen is closed right now.")
    items = clean_items(conn, raw_items or [])
    notes = _clean_text(notes, 500, "Notes")
    if not items and not notes:
        raise ApiError(400, "Pick at least one dish or write what you need.")
    needed_by = _clean_text(needed_by, 20, "Needed by") or "ASAP"
    now = clock.iso_now()
    with transaction(conn):
        order_id = conn.execute(
            "INSERT INTO orders (house_id, kind, service_date, meal, status, notes, needed_by, created_by, "
            "updated_by, created_at, updated_at) VALUES (?, 'urgent', ?, NULL, 'pending', ?, ?, ?, ?, ?, ?)",
            (house_id, rules.today(cfg).isoformat(), notes, needed_by, user["id"], user["id"], now, now),
        ).lastrowid
        _write_items(conn, order_id, items)
        bump_version(conn)
    return load_orders(conn, "o.id = ?", (order_id,))[0]


def set_urgent_status(conn, user, order_id, new_status, eta=None, chef_note=None):
    rows = load_orders(conn, "o.id = ? AND o.kind = 'urgent'", (order_id,))
    if not rows:
        raise ApiError(404, "Order not found.")
    order = rows[0]
    allowed = URGENT_FLOW.get(order["status"], set())
    if new_status not in allowed:
        raise ApiError(409, f"This order is already {order['status']}.")
    eta = _clean_text(eta, 20, "ETA") if eta is not None else order["eta"]
    chef_note = _clean_text(chef_note, 300, "Note") if chef_note is not None else order["chefNote"]
    with transaction(conn):
        conn.execute(
            "UPDATE orders SET status = ?, eta = ?, chef_note = ?, updated_by = ?, updated_at = ? WHERE id = ?",
            (new_status, eta, chef_note, user["id"], clock.iso_now(), order_id),
        )
        bump_version(conn)
    return load_orders(conn, "o.id = ?", (order_id,))[0]


# --- kitchen overview -------------------------------------------------------------------

def houses(conn):
    return [dict(id=r["id"], name=r["name"], color=r["color"], people=r["people"])
            for r in conn.execute("SELECT * FROM houses ORDER BY sort_order, id")]


def prep_summary(orders):
    """Aggregate ordered dishes: [{category, dishes: [{name, total, byHouse}]}] in menu order."""
    cats = {}
    for o in orders:
        if o["status"] != "ordered":
            continue
        for it in o["items"]:
            cat = cats.setdefault(it["category"], {})
            key = it["dishId"] or it["name"]
            dish = cat.setdefault(key, {"name": it["name"], "total": 0, "byHouse": [], "notes": []})
            dish["total"] += it["servings"]
            dish["byHouse"].append({"house": o["houseName"], "color": o["houseColor"], "servings": it["servings"]})
            if it["note"]:
                dish["notes"].append(f"{o['houseName']}: {it['note']}")
    return [{"category": c, "dishes": list(d.values())} for c, d in cats.items()]


def kitchen_day(conn, cfg, d: date):
    hs = houses(conn)
    orders = load_orders(conn, "o.kind = 'scheduled' AND o.service_date = ?", (d.isoformat(),))
    by_meal = {}
    for o in orders:
        by_meal.setdefault(o["meal"], {})[o["houseId"]] = o
    meals = []
    for meal in rules.enabled_meals(cfg):
        got = by_meal.get(meal, {})
        meal_orders = [got[h["id"]] for h in hs if h["id"] in got]
        meals.append({
            "meal": meal,
            "time": cfg["meals"][meal]["time"],
            "houses": [{**h, "status": got[h["id"]]["status"] if h["id"] in got else None,
                        "order": got.get(h["id"])} for h in hs],
            "summary": prep_summary(meal_orders),
            "servings": sum(o["totalServings"] for o in meal_orders if o["status"] == "ordered"),
            "ordered": sum(1 for o in meal_orders if o["status"] == "ordered"),
        })
    hours = rules.day_hours(cfg, d)
    return {
        "date": d.isoformat(),
        "open": hours is not None,
        "hours": hours,
        "locked": rules.is_locked(cfg, d),
        "lockAt": rules.fmt_lock(cfg, d),
        "meals": meals,
    }


def meal_line(day, meal):
    m = next((x for x in day["meals"] if x["meal"] == meal), None)
    if not m:
        return ""
    if not m["ordered"]:
        return f"{meal.title()}: nothing ordered"
    return f"{meal.title()}: {m['ordered']} {'house' if m['ordered'] == 1 else 'houses'} · {m['servings']} servings"
