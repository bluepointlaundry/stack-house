"""JSON API used by the web app."""
import base64
import binascii
import json
import uuid
from datetime import date, timedelta

from flask import Blueprint, current_app, jsonify, request

from . import clock, notify, orders, rules, settings
from .auth import (ApiError, check_new_password, check_throttle, clean_username, clear_failures, current_user,
                   hash_password, login_user, logout_user, record_failure, require_login,
                   verify_password)
from .db import add_sample_dishes, get_db, transaction

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.errorhandler(ApiError)
def _api_error(e):
    return jsonify(error=e.message), e.status


@bp.before_request
def _json_only_for_writes():
    # Browsers cannot send a cross-site JSON request without CORS approval, so this
    # (together with SameSite cookies) protects every state-changing call from CSRF.
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not request.is_json:
        raise ApiError(415, "Expected a JSON request.")


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def parse_day(value):
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ApiError(400, "Invalid date.")


def text(value, limit, field, required=False):
    t = str(value or "").strip()
    if required and not t:
        raise ApiError(400, f"{field} is required.")
    if len(t) > limit:
        raise ApiError(400, f"{field} is too long (max {limit} characters).")
    return t


def user_json(u):
    if not u:
        return None
    return {
        "id": u["id"], "username": u["username"], "name": u["name"], "role": u["role"],
        "isAdmin": bool(u["is_admin"]), "houseId": u["house_id"], "kitchenAlerts": bool(u["kitchen_alerts"]),
        "active": bool(u["active"]), "createdAt": u["created_at"], "lastLoginAt": u["last_login_at"],
    }


def categories(conn):
    return [{"id": r["id"], "name": r["name"], "icon": r["icon"], "sortOrder": r["sort_order"]}
            for r in conn.execute("SELECT * FROM categories ORDER BY sort_order, id")]


def dish_json(r):
    return {"id": r["id"], "categoryId": r["category_id"], "name": r["name"], "description": r["description"],
            "image": r["image"], "active": bool(r["active"])}


def target_house(user, requested=None):
    """The house an order is for: your own, or (admins only) any house."""
    if requested not in (None, "", user["house_id"]):
        if not user["is_admin"]:
            raise ApiError(403, "You can only order for your own family.")
        row = get_db().execute("SELECT id FROM houses WHERE id = ?", (requested,)).fetchone()
        if not row:
            raise ApiError(404, "Family not found.")
        return row["id"]
    if not user["house_id"]:
        raise ApiError(400, "Your account is not linked to a family yet. Ask an admin.")
    return user["house_id"]


def admin_count(conn, exclude=None):
    return conn.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1 AND active = 1 AND id != ?",
                        (exclude or 0,)).fetchone()[0]


# --- session & bootstrap -------------------------------------------------------------

@bp.get("/bootstrap")
def bootstrap():
    conn = get_db()
    cfg = settings.load(conn)
    user = current_user()
    setup_needed = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    data = {"setupNeeded": setup_needed, "user": user_json(user)}
    if setup_needed:
        data["houses"] = orders.houses(conn)
    if user:
        data.update({
            "settings": cfg,
            "houses": orders.houses(conn),
            "categories": categories(conn),
            "kitchen": rules.kitchen_status(cfg),
            "today": rules.today(cfg).isoformat(),
            "lockTomorrow": rules.fmt_lock(cfg, rules.today(cfg) + timedelta(days=1)),
            "vapidPublicKey": notify.vapid_public_key(conn),
            "version": orders.get_version(conn),
        })
        if user["is_admin"]:
            data["lastTick"] = settings.get_value(conn, "last_tick")
            data["timerSetup"] = settings.get_value(conn, "timer_setup")
    return jsonify(data)


