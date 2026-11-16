"""In-app notifications plus Web Push delivery to subscribed devices."""
import base64
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from flask import current_app

from . import clock, settings
from .db import connect, transaction

log = logging.getLogger("stackhouse.notify")
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="push")


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
    settings.set_value(conn, "vapid_private_pem", pem)
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
        sender = current_app.config.get("PUSH_SENDER")
        if sender:  # tests swap in a fake sender
            sender(subs, payload, urgent)
        else:
            _pool.submit(_send_all, subs, payload, urgent,
                         settings.get_value(conn, "vapid_private_pem"),
                         current_app.config["VAPID_SUBJECT"], current_app.config["DB_PATH"])
    return len(ids)


def _send_all(subs, payload, urgent, vapid_pem, subject, db_path):
    try:
        from py_vapid import Vapid
        from pywebpush import WebPushException, webpush
    except ImportError:
        log.warning("pywebpush is not installed; skipping push delivery")
        return
    vapid = Vapid.from_pem(vapid_pem.encode())
    dead = []
    for s in subs:
        try:
            webpush(
                {"endpoint": s["endpoint"], "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}},
                data=payload,
                vapid_private_key=vapid,
                vapid_claims={"sub": subject},
                ttl=900 if urgent else 12 * 3600,
                headers={"Urgency": "high" if urgent else "normal"},
                timeout=10,
            )
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                dead.append(s["endpoint"])
            else:
                log.warning("push failed (%s): %s", status, e)
        except Exception as e:  # network errors etc. must not kill the worker
            log.warning("push failed: %s", e)
    if dead:
        conn = connect(db_path)
        try:
            for endpoint in dead:
                conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        finally:
            conn.close()
