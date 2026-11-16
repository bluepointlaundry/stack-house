"""Background jobs: daily reminders, cutoff summary and the chef's morning brief.

`run_due_jobs` is idempotent: every job claims a unique key in `job_runs`, so a restart,
a second worker or a fast loop never sends the same reminder twice.
"""
import logging
import threading
import time
from datetime import timedelta

from . import clock, notify, orders, rules, settings
from .db import connect

log = logging.getLogger("stackhouse.scheduler")
CATCH_UP = timedelta(minutes=60)  # a job still runs if the server was down for less than this
_started = False


def _claim(conn, key):
    """True for exactly one caller per key, even with several servers ticking at once."""
    row = conn.execute("INSERT INTO job_runs (key, ran_at) VALUES (?, ?) ON CONFLICT (key) DO NOTHING RETURNING key",
                       (key, clock.iso_now())).fetchone()
    return row is not None


def _due(now, at):
    return at <= now < at + CATCH_UP


def run_due_jobs(conn):
    cfg = settings.load(conn)
    settings.set_value(conn, "last_tick", clock.iso_now())
    now = rules.local_now(cfg)
    today = now.date()
    tomorrow = today + timedelta(days=1)
    done = []

    # 1. Morning brief for the kitchen when it opens.
    hours = rules.day_hours(cfg, today)
    if hours and rules.enabled_meals(cfg) and _due(now, rules.at(cfg, today, hours["start"])):
        if _claim(conn, f"brief:{today}"):
            send_brief(conn, cfg, today)
            done.append(f"brief:{today}")

    # 2. Reminders to houses that have not set tomorrow's food yet.
    if rules.is_service_day(cfg, tomorrow) and not rules.is_locked(cfg, tomorrow, now):
        for hm in cfg["reminderTimes"]:
            if _due(now, rules.at(cfg, today, hm)) and _claim(conn, f"reminder:{today}:{hm}"):
                send_reminders(conn, cfg, tomorrow)
                done.append(f"reminder:{today}:{hm}")

    # 3. Summary to the kitchen when a day's orders lock.
    for i in range(cfg["cutoff"]["dayOffset"] + 1):
        d = today + timedelta(days=i)
        if rules.is_service_day(cfg, d) and _due(now, rules.lock_at(cfg, d)):
            if _claim(conn, f"cutoff:{d}"):
                send_cutoff_summary(conn, cfg, d)
                done.append(f"cutoff:{d}")

    # 4. Housekeeping once a day.
    if _claim(conn, f"cleanup:{today}"):
        old = (clock.now_utc() - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute("DELETE FROM notifications WHERE created_at < ?", (old,))
        conn.execute("DELETE FROM job_runs WHERE ran_at < ?", (old,))
        conn.execute("DELETE FROM login_failures WHERE at < ?", (old,))
    return done


def houses_not_set(conn, cfg, d):
    meals = rules.enabled_meals(cfg)
    result = []
    for h in orders.houses(conn):
        got = orders.day_orders(conn, h["id"], d)
        missing = [m for m in meals if m not in got]
        if missing:
            result.append((h, missing))
    return result


def send_reminders(conn, cfg, d):
    for house, missing in houses_not_set(conn, cfg, d):
        members = notify.house_user_ids(conn, house["id"])
        if not members:
            continue
        what = " & ".join(missing)
        notify.notify(
            conn, members,
            title="🍽️ What is your family eating tomorrow?",
            body=f"Please set {what} for {rules.fmt_day(d)} before {rules.fmt_lock(cfg, d)}.",
            url=f"/#/plan/{d.isoformat()}", kind="reminder",
        )


def send_cutoff_summary(conn, cfg, d):
    day = orders.kitchen_day(conn, cfg, d)
    lines = [orders.meal_line(day, m["meal"]) for m in day["meals"]]
    missing = [h["name"] for h, _ in houses_not_set(conn, cfg, d)]
    if missing:
        lines.append("Not set: " + ", ".join(missing))
    notify.notify(
        conn, notify.kitchen_user_ids(conn),
        title=f"🔒 Orders locked for {rules.fmt_day(d)}",
        body=" · ".join(lines), url=f"/#/kitchen/{d.isoformat()}", kind="cutoff",
    )


def send_brief(conn, cfg, d):
    day = orders.kitchen_day(conn, cfg, d)
    lines = [f"{orders.meal_line(day, m['meal'])} ({m['time']})" for m in day["meals"]]
    notify.notify(
        conn, notify.kitchen_user_ids(conn),
        title="☀️ Today in the kitchen",
        body=" · ".join(lines), url=f"/#/kitchen/{d.isoformat()}", kind="brief",
    )


def start(app, interval=30):
    global _started
    if _started:
        return
    _started = True

    def loop():
        while True:
            try:
                with app.app_context():
                    conn = connect(app.config["DATABASE"])
                    try:
                        for job in run_due_jobs(conn):
                            log.info("ran job %s", job)
                    finally:
                        conn.close()
            except Exception:
                log.exception("scheduler tick failed")
            time.sleep(interval)

    threading.Thread(target=loop, name="scheduler", daemon=True).start()