@bp.post("/setup")
def setup():
    conn = get_db()
    data = body()
    name = text(data.get("name"), 60, "Name", required=True)
    username = clean_username(data.get("username"))
    check_new_password(data.get("password"))
    role = data.get("role") if data.get("role") in ("member", "chef") else "member"
    house_id = data.get("houseId") if role == "member" else None
    if role == "member" and not conn.execute("SELECT 1 FROM houses WHERE id = ?", (house_id,)).fetchone():
        raise ApiError(400, "Choose your family.")
    tz = data.get("timezone")
    with transaction(conn):
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            raise ApiError(409, "Setup has already been completed.")
        uid = conn.execute(
            "INSERT INTO users (username, name, password_hash, role, is_admin, house_id, kitchen_alerts, created_at, "
            "last_login_at) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?) RETURNING id",
            (username, name, hash_password(data["password"]), role, house_id, 1 if role == "chef" else 0,
             clock.iso_now(), clock.iso_now()),
        ).fetchone()["id"]
        if tz and settings.valid_timezone(tz):
            cfg = settings.load(conn)
            cfg["timezone"] = tz
            settings.save(conn, cfg)
        if data.get("sampleMenu") and conn.execute("SELECT COUNT(*) FROM dishes").fetchone()[0] == 0:
            add_sample_dishes(conn)
    login_user(conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone())
    return jsonify(ok=True)


@bp.post("/login")
def login():
    check_throttle()
    data = body()
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE username = ? AND active = 1",
                       (str(data.get("username") or "").strip().lower(),)).fetchone()
    if not row or not verify_password(row["password_hash"], str(data.get("password") or "")):
        record_failure()
        raise ApiError(401, "Wrong username or password.")
    clear_failures()
    conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (clock.iso_now(), row["id"]))
    login_user(row)
    return jsonify(ok=True)


@bp.post("/logout")
def logout():
    logout_user()
    return jsonify(ok=True)


@bp.post("/me/password")
@require_login()
def change_password():
    user = current_user()
    data = body()
    if not verify_password(user["password_hash"], str(data.get("current") or "")):
        raise ApiError(400, "Your current password is not correct.")
    check_new_password(data.get("new"))
    conn = get_db()
    conn.execute("UPDATE users SET password_hash = ?, session_version = session_version + 1 WHERE id = ?",
                 (hash_password(data["new"]), user["id"]))
    login_user(conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone())
    return jsonify(ok=True)


@bp.get("/poll")
@require_login()
def poll():
    conn = get_db()
    cfg = settings.load(conn)
    unread = conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL",
                          (current_user()["id"],)).fetchone()[0]
    latest = conn.execute("SELECT id, title, body, url, kind FROM notifications WHERE user_id = ? "
                          "ORDER BY id DESC LIMIT 1", (current_user()["id"],)).fetchone()
    return jsonify(unread=unread, version=orders.get_version(conn), kitchen=rules.kitchen_status(cfg),
                   today=rules.today(cfg).isoformat(), latest=dict(latest) if latest else None)


# --- menu ---------------------------------------------------------------------------------

@bp.get("/menu")
@require_login()
def menu():
    conn = get_db()
    show_all = request.args.get("all") == "1" and current_user()["is_admin"]
    where = "" if show_all else "WHERE active = 1"
    dishes = [dish_json(r) for r in conn.execute(f"SELECT * FROM dishes {where} ORDER BY lower(name)")]
    return jsonify(categories=categories(conn), dishes=dishes)


def _save_image(data_url):
    try:
        header, b64 = data_url.split(",", 1)
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, binascii.Error):
        raise ApiError(400, "Could not read the photo.")
    if len(raw) > 3 * 1024 * 1024:
        raise ApiError(400, "Photo is too large (max 3 MB).")
    if raw[:3] == b"\xff\xd8\xff":
        ext, mime = "jpg", "image/jpeg"
    elif raw[:8] == b"\x89PNG\r\n\x1a\n":
        ext, mime = "png", "image/png"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        ext, mime = "webp", "image/webp"
    else:
        raise ApiError(400, "Photo must be a JPEG, PNG or WebP image.")
    name = f"{uuid.uuid4().hex}.{ext}"
    # Photos live in the database: serverless hosts have no lasting disk.
    get_db().execute("INSERT INTO images (name, mime, data, created_at) VALUES (?, ?, ?, ?)",
                     (name, mime, raw, clock.iso_now()))
    return f"/uploads/{name}"


