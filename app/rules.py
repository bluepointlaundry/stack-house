"""Time rules for the kitchen: open hours, service days and order cutoffs.

Every date/time decision is made in the kitchen's configured timezone.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import clock
from .settings import DAYS, MEALS, hm_to_min


def tz(cfg):
    return ZoneInfo(cfg["timezone"])


def local_now(cfg) -> datetime:
    return clock.now_utc().astimezone(tz(cfg))


def today(cfg) -> date:
    return local_now(cfg).date()


def at(cfg, d: date, hm: str) -> datetime:
    """Aware datetime for wall-clock time `hm` on day `d` ("24:00" = next midnight)."""
    mins = hm_to_min(hm)
    if mins >= 24 * 60:
        return datetime.combine(d + timedelta(days=1), time(0, 0), tzinfo=tz(cfg))
    return datetime.combine(d, time(mins // 60, mins % 60), tzinfo=tz(cfg))


def weekday_key(d: date) -> str:
    return DAYS[(d.weekday() + 1) % 7]  # Python: Monday=0; DAYS starts on Sunday


def day_hours(cfg, d: date):
    """Working hours for a date, or None when the kitchen is closed that day."""
    if d.isoformat() in cfg["closedDates"]:
        return None
    wh = cfg["workingHours"][weekday_key(d)]
    return wh if wh["open"] else None


def enabled_meals(cfg):
    return [m for m in MEALS if cfg["meals"][m]["enabled"]]


def is_service_day(cfg, d: date) -> bool:
    return day_hours(cfg, d) is not None and bool(enabled_meals(cfg))


def lock_at(cfg, d: date) -> datetime:
    c = cfg["cutoff"]
    return at(cfg, d - timedelta(days=c["dayOffset"]), c["time"])


def is_locked(cfg, d: date, now=None) -> bool:
    return (now or local_now(cfg)) >= lock_at(cfg, d)


def last_plannable(cfg) -> date:
    return today(cfg) + timedelta(days=cfg["daysAhead"])


def plannable_dates(cfg):
    t = today(cfg)
    return [t + timedelta(days=i) for i in range(cfg["daysAhead"] + 1)]


def kitchen_status(cfg) -> dict:
    now = local_now(cfg)
    d = now.date()
    wh = day_hours(cfg, d)
    if wh and at(cfg, d, wh["start"]) <= now < at(cfg, d, wh["end"]):
        return {"open": True, "until": wh["end"], "nextOpen": None}
    for i in range(15):
        dd = d + timedelta(days=i)
        wh = day_hours(cfg, dd)
        if wh and at(cfg, dd, wh["start"]) > now:
            return {"open": False, "until": None, "nextOpen": {"date": dd.isoformat(), "time": wh["start"]}}
    return {"open": False, "until": None, "nextOpen": None}


def fmt_day(d: date) -> str:
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


def fmt_lock(cfg, d: date) -> str:
    """Human description of when orders for `d` lock, relative to today."""
    lock = lock_at(cfg, d)
    days = (lock.date() - today(cfg)).days
    when = {0: "today", 1: "tomorrow"}.get(days, fmt_day(lock.date()))
    return f"{lock.strftime('%H:%M')} {when}"
