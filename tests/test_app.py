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


def at(day, hm):
    h, m = map(int, hm.split(":"))
    return datetime(2026, 11, day, h, m, tzinfo=TZ)


class StackHouseTest(unittest.TestCase):
    def setUp(self):
        clock.set_fake_now(at(16, "10:00"))  # Monday 16 Nov 2026, 10:00 kitchen time
        self.dir = tempfile.mkdtemp()
        self.pushes = []
        self.app = create_app({
            "DATA_DIR": self.dir, "SCHEDULER": False, "TESTING": True,
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
        return connect(self.app.config["DB_PATH"])

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
        import sqlite3
        import zipfile
        self.assertEqual(self.salem.get("/api/admin/backup").status_code, 403)
        r = self.admin.get("/api/admin/backup")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["Content-Disposition"])
        with zipfile.ZipFile(io.BytesIO(r.data)) as z:
            path = os.path.join(self.dir, "restored.db")
            with open(path, "wb") as f:
                f.write(z.read("stackhouse.db"))
        conn = sqlite3.connect(path)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 4)
        finally:
            conn.close()

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
        self.app = create_app({"DATA_DIR": self.dir, "SCHEDULER": False, "TESTING": True,
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

    def test_health_check_works_over_plain_http(self):
        r = self.c.get("/healthz")  # the host's health check calls without the proxy headers
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json, {"ok": True})


if __name__ == "__main__":
    unittest.main()