def _delete_image(path):
    if path and path.startswith("/uploads/"):
        get_db().execute("DELETE FROM images WHERE name = ?", (path.rsplit("/", 1)[-1],))


def _dish_fields(conn, data, existing=None):
    name = text(data.get("name", existing["name"] if existing else ""), 80, "Dish name", required=True)
    desc = text(data.get("description", existing["description"] if existing else ""), 300, "Description")
    cat_id = data.get("categoryId", existing["category_id"] if existing else None)
    if not conn.execute("SELECT 1 FROM categories WHERE id = ?", (cat_id,)).fetchone():
        raise ApiError(400, "Choose a category.")
    active = bool(data.get("active", existing["active"] if existing else True))
    return name, desc, cat_id, active


@bp.post("/dishes")
@require_login(admin=True)
def create_dish():
    conn = get_db()
    data = body()
    name, desc, cat_id, active = _dish_fields(conn, data)
    image = _save_image(data["image"]) if data.get("image") else None
    now = clock.iso_now()
    did = conn.execute(
        "INSERT INTO dishes (category_id, name, description, image, active, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id", (cat_id, name, desc, image, int(active), now, now)).fetchone()["id"]
    return jsonify(dish_json(conn.execute("SELECT * FROM dishes WHERE id = ?", (did,)).fetchone()))


@bp.put("/dishes/<int:dish_id>")
@require_login(admin=True)
def update_dish(dish_id):
    conn = get_db()
    existing = conn.execute("SELECT * FROM dishes WHERE id = ?", (dish_id,)).fetchone()
    if not existing:
        raise ApiError(404, "Dish not found.")
    data = body()
    name, desc, cat_id, active = _dish_fields(conn, data, existing)
    image = existing["image"]
    if "image" in data:
        if data["image"] and data["image"].startswith("data:"):
            image = _save_image(data["image"])
            _delete_image(existing["image"])
        elif not data["image"]:
            _delete_image(existing["image"])
            image = None
    conn.execute(
        "UPDATE dishes SET category_id = ?, name = ?, description = ?, image = ?, active = ?, updated_at = ? "
        "WHERE id = ?", (cat_id, name, desc, image, int(active), clock.iso_now(), dish_id))
    return jsonify(dish_json(conn.execute("SELECT * FROM dishes WHERE id = ?", (dish_id,)).fetchone()))


@bp.delete("/dishes/<int:dish_id>")
@require_login(admin=True)
def delete_dish(dish_id):
    conn = get_db()
    existing = conn.execute("SELECT * FROM dishes WHERE id = ?", (dish_id,)).fetchone()
    if not existing:
        raise ApiError(404, "Dish not found.")
    conn.execute("DELETE FROM dishes WHERE id = ?", (dish_id,))  # past orders keep the dish name
    _delete_image(existing["image"])
    return jsonify(ok=True)


@bp.post("/categories")
@require_login(admin=True)
def create_category():
    conn = get_db()
    data = body()
    name = text(data.get("name"), 40, "Category name", required=True)
    icon = text(data.get("icon"), 8, "Icon") or "🍽️"
    if conn.execute("SELECT 1 FROM categories WHERE lower(name) = lower(?)", (name,)).fetchone():
        raise ApiError(409, "That category already exists.")
    order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM categories").fetchone()[0]
    conn.execute("INSERT INTO categories (name, icon, sort_order) VALUES (?, ?, ?)", (name, icon, order))
    return jsonify(categories=categories(conn))


