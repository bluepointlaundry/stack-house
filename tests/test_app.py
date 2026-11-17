"""End-to-end API tests with a frozen clock.

Run:  .venv\\Scripts\\python -m unittest discover -s tests -v
"""
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from app import clock, create_app
from app.db import connect
from app.scheduler import run_due_jobs

TZ = ZoneInfo("Asia/Bahrain")
PG_URL = os.environ.get("STACKHOUSE_TEST_DATABASE_URL")
_pg_server = None


def setUpModule():
    global PG_URL, _pg_server
    if os.environ.get("STACKHOUSE_TEST_PG") == "1" and not PG_URL:
        import pgserver
        _pg_server = pgserver.get_server(tempfile.mkdtemp(prefix="stackhouse-pg-"), cleanup_mode="stop")
        PG_URL = _pg_server.get_uri()


def fresh_db(tmpdir):
    """Config for an empty database: a wiped Postgres schema, or a new SQLite file."""
    if PG_URL:
        conn = connect(PG_URL)
        try:
            conn.script("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        finally:
            conn.close()
        return {"DATABASE": PG_URL}
    return {"DATA_DIR": tmpdir}


def at(day, hm):
    h, m = map(int, hm.split(":"))
    return datetime(2026, 11, day, h, m, tzinfo=TZ)


class StackHouseTest(unittest.TestCase):
    def setUp(self):
        clock.set_fake_now(at(16, "10:00"))  # Monday 16 Nov 2026, 10:00 kitchen time
        self.dir = tempfile.mkdtemp()
        self.pushes = []
        self.app = create_app({
            **fresh_db(self.dir), "SCHEDULER": False, "TESTING": True,
            "PUSH_SENDER": lambda subs, payload, urgent: self.pushes.append((subs, payload, urgent)),
        })
        self.admin = self.app.test_client()
        r = self.admin.post("/api/setup", json={
            "name": "Mohammed", "username": "mohammed", "password": "secret1",
            "houseId": 1, "sampleMenu": True, "timezone": "Asia/Bahrain"})
        self.assertEqual(r.status_code, 200, r.json)
        self.make_user("salem", "Salem", role="member", houseId=2)
        self.make_user("ayman", "Ayman", role="member", houseId=3)
        self.make_user("chef", "Chef Ravi", role="chef")
        self.salem = self.login("salem")
        self.ayman = self.login("ayman")
        self.chef = self.login("chef")
        self.dishes = self.admin.get("/api/menu").json["dishes"]

    def tearDown(self):
        clock.set_fake_now(None)
        shutil.rmtree(self.dir, ignore_errors=True)

    # helpers -----------------------------------------------------------------
    def make_user(self, username, name, **extra):
        r = self.admin.post("/api/admin/users", json={"username": username, "name": name, "password": "secret1", **extra})
        self.assertEqual(r.status_code, 200, r.json)
        return r.json

    def login(self, username):
        c = self.app.test_client()
        r = c.post("/api/login", json={"username": username, "password": "secret1"})
        self.assertEqual(r.status_code, 200, r.json)
        return c

    def dish(self, name):
        return next(d for d in self.dishes if d["name"] == name)["id"]

    def notes(self, client):
        return client.get("/api/notifications").json["notifications"]

    def plan(self, client, day, meals, **extra):
        return client.put(f"/api/plan/{day}", json={"meals": meals, **extra})

    def db(self):
        return connect(self.app.config["DATABASE"])

    # tests ---------------------------------------------------------------------
    def test_setup_only_once_and_login(self):
        r = self.app.test_client().post("/api/setup", json={"name": "X", "username": "xx", "password": "secret1", "houseId": 1})
        self.assertEqual(r.status_code, 409)
        bad = self.app.test_client().post("/api/login", json={"username": "salem", "password": "nope"})
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(self.app.test_client().get("/api/days").status_code, 401)

    def test_writes_require_json(self):
        r = self.salem.post("/api/urgent", data="items=1")
        self.assertEqual(r.status_code, 415)

    def test_plan_tomorrow_notifies_chef(self):
        r = self.plan(self.salem, "2026-11-17", {
            "lunch": {"need": True, "notes": "less salt", "items": [
                {"dishId": self.dish("Hummus"), "servings": 5}, {"dishId": self.dish("Chicken machboos"), "servings": 6}]},
            "dinner": {"need": False},
        })
        self.assertEqual(r.status_code, 200, r.json)
        self.assertTrue(r.json["isSet"])
        self.assertEqual(r.json["meals"]["lunch"]["totalServings"], 11)
        self.assertEqual(r.json["meals"]["dinner"]["status"], "skipped")
        chef_notes = self.notes(self.chef)
        self.assertIn("Salem family is set for Tue 17 Nov", chef_notes[0]["title"])
        self.assertIn("Hummus ×5", chef_notes[0]["body"])
        self.assertIn("Dinner: not needed", chef_notes[0]["body"])

        # an edit is reported as an update; saving the same thing again sends nothing new
        self.plan(self.salem, "2026-11-17", {"dinner": {"need": True, "items": [{"dishId": self.dish("Lentil soup"), "servings": 2}]}})
        self.assertIn("updated", self.notes(self.chef)[0]["title"])
        count = len(self.notes(self.chef))
        self.plan(self.salem, "2026-11-17", {"dinner": {"need": True, "items": [{"dishId": self.dish("Lentil soup"), "servings": 2}]}})
        self.assertEqual(len(self.notes(self.chef)), count)

        kitchen = self.chef.get("/api/kitchen?date=2026-11-17").json["day"]
        lunch = next(m for m in kitchen["meals"] if m["meal"] == "lunch")
        self.assertEqual(lunch["servings"], 11)
        self.assertEqual([h["status"] for h in lunch["houses"]], [None, "ordered", None, None])

    def test_plan_validation(self):
        self.assertEqual(self.plan(self.salem, "2026-11-17", {"lunch": {"need": True, "items": []}}).status_code, 400)
        self.assertEqual(self.plan(self.salem, "2026-11-17", {"lunch": {"need": True, "items": [{"dishId": 9999, "servings": 2}]}}).status_code, 400)
        self.assertEqual(self.plan(self.salem, "2026-11-17", {"lunch": {"need": True, "items": [{"dishId": self.dish("Hummus"), "servings": 0}]}}).status_code, 400)
        self.assertEqual(self.plan(self.salem, "2026-12-30", {"lunch": {"need": False}}).status_code, 400)  # too far ahead
        # members cannot order for another family
        r = self.plan(self.salem, "2026-11-17", {"lunch": {"need": False}}, houseId=3)
        self.assertEqual(r.status_code, 403)

    def test_cutoff_locks_members_but_not_admins(self):
        clock.set_fake_now(at(16, "22:01"))
        r = self.plan(self.salem, "2026-11-17", {"lunch": {"need": False}})
        self.assertEqual(r.status_code, 409)
        r = self.plan(self.admin, "2026-11-17", {"lunch": {"need": False}}, houseId=2)
        self.assertEqual(r.status_code, 200, r.json)
        self.assertIn("Late change", self.notes(self.chef)[0]["title"])
        # the day after tomorrow is still open
        self.assertEqual(self.plan(self.salem, "2026-11-18", {"lunch": {"need": False}}).status_code, 200)

    def test_inactive_dish_cannot_be_ordered(self):
        hummus = self.dish("Hummus")
        self.assertEqual(self.admin.put(f"/api/dishes/{hummus}", json={"active": False}).status_code, 200)
        self.assertNotIn(hummus, [d["id"] for d in self.salem.get("/api/menu").json["dishes"]])
        r = self.plan(self.salem, "2026-11-17", {"lunch": {"need": True, "items": [{"dishId": hummus, "servings": 2}]}})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.salem.post("/api/dishes", json={"name": "x", "categoryId": 1}).status_code, 403)

    def test_urgent_order_flow(self):
        # chef has a push subscription, so the urgent alert is pushed with high urgency
        self.chef.post("/api/push/subscribe", json={"subscription": {
            "endpoint": "https://push.example.com/abc", "keys": {"p256dh": "k", "auth": "a"}}})
        r = self.salem.post("/api/urgent", json={"items": [{"dishId": self.dish("Fruit salad"), "servings": 3}],
                                                 "notes": "for the kids", "neededBy": "in 30 min"})
        self.assertEqual(r.status_code, 200, r.json)
        oid = r.json["id"]
        self.assertTrue(self.notes(self.chef)[0]["title"].startswith("🚨 Order now: Salem"))
        self.assertTrue(self.pushes and self.pushes[-1][2] is True)

        self.assertEqual(self.salem.post(f"/api/urgent/{oid}/status", json={"status": "accepted"}).status_code, 403)
        r = self.chef.post(f"/api/urgent/{oid}/status", json={"status": "accepted", "eta": "20 min"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("20 min", self.notes(self.salem)[0]["body"])
        self.assertEqual(self.salem.post(f"/api/urgent/{oid}/cancel", json={}).status_code, 409)  # already accepted
        self.assertEqual(self.chef.post(f"/api/urgent/{oid}/status", json={"status": "ready"}).status_code, 200)
        self.assertEqual(self.chef.post(f"/api/urgent/{oid}/status", json={"status": "accepted"}).status_code, 409)
        self.assertEqual(self.ayman.post(f"/api/urgent/{oid}/cancel", json={}).status_code, 403)

    def test_urgent_needs_open_kitchen(self):
        clock.set_fake_now(at(16, "23:00"))
        r = self.salem.post("/api/urgent", json={"notes": "tea please"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.salem.get("/api/bootstrap").json["kitchen"]["nextOpen"], {"date": "2026-11-17", "time": "08:00"})

    def test_reminders_cutoff_summary_and_brief(self):
        self.plan(self.salem, "2026-11-17", {"lunch": {"need": False}, "dinner": {"need": False}})
        self.plan(self.ayman, "2026-11-17", {"lunch": {"need": False}})  # dinner still missing
        conn = self.db()
        try:
            clock.set_fake_now(at(16, "17:59"))
            self.assertEqual(run_due_jobs(conn), [])
            clock.set_fake_now(at(16, "18:00"))
            self.assertEqual(run_due_jobs(conn), ["reminder:2026-11-16:18:00"])
            self.assertEqual(run_due_jobs(conn), [])  # never twice
        finally:
            conn.close()
        self.assertEqual(self.notes(self.salem), [])  # Salem already set tomorrow
        ayman = self.notes(self.ayman)
        self.assertEqual(len(ayman), 1)
        self.assertIn("set dinner for Tue 17 Nov", ayman[0]["body"])
        self.assertEqual(self.notes(self.admin)[0]["kind"], "reminder")  # Mohammed's family has not set anything

        conn = self.db()
        try:
            clock.set_fake_now(at(16, "22:05"))
            self.assertEqual(run_due_jobs(conn), ["cutoff:2026-11-17"])
            summary = self.notes(self.chef)[0]
            self.assertIn("Orders locked for Tue 17 Nov", summary["title"])
            self.assertIn("Not set: Mohammed, Ayman, Sabeeh", summary["body"])
            clock.set_fake_now(at(17, "08:10"))
            self.assertEqual(run_due_jobs(conn), ["brief:2026-11-17"])
            self.assertIn("Today in the kitchen", self.notes(self.chef)[0]["title"])
        finally:
            conn.close()

    def test_closed_days_and_settings(self):
        bad = self.admin.put("/api/admin/settings", json={**self.admin.get("/api/bootstrap").json["settings"],
                                                           "reminderTimes": ["25:00"]})
        self.assertEqual(bad.status_code, 400)
        cfg = self.admin.get("/api/bootstrap").json["settings"]
        cfg["closedDates"] = ["2026-11-17"]
        cfg["workingHours"]["wed"]["open"] = False
        cfg["meals"]["dinner"]["enabled"] = False
        r = self.admin.put("/api/admin/settings", json=cfg)
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(self.plan(self.salem, "2026-11-17", {"lunch": {"need": False}}).status_code, 400)  # closed date
        self.assertEqual(self.plan(self.salem, "2026-11-18", {"lunch": {"need": False}}).status_code, 400)  # closed Wednesday
        r = self.plan(self.salem, "2026-11-19", {"dinner": {"need": False}})
        self.assertEqual(r.status_code, 400)  # dinner switched off
        r = self.plan(self.salem, "2026-11-19", {"lunch": {"need": False}})
        self.assertTrue(r.json["isSet"])  # only lunch is served now
        self.assertEqual(self.salem.put("/api/admin/settings", json=cfg).status_code, 403)

    def test_admin_guards(self):
        users = self.admin.get("/api/admin/users").json["users"]
        me = next(u for u in users if u["username"] == "mohammed")
        r = self.admin.put(f"/api/admin/users/{me['id']}", json={"isAdmin": False})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.admin.delete(f"/api/admin/users/{me['id']}", json={}).status_code, 400)
        # a deactivated user is logged out immediately
        salem = next(u for u in users if u["username"] == "salem")
        self.admin.put(f"/api/admin/users/{salem['id']}", json={"active": False})
        self.assertEqual(self.salem.get("/api/days").status_code, 401)
        # a family with members cannot be deleted
        self.assertEqual(self.admin.delete("/api/admin/houses/3", json={}).status_code, 409)

    def test_backup_download(self):
        import io
        import json
        import zipfile
        tiny_png = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
        r = self.admin.post("/api/dishes", json={"name": "Photo dish", "categoryId": 1, "image": tiny_png})
        self.assertEqual(r.status_code, 200, r.json)
        img = self.admin.get(r.json["image"])
        self.assertEqual((img.status_code, img.mimetype), (200, "image/png"))

        self.assertEqual(self.salem.get("/api/admin/backup").status_code, 403)
        r = self.admin.get("/api/admin/backup")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["Content-Disposition"])
        with zipfile.ZipFile(io.BytesIO(r.data)) as z:
            data = json.loads(z.read("stackhouse-data.json"))
            photos = [n for n in z.namelist() if n.startswith("uploads/")]
        self.assertEqual(len(data["tables"]["users"]), 4)
        self.assertEqual(len(data["tables"]["houses"]), 4)
        self.assertEqual(len(photos), 1)

    def test_cron_tick_needs_the_secret(self):
        self.assertEqual(self.app.test_client().post("/api/cron/tick", json={}).status_code, 401)
        bad = self.app.test_client().post("/api/cron/tick", json={}, headers={"Authorization": "Bearer nope"})
        self.assertEqual(bad.status_code, 401)
        conn = self.db()
        try:
            secret = conn.execute("SELECT value FROM settings WHERE key = 'cron_secret'").fetchone()[0]
        finally:
            conn.close()
        clock.set_fake_now(at(16, "18:00"))
        r = self.app.test_client().post("/api/cron/tick", json={}, headers={"Authorization": f"Bearer {secret}"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("reminder:2026-11-16:18:00", r.json["ran"])
        self.assertTrue(self.admin.get("/api/bootstrap").json["lastTick"])

    def test_login_throttle(self):
        c = self.app.test_client()
        for _ in range(8):
            self.assertEqual(c.post("/api/login", json={"username": "salem", "password": "wrong"}).status_code, 401)
        self.assertEqual(c.post("/api/login", json={"username": "salem", "password": "secret1"}).status_code, 429)

    def test_bulk_menu_import_replaces_sample_menu(self):
        from app import menu_data
        # an order placed from the sample menu must survive the replacement
        self.plan(self.salem, "2026-11-17", {"lunch": {"need": True, "items": [{"dishId": self.dish("Hummus"), "servings": 3}]}})

        self.assertEqual(self.salem.post("/api/admin/menu/import", json={"text": menu_data.MENU}).status_code, 403)
        preview = self.admin.post("/api/admin/menu/import", json={"text": menu_data.MENU, "replace": True}).json
        self.assertEqual([s["name"] for s in preview["sections"]], ["Appetizers", "Main Dishes", "Fatayer", "Sandwiches"])
        self.assertEqual((preview["added"], preview["removeDishes"]), (35, 18))
        self.assertEqual(set(preview["removeSections"]), {"Starters", "Soups", "Salads", "Main dish", "Desserts"})
        self.assertEqual(len(self.admin.get("/api/menu").json["dishes"]), 18)  # preview changes nothing

        r = self.admin.post("/api/admin/menu/import", json={"text": menu_data.MENU, "replace": True, "apply": True})
        self.assertEqual(r.status_code, 200, r.json)
        menu = self.salem.get("/api/menu").json
        self.assertEqual([(c["name"], c["icon"]) for c in menu["categories"]],
                         [("Appetizers", "🥟"), ("Main Dishes", "🍛"), ("Fatayer", "🫓"), ("Sandwiches", "🥪")])

        def section(name):
            cid = next(c["id"] for c in menu["categories"] if c["name"] == name)
            return [d["name"] for d in sorted((d for d in menu["dishes"] if d["categoryId"] == cid),
                                              key=lambda d: d["sortOrder"])]
        self.assertEqual(section("Appetizers"), ["Chicken and mushroom pot pie", "Fried shrimps"])
        main = section("Main Dishes")
        self.assertEqual(len(main), 20)
        self.assertEqual((main[0], main[14], main[19]),
                         ("Chicken machbous", "Grilled chicken with honey mustard sauce and white rice",
                          "Meat doner shawarma"))
        self.assertEqual(section("Sandwiches")[1], "Chicken salad sandwich (Greek yogurt base)")
        old = self.salem.get("/api/plan/2026-11-17").json["meals"]["lunch"]
        self.assertEqual(old["items"][0]["name"], "Hummus")

        # pasting the same list again (without replace) adds nothing
        again = self.admin.post("/api/admin/menu/import", json={"text": menu_data.MENU}).json
        self.assertEqual((again["added"], again["skipped"]), (0, 35))

    def test_menu_text_parsing(self):
        from app.menu_import import parse_menu
        got = parse_menu("Wraps:\nfalafel wrap - with tahini\n\nDrinks\n1) Tea\n2) Coffee\n")
        self.assertEqual(got, [("Wraps", [("Falafel wrap", "with tahini")]),
                               ("Drinks", [("Tea", ""), ("Coffee", "")])])

    def test_sections_can_be_added_renamed_and_reordered(self):
        r = self.admin.post("/api/categories", json={"name": "Breakfast ", "icon": "🍳"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([c["name"] for c in r.json["categories"]][-1], "Breakfast")  # new sections go last
        self.assertEqual(self.admin.post("/api/categories", json={"name": "breakfast"}).json["error"],
                         "That section already exists.")
        new = next(c for c in r.json["categories"] if c["name"] == "Breakfast")
        self.assertEqual(new["dishCount"], 0)
        r = self.admin.put(f"/api/categories/{new['id']}", json={"name": "Morning breakfast", "move": "up"})
        names = [c["name"] for c in r.json["categories"]]
        self.assertEqual(names[-2:], ["Morning breakfast", "Desserts"])
        soups = next(c for c in r.json["categories"] if c["name"] == "Soups")
        self.assertEqual(self.admin.delete(f"/api/categories/{soups['id']}", json={}).status_code, 409)  # has dishes

    def test_password_change_signs_out_other_sessions(self):
        other = self.login("salem")
        r = self.salem.post("/api/me/password", json={"current": "secret1", "new": "newpass1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.salem.get("/api/days").status_code, 200)
        self.assertEqual(other.get("/api/days").status_code, 401)


class LiveHostingTest(unittest.TestCase):
    """Behaviour behind the hosting provider's https proxy."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.app = create_app({**fresh_db(self.dir), "SCHEDULER": False, "TESTING": True,
                               "TRUST_PROXY": True, "FORCE_HTTPS": True, "SESSION_COOKIE_SECURE": True})
        self.c = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_http_redirects_to_https(self):
        r = self.c.get("/plan?x=1", headers={"X-Forwarded-Proto": "http", "Host": "stackhouse.example.com"})
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r.headers["Location"], "https://stackhouse.example.com/plan?x=1")

    def test_https_requests_get_hsts_and_secure_cookie(self):
        r = self.c.get("/", headers={"X-Forwarded-Proto": "https"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("max-age", r.headers["Strict-Transport-Security"])
        r.close()
        r = self.c.post("/api/setup", headers={"X-Forwarded-Proto": "https"}, json={
            "name": "A", "username": "admin", "password": "secret1", "houseId": 1})
        self.assertEqual(r.status_code, 200, r.json)
        cookie = r.headers["Set-Cookie"]
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)

    def test_database_address_and_password_are_joined(self):
        from app import resolve_database
        url = "postgresql://postgres.abc:[YOUR-PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
        got = resolve_database({}, {"DATABASE_URL": f" {url} ", "DATABASE_PASSWORD": "p@ss word"}, True)
        self.assertEqual(got, url.replace("[YOUR-PASSWORD]", "p%40ss%20word"))
        with self.assertRaises(RuntimeError):
            resolve_database({}, {"DATABASE_URL": url}, True)  # password missing
        with self.assertRaises(RuntimeError):
            resolve_database({}, {}, True)  # nothing configured on Vercel
        from app.db import clean_postgres_url
        cleaned = clean_postgres_url("postgres://u:p@db.example.com:6543/postgres?supa=base-pooler.x&sslmode=require")
        self.assertEqual(cleaned, "postgres://u:p@db.example.com:6543/postgres?sslmode=require")

    def test_live_menu_is_applied_only_once(self):
        db_cfg = {"DATABASE": self.app.config["DATABASE"], "SCHEDULER": False, "TESTING": True, "APPLY_MENU": True}
        first = create_app(db_cfg).test_client()
        first.post("/api/setup", headers={"X-Forwarded-Proto": "https"}, json={
            "name": "A", "username": "admin", "password": "secret1", "houseId": 1})
        menu = first.get("/api/menu", headers={"X-Forwarded-Proto": "https"}).json
        self.assertEqual(len(menu["dishes"]), 35)
        self.assertEqual(menu["categories"][0]["name"], "Appetizers")
        dish = menu["dishes"][0]["id"]
        first.delete(f"/api/dishes/{dish}", json={}, headers={"X-Forwarded-Proto": "https"})
        # a later start of the live site must not undo the admin's own edits
        second = create_app(db_cfg).test_client()
        second.post("/api/login", headers={"X-Forwarded-Proto": "https"},
                    json={"username": "admin", "password": "secret1"})
        self.assertEqual(len(second.get("/api/menu", headers={"X-Forwarded-Proto": "https"}).json["dishes"]), 34)

    def test_timer_setup_fails_gracefully(self):
        from app.db import ensure_supabase_timer
        ok, msg = ensure_supabase_timer(self.app.config["DATABASE"], "bad host'; drop table users; --")
        self.assertFalse(ok)
        self.assertIn("Invalid site address", msg)
        # local SQLite / plain Postgres have no pg_cron: must report, not crash
        ok, msg = ensure_supabase_timer(self.app.config["DATABASE"], "stack-house.vercel.app")
        self.assertFalse(ok)
        self.assertIn("Could not start the reminder timer", msg)

    def test_health_check_works_over_plain_http(self):
        r = self.c.get("/healthz")  # the host's health check calls without the proxy headers
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json, {"ok": True})


if __name__ == "__main__":
    unittest.main()
