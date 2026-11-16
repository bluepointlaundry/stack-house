"""In-app notifications plus Web Push delivery to subscribed devices."""
import base64
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from flask import current_app

from . import clock, settings
from .db import connect, transaction

log = logging.getLogger("stackhouse.notify")
_background = ThreadPoolExecutor(max_workers=2, thread_name_prefix="push")


# --- VAPID keys -----------------------------------------------------------------

def ensure_vapid_keys(conn):
    if settings.get_value(conn, "vapid_private_pem"):
        return
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    with transaction(conn):
        # two servers starting at once must end up with the same key pair
        conn.execute("INSERT INTO settings (key, value) VALUES ('vapid_private_pem', ?) ON CONFLICT (key) DO NOTHING",
                     (pem,))
        stored = settings.get_value(conn, "vapid_private_pem")
        if stored == pem:
            settings.set_value(conn, "vapid_public_key", base64.urlsafe_b64encode(pub).rstrip(b"=").decode())


def vapid_public_key(conn):
    return settings.get_value(conn, "vapid_public_key")


# --- recipients -------------------------------------------------------------------

def kitchen_user_ids(conn):
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM users WHERE active = 1 AND (role = 'chef' OR kitchen_alerts = 1)")]
    if not ids:  # nobody is set up as kitchen yet: fall back to admins
        ids = [r["id"] for r in conn.execute("SELECT id FROM users WHERE active = 1 AND is_admin = 1")]
    return ids


def house_user_ids(conn, house_id, exclude=None):
    return [r["id"] for r in conn.execute(
        "SELECT id FROM users WHERE active = 1 AND house_id = ?", (house_id,)) if r["id"] != exclude]


# --- sending ------------------------------------------------------------------------

def notify(conn, user_ids, title, body="", url="/", kind="info", urgent=False):
    """Store an in-app notification for each user and push it to their devices.

    Call this *after* the data change has been committed.
    """
    ids = sorted(set(user_ids))
    if not ids:
        return 0
    now = clock.iso_now()
    with transaction(conn):
        for uid in ids:
            conn.execute(
                "INSERT INTO notifications (user_id, title, body, url, kind, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, title, body, url, kind, now),
            )
    marks = ",".join("?" * len(ids))
    subs = [dict(r) for r in conn.execute(
        f"SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE user_id IN ({marks})", ids)]
    if subs:
        payload = json.dumps({"title": title, "body": body, "url": url, "kind": kind, "urgent": urgent,
                              "tag": f"{kind}-{now}"})
        cfg = current_app.config
        if cfg.get("PUSH_SENDER"):  # tests swap in a fake sender
            cfg["PUSH_SENDER"](subs, payload, urgent)
            return len(ids)
        job = (subs, payload, urgent, settings.get_value(conn, "vapid_private_pem"),
               cfg["VAPID_SUBJECT"], cfg["DATABASE"])
        if cfg.get("PUSH_SYNC"):
            # Serverless (Vercel): the request is frozen once it returns, so send now.
            _send_all(*job)
        else:
            _background.submit(_send_all, *job)
    return len(ids)


def _send_all(subs, payload, urgent, vapid_pem, subject, database):
    try:
        from py_vapid import Vapid
        from pywebpush import WebPushException, webpush
    except ImportError:
        log.warning("pywebpush is not installed; skipping push delivery")
        return
    vapid = Vapid.from_pem(vapid_pem.encode())

    def send(s):
        try:
            webpush(
                {"endpoint": s["endpoint"], "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}},
                data=payload,
                vapid_private_key=vapid,
                vapid_claims={"sub": subject},
                ttl=900 if urgent else 12 * 3600,
                headers={"Urgency": "high" if urgent else "normal"},
                timeout=8,
            )
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                return s["endpoint"]  # this device unsubscribed
            log.warning("push failed (%s): %s", status, e)
        except Exception as e:  # network errors etc. must not break the request
            log.warning("push failed: %s", e)
        return None

    with ThreadPoolExecutor(max_workers=min(8, len(subs))) as pool:
        dead = [ep for ep in pool.map(send, subs) if ep]
    if dead:
        conn = connect(database)
        try:
            for endpoint in dead:
                conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        finally:
            conn.close()