@bp.put("/categories/<int:cat_id>")
@require_login(admin=True)
def update_category(cat_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if not row:
        raise ApiError(404, "Category not found.")
    data = body()
    name = text(data.get("name", row["name"]), 40, "Category name", required=True)
    icon = text(data.get("icon", row["icon"]), 8, "Icon") or "🍽️"
    clash = conn.execute("SELECT 1 FROM categories WHERE lower(name) = lower(?) AND id != ?", (name, cat_id)).fetchone()
    if clash:
        raise ApiError(409, "That category already exists.")
    with transaction(conn):
        conn.execute("UPDATE categories SET name = ?, icon = ? WHERE id = ?", (name, icon, cat_id))
        move = data.get("move")
        if move in ("up", "down"):
            ids = [r["id"] for r in conn.execute("SELECT id FROM categories ORDER BY sort_order, id")]
            i = ids.index(cat_id)
            j = i - 1 if move == "up" else i + 1
            if 0 <= j < len(ids):
                ids[i], ids[j] = ids[j], ids[i]
            for pos, cid in enumerate(ids):
                conn.execute("UPDATE categories SET sort_order = ? WHERE id = ?", (pos, cid))
    return jsonify(categories=categories(conn))


@bp.delete("/categories/<int:cat_id>")
@require_login(admin=True)
def delete_category(cat_id):
    conn = get_db()
    if conn.execute("SELECT 1 FROM dishes WHERE category_id = ?", (cat_id,)).fetchone():
        raise ApiError(409, "Move or delete the dishes in this category first.")
    conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    return jsonify(categories=categories(conn))


# --- meal plans -------------------------------------------------------------------------------

def plan_json(conn, cfg, house_id, d):
    got = orders.day_orders(conn, house_id, d)
    meals = rules.enabled_meals(cfg)
    return {
        "date": d.isoformat(),
        "houseId": house_id,
        "open": rules.is_service_day(cfg, d),
        "locked": rules.is_locked(cfg, d),
        "lockAt": rules.fmt_lock(cfg, d),
        "isSet": orders.is_set(got, meals),
        "meals": {m: got.get(m) for m in meals},
    }


@bp.get("/days")
@require_login()
def days():
    user = current_user()
    conn = get_db()
    cfg = settings.load(conn)
    house_id = target_house(user, request.args.get("houseId", type=int))
    return jsonify(days=[plan_json(conn, cfg, house_id, d) for d in rules.plannable_dates(cfg)])


@bp.get("/plan/<day>")
@require_login()
def get_plan(day):
    user = current_user()
    conn = get_db()
    cfg = settings.load(conn)
    house_id = target_house(user, request.args.get("houseId", type=int))
    return jsonify(plan_json(conn, cfg, house_id, parse_day(day)))


@bp.put("/plan/<day>")
@require_login()
def put_plan(day):
    user = current_user()
    conn = get_db()
    cfg = settings.load(conn)
    data = body()
    d = parse_day(day)
    house_id = target_house(user, data.get("houseId"))
    before, after, late = orders.save_plan(conn, cfg, user, house_id, d, data.get("meals"))

    if orders.plan_changed(before, after):
        meals = rules.enabled_meals(cfg)
        house = conn.execute("SELECT name FROM houses WHERE id = ?", (house_id,)).fetchone()["name"]
        was_set, now_set = orders.is_set(before, meals), orders.is_set(after, meals)
        when = rules.fmt_day(d)
        if late:
            title = f"⚠️ Late change: {house} family, {when}"
        elif now_set and not was_set:
            title = f"🏠 {house} family is set for {when}"
        elif not after:
            title = f"↩️ {house} family cleared their plan for {when}"
        else:
            title = f"✏️ {house} family updated {when}"
        body_text = " · ".join(f"{m.title()}: {orders.describe_meal(after.get(m))}" for m in meals)
        notify.notify(conn, notify.kitchen_user_ids(conn), title, body_text,
                      url=f"/#/kitchen/{d.isoformat()}", kind="plan")
    return jsonify(plan_json(conn, cfg, house_id, d))


# --- urgent orders ----------------------------------------------------------------------------

@bp.post("/urgent")
@require_login()
def create_urgent():
    user = current_user()
    conn = get_db()
    cfg = settings.load(conn)
    data = body()
    house_id = target_house(user, data.get("houseId"))
    order = orders.create_urgent(conn, cfg, user, house_id, data.get("items"), data.get("notes"),
                                 data.get("neededBy"))
    what = orders.describe_meal(order) if order["items"] else order["notes"]
    extra = f" · Note: {order['notes']}" if order["items"] and order["notes"] else ""
    notify.notify(conn, notify.kitchen_user_ids(conn),
                  title=f"🚨 Order now: {order['houseName']} family",
                  body=f"{what}{extra} · Needed: {order['neededBy']} · by {user['name']}",
                  url="/#/kitchen", kind="urgent", urgent=True)
    return jsonify(order)


@bp.post("/urgent/<int:order_id>/cancel")
@require_login()
def cancel_urgent(order_id):
    user = current_user()
    conn = get_db()
    row = conn.execute("SELECT house_id FROM orders WHERE id = ? AND kind = 'urgent'", (order_id,)).fetchone()
    if not row:
        raise ApiError(404, "Order not found.")
    if row["house_id"] != user["house_id"] and not user["is_admin"]:
        raise ApiError(403, "This is not your family's order.")
    order = orders.set_urgent_status(conn, user, order_id, "cancelled")
    notify.notify(conn, notify.kitchen_user_ids(conn),
                  title=f"❌ {order['houseName']} family cancelled their order",
                  body=orders.describe_meal(order) if order["items"] else order["notes"],
                  url="/#/kitchen", kind="urgent")
    return jsonify(order)


STATUS_MESSAGES = {
    "accepted": ("👨‍🍳 The kitchen is on it", "Your order was accepted"),
    "ready": ("✅ Your order is ready", "Your order is ready to collect"),
    "delivered": ("🍽️ Order delivered", "Enjoy your meal"),
    "declined": ("🙁 The kitchen can't make this order", "Your order was declined"),
}


@bp.post("/urgent/<int:order_id>/status")
@require_login(kitchen=True)
def urgent_status(order_id):
    user = current_user()
    conn = get_db()
    data = body()
    status = data.get("status")
    if status not in STATUS_MESSAGES:
        raise ApiError(400, "Unknown status.")
    order = orders.set_urgent_status(conn, user, order_id, status, data.get("eta"), data.get("note"))
    title, fallback = STATUS_MESSAGES[status]
    parts = []
    if status == "accepted" and order["eta"]:
        parts.append(f"Ready in about {order['eta']}")
    if order["chefNote"]:
        parts.append(order["chefNote"])
    notify.notify(conn, notify.house_user_ids(conn, order["houseId"]), title,
                  " · ".join(parts) or fallback, url="/#/orders", kind="status")
    return jsonify(order)


# --- order lists --------------------------------------------------------------------------------

@bp.get("/orders")
@require_login()
def list_orders():
    user = current_user()
    conn = get_db()
    cfg = settings.load(conn)
    house_id = target_house(user, request.args.get("houseId", type=int))
    today = rules.today(cfg)
    since = (today - timedelta(days=30)).isoformat()
    all_orders = orders.load_orders(conn, "o.house_id = ? AND o.service_date >= ?", (house_id, since))
    upcoming = [o for o in all_orders if o["kind"] == "scheduled" and o["date"] >= today.isoformat()]
    urgent = [o for o in all_orders if o["kind"] == "urgent"]
    urgent.sort(key=lambda o: o["createdAt"], reverse=True)
    past = [o for o in all_orders if o["kind"] == "scheduled" and o["date"] < today.isoformat()]
    past.sort(key=lambda o: (o["date"], o["meal"] or ""), reverse=True)
    return jsonify(upcoming=upcoming, urgent=urgent, past=past)


@bp.get("/kitchen")
@require_login(kitchen=True)
def kitchen():
    conn = get_db()
    cfg = settings.load(conn)
    today = rules.today(cfg)
    d = parse_day(request.args["date"]) if request.args.get("date") else today
    active = orders.load_orders(
        conn, f"o.kind = 'urgent' AND o.status IN ({','.join('?' * len(orders.URGENT_ACTIVE))})",
        orders.URGENT_ACTIVE)
    active.sort(key=lambda o: o["createdAt"])
    done_today = orders.load_orders(
        conn, "o.kind = 'urgent' AND o.service_date = ? AND o.status NOT IN ('pending','accepted','ready')",
        (today.isoformat(),))
    done_today.sort(key=lambda o: o["updatedAt"], reverse=True)
    days_list = []
    for i in range(-1, cfg["daysAhead"] + 1):
        dd = today + timedelta(days=i)
        days_list.append({"date": dd.isoformat(), "open": rules.is_service_day(cfg, dd)})
    return jsonify(day=orders.kitchen_day(conn, cfg, d), urgent=active, urgentDone=done_today,
                   days=days_list, today=today.isoformat())


# --- notifications & push ---------------------------------------------------------------------

@bp.get("/notifications")
@require_login()
def list_notifications():
    rows = get_db().execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 60", (current_user()["id"],))
    return jsonify(notifications=[{
        "id": r["id"], "title": r["title"], "body": r["body"], "url": r["url"], "kind": r["kind"],
        "read": r["read_at"] is not None, "createdAt": r["created_at"]} for r in rows])


@bp.post("/notifications/read")
@require_login()
def read_notifications():
    data = body()
    conn = get_db()
    uid = current_user()["id"]
    if data.get("all"):
        conn.execute("UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL",
                     (clock.iso_now(), uid))
    else:
        ids = data.get("ids") if isinstance(data.get("ids"), list) else []
        for nid in ids[:200]:
            if not isinstance(nid, int):
                continue
            conn.execute("UPDATE notifications SET read_at = ? WHERE id = ? AND user_id = ? AND read_at IS NULL",
                         (clock.iso_now(), nid, uid))
    return jsonify(ok=True)


@bp.post("/push/subscribe")
@require_login()
def push_subscribe():
    sub = body().get("subscription") or {}
    endpoint = str(sub.get("endpoint") or "")
    keys = sub.get("keys") or {}
    if not endpoint.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
        raise ApiError(400, "Invalid push subscription.")
    conn = get_db()
    conn.execute(
        "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, user_agent, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(endpoint) DO UPDATE SET user_id = excluded.user_id, "
        "p256dh = excluded.p256dh, auth = excluded.auth",
        (current_user()["id"], endpoint[:1000], str(keys["p256dh"])[:200], str(keys["auth"])[:100],
         request.headers.get("User-Agent", "")[:300], clock.iso_now()))
    return jsonify(ok=True)


@bp.post("/push/unsubscribe")
@require_login()
def push_unsubscribe():
    endpoint = str(body().get("endpoint") or "")
    get_db().execute("DELETE FROM push_subscriptions WHERE endpoint = ? AND user_id = ?",
                     (endpoint, current_user()["id"]))
    return jsonify(ok=True)


@bp.post("/push/test")
@require_login()
def push_test():
    notify.notify(get_db(), [current_user()["id"]], "🔔 Test notification",
                  "Notifications are working on this device.", url="/#/me", kind="test")
    return jsonify(ok=True)


# --- admin: users ---------------------------------------------------------------------------------

@bp.get("/admin/users")
@require_login(admin=True)
def admin_users():
    rows = get_db().execute("SELECT * FROM users ORDER BY active DESC, lower(name)")
    return jsonify(users=[user_json(r) for r in rows])


def _user_fields(conn, data, existing=None):
    def pick(key, col, default=None):
        if key in data:
            return data[key]
        return existing[col] if existing else default

    name = text(pick("name", "name", ""), 60, "Name", required=True)
    role = pick("role", "role", "member")
    if role not in ("member", "chef"):
        raise ApiError(400, "Role must be family member or chef.")
    house_id = pick("houseId", "house_id")
    if role == "member":
        if not conn.execute("SELECT 1 FROM houses WHERE id = ?", (house_id,)).fetchone():
            raise ApiError(400, "Choose a family for this person.")
    else:
        house_id = None
    is_admin = bool(pick("isAdmin", "is_admin", False))
    alerts = bool(pick("kitchenAlerts", "kitchen_alerts", role == "chef"))
    active = bool(pick("active", "active", True))
    return name, role, house_id, is_admin, alerts, active


@bp.post("/admin/users")
@require_login(admin=True)
def admin_create_user():
    conn = get_db()
    data = body()
    username = clean_username(data.get("username"))
    check_new_password(data.get("password"))
    name, role, house_id, is_admin, alerts, active = _user_fields(conn, data)
    if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        raise ApiError(409, "That username is taken.")
    uid = conn.execute(
        "INSERT INTO users (username, name, password_hash, role, is_admin, house_id, kitchen_alerts, active, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
        (username, name, hash_password(data["password"]), role, int(is_admin), house_id, int(alerts),
         int(active), clock.iso_now())).fetchone()["id"]
    return jsonify(user_json(conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()))


@bp.put("/admin/users/<int:user_id>")
@require_login(admin=True)
def admin_update_user(user_id):
    conn = get_db()
    me = current_user()
    existing = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not existing:
        raise ApiError(404, "User not found.")
    data = body()
    name, role, house_id, is_admin, alerts, active = _user_fields(conn, data, existing)
    username = clean_username(data["username"]) if "username" in data else existing["username"]
    if conn.execute("SELECT 1 FROM users WHERE username = ? AND id != ?", (username, user_id)).fetchone():
        raise ApiError(409, "That username is taken.")
    if user_id == me["id"] and (not is_admin or not active):
        raise ApiError(400, "You can't remove your own admin access or deactivate yourself.")
    if existing["is_admin"] and (not is_admin or not active) and admin_count(conn, exclude=user_id) == 0:
        raise ApiError(400, "There must be at least one active admin.")
    bump_session = not active
    if data.get("password"):
        check_new_password(data["password"])
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(data["password"]), user_id))
        bump_session = True
    conn.execute(
        "UPDATE users SET username = ?, name = ?, role = ?, house_id = ?, is_admin = ?, kitchen_alerts = ?, "
        "active = ?, session_version = session_version + ? WHERE id = ?",
        (username, name, role, house_id, int(is_admin), int(alerts), int(active), 1 if bump_session else 0,
         user_id))
    if user_id == me["id"]:
        login_user(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
    return jsonify(user_json(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()))


@bp.delete("/admin/users/<int:user_id>")
@require_login(admin=True)
def admin_delete_user(user_id):
    conn = get_db()
    if user_id == current_user()["id"]:
        raise ApiError(400, "You can't delete your own account.")
    existing = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not existing:
        raise ApiError(404, "User not found.")
    if existing["is_admin"] and admin_count(conn, exclude=user_id) == 0:
        raise ApiError(400, "There must be at least one active admin.")
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return jsonify(ok=True)


# --- admin: houses ----------------------------------------------------------------------------------

def _house_fields(data, existing=None):
    name = text(data.get("name", existing["name"] if existing else ""), 40, "Family name", required=True)
    color = str(data.get("color", existing["color"] if existing else "#b4532a"))
    if not (len(color) == 7 and color.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in color[1:])):
        raise ApiError(400, "Color must look like #b4532a.")
    try:
        people = int(data.get("people", existing["people"] if existing else 4))
    except (TypeError, ValueError):
        raise ApiError(400, "People must be a number.")
    if not 1 <= people <= orders.MAX_SERVINGS:
        raise ApiError(400, "People must be between 1 and 99.")
    return name, color, people


