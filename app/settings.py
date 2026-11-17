"""Kitchen configuration: working hours, meal times, cutoff, reminders."""
import copy
import json
import re
from datetime import date
from zoneinfo import ZoneInfo, available_timezones

DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
MEALS = ["lunch", "dinner"]

DEFAULTS = {
    "timezone": "UTC",
    "meals": {
        "lunch": {"enabled": True, "time": "13:30"},
        "dinner": {"enabled": True, "time": "20:00"},
    },
    "workingHours": {d: {"open": True, "start": "08:00", "end": "22:00"} for d in DAYS},
    # Orders for day D lock at `time` on day D - dayOffset.
    "cutoff": {"dayOffset": 1, "time": "22:00"},
    # Each day at these times, houses that have not set tomorrow's food get a reminder.
    "reminderTimes": ["18:00", "21:00"],
    "daysAhead": 7,
    "closedDates": [],
    "urgentOnlyWhenOpen": True,
}

_HM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_HM_END = re.compile(r"^(([01]\d|2[0-3]):[0-5]\d|24:00)$")


def hm_to_min(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


def load(conn) -> dict:
    row = conn.execute("SELECT value FROM settings WHERE key = 'config'").fetchone()
    cfg = copy.deepcopy(DEFAULTS)
    if row:
        stored = json.loads(row["value"])
        for key, value in stored.items():
            if key in cfg:
                cfg[key] = value
    return cfg


def save(conn, cfg: dict):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('config', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (json.dumps(cfg),),
    )


def get_value(conn, key):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_value(conn, key, value):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def bump_menu_version(conn):
    """Tell open apps to reload the menu (dishes or sections changed)."""
    set_value(conn, "menu_version", str(int(get_value(conn, "menu_version") or 0) + 1))


def valid_timezone(name) -> bool:
    if not isinstance(name, str) or not name:
        return False
    if name in available_timezones():
        return True
    try:
        ZoneInfo(name)
        return True
    except Exception:
        return False


def validate(data: dict) -> dict:
    """Return a cleaned copy of a settings payload, or raise ValueError."""
    if not isinstance(data, dict):
        raise ValueError("Settings must be an object.")
    out = copy.deepcopy(DEFAULTS)

    tz = data.get("timezone", out["timezone"])
    if not valid_timezone(tz):
        raise ValueError(f"Unknown timezone: {tz}")
    out["timezone"] = tz

    meals = data.get("meals", {})
    for meal in MEALS:
        m = meals.get(meal, out["meals"][meal])
        t = m.get("time", "")
        if not _HM.match(str(t)):
            raise ValueError(f"{meal.title()} time must look like 13:30.")
        out["meals"][meal] = {"enabled": bool(m.get("enabled")), "time": t}

    wh = data.get("workingHours", {})
    for d in DAYS:
        day = wh.get(d, out["workingHours"][d])
        start, end = str(day.get("start", "")), str(day.get("end", ""))
        if not _HM.match(start) or not _HM_END.match(end):
            raise ValueError(f"Working hours for {d.title()} must look like 08:00 – 22:00.")
        if day.get("open") and hm_to_min(end) <= hm_to_min(start):
            raise ValueError(f"On {d.title()}, closing time must be after opening time.")
        out["workingHours"][d] = {"open": bool(day.get("open")), "start": start, "end": end}

    cutoff = data.get("cutoff", out["cutoff"])
    try:
        offset = int(cutoff.get("dayOffset"))
    except (TypeError, ValueError):
        raise ValueError("Cutoff day must be 0, 1 or 2 days before.")
    if offset not in (0, 1, 2):
        raise ValueError("Cutoff day must be 0, 1 or 2 days before.")
    if not _HM.match(str(cutoff.get("time", ""))):
        raise ValueError("Cutoff time must look like 22:00.")
    out["cutoff"] = {"dayOffset": offset, "time": cutoff["time"]}

    reminders = data.get("reminderTimes", out["reminderTimes"])
    if not isinstance(reminders, list) or len(reminders) > 8:
        raise ValueError("Use at most 8 reminder times.")
    for t in reminders:
        if not _HM.match(str(t)):
            raise ValueError("Reminder times must look like 20:00.")
    out["reminderTimes"] = sorted(set(reminders))

    try:
        days_ahead = int(data.get("daysAhead", out["daysAhead"]))
    except (TypeError, ValueError):
        raise ValueError("Days ahead must be a number.")
    if not 1 <= days_ahead <= 30:
        raise ValueError("Days ahead must be between 1 and 30.")
    out["daysAhead"] = days_ahead

    closed = data.get("closedDates", [])
    if not isinstance(closed, list) or len(closed) > 200:
        raise ValueError("Too many closed dates.")
    clean = set()
    for d in closed:
        try:
            clean.add(date.fromisoformat(str(d)).isoformat())
        except ValueError:
            raise ValueError(f"Closed date {d!r} is not a valid date.")
    out["closedDates"] = sorted(clean)

    out["urgentOnlyWhenOpen"] = bool(data.get("urgentOnlyWhenOpen", True))
    return out
