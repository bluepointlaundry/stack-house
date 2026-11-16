"""Single source of "now" so tests can freeze time."""
from datetime import datetime, timezone

_fake_now = None


def now_utc() -> datetime:
    return _fake_now if _fake_now is not None else datetime.now(timezone.utc)


def set_fake_now(dt):
    """Freeze the clock (tests only). Pass None to unfreeze."""
    global _fake_now
    if dt is not None and dt.tzinfo is None:
        raise ValueError("fake time must be timezone-aware")
    _fake_now = dt.astimezone(timezone.utc) if dt is not None else None


def iso_now() -> str:
    return now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