@bp.get("/admin/houses")
@require_login(admin=True)
def admin_houses():
    conn = get_db()
    counts = {r["house_id"]: r["n"] for r in conn.execute(
        "SELECT house_id, COUNT(*) AS n FROM users WHERE active = 1 GROUP BY house_id")}
    return jsonify(houses=[{**h, "members": counts.get(h["id"], 0)} for h in orders.houses(conn)])


@bp.post("/admin/houses")
@require_login(admin=True)
def admin_create_house():
    conn = get_db()
    name, color, people = _house_fields(body())
    if conn.execute("SELECT 1 FROM houses WHERE lower(name) = lower(?)", (name,)).fetchone():
        raise ApiError(409, "A family with that name already exists.")
    order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM houses").fetchone()[0]
    conn.execute("INSERT INTO houses (name, color, people, sort_order, created_at) VALUES (?, ?, ?, ?, ?)",
                 (name, color, people, order, clock.iso_now()))
    return admin_houses()


@bp.put("/admin/houses/<int:house_id>")
@require_login(admin=True)
def admin_update_house(house_id):
    conn = get_db()
    existing = conn.execute("SELECT * FROM houses WHERE id = ?", (house_id,)).fetchone()
    if not existing:
        raise ApiError(404, "Family not found.")
    name, color, people = _house_fields(body(), existing)
    if conn.execute("SELECT 1 FROM houses WHERE lower(name) = lower(?) AND id != ?", (name, house_id)).fetchone():
        raise ApiError(409, "A family with that name already exists.")
    conn.execute("UPDATE houses SET name = ?, color = ?, people = ? WHERE id = ?", (name, color, people, house_id))
    return admin_houses()


@bp.delete("/admin/houses/<int:house_id>")
@require_login(admin=True)
def admin_delete_house(house_id):
    conn = get_db()
    if conn.execute("SELECT 1 FROM users WHERE house_id = ?", (house_id,)).fetchone():
        raise ApiError(409, "Move or remove this family's members first.")
    if conn.execute("SELECT 1 FROM orders WHERE house_id = ?", (house_id,)).fetchone():
        raise ApiError(409, "This family has order history and can't be deleted.")
    conn.execute("DELETE FROM houses WHERE id = ?", (house_id,))
    return admin_houses()


# --- admin: settings ----------------------------------------------------------------------------------

@bp.put("/admin/settings")
@require_login(admin=True)
def admin_settings():
    conn = get_db()
    try:
        cfg = settings.validate(body())
    except ValueError as e:
        raise ApiError(400, str(e))
    settings.save(conn, cfg)
    return jsonify(settings=cfg, kitchen=rules.kitchen_status(cfg))


@bp.get("/admin/backup")
@require_login(admin=True)
def admin_backup():
    """A zip with every table as JSON (stackhouse-data.json) plus all dish photos (uploads/)."""
    import io
    import zipfile

    conn = get_db()
    tables = ["houses", "users", "categories", "dishes", "orders", "order_items", "settings",
              "push_subscriptions", "notifications"]
    buf = io.BytesIO()
    with transaction(conn), zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if conn.postgres:  # one consistent snapshot of all tables
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        data = {"format": "stackhouse-backup-1", "exportedAt": clock.iso_now(),
                "tables": {t: [dict(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY 1")] for t in tables}}
        z.writestr("stackhouse-data.json", json.dumps(data, ensure_ascii=False, indent=1))
        for img in conn.execute("SELECT name, data FROM images ORDER BY name"):
            z.writestr(f"uploads/{img['name']}", bytes(img["data"]))
    stamp = clock.now_utc().strftime("%Y%m%d-%H%M")
    resp = current_app.response_class(buf.getvalue(), mimetype="application/zip")
    resp.headers["Content-Disposition"] = f'attachment; filename="stackhouse-backup-{stamp}.zip"'
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.post("/cron/tick")
def cron_tick():
    """Called every minute by Supabase (pg_cron) when running serverless: sends due reminders.

    Protected by a random secret that only the database knows (settings.cron_secret).
    """
    import hmac

    from . import scheduler

    conn = get_db()
    expected = settings.get_value(conn, "cron_secret") or ""
    given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
        raise ApiError(401, "Not allowed.")
    return jsonify(ran=scheduler.run_due_jobs(conn))


@bp.get("/admin/timezones")
@require_login(admin=True)
def timezones():
    from zoneinfo import available_timezones
    return jsonify(timezones=sorted(t for t in available_timezones() if "/" in t and not t.startswith("Etc/")))
