# modules/push_notifications.py
# PURPOSE: Sends real Web Push notifications to subscribed devices.
# These appear as OS-level popups (like WhatsApp) even when the
# browser tab is not open.

import json
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "database", "pvpro.db")

# ── PASTE YOUR GENERATED VAPID KEYS HERE ─────────────────────────────────────
VAPID_PUBLIC_KEY  = "PASTE_YOUR_PUBLIC_KEY_HERE"
VAPID_PRIVATE_KEY = "PASTE_YOUR_PRIVATE_KEY_HERE"
VAPID_CLAIMS = {"sub": "mailto:vishal636pharmd@gmail.com"}
# ─────────────────────────────────────────────────────────────────────────────


def init_push_table():
    """Creates table to store push subscriptions from devices."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            sub_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id  INTEGER,
            subscription_json TEXT,
            device_name TEXT,
            created_at  TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_subscription(patient_id, subscription_json, device_name="Unknown"):
    """Saves a device's push subscription endpoint from the browser."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Remove old subscriptions for this patient to avoid duplicate sends
    c.execute("DELETE FROM push_subscriptions WHERE patient_id=?", (patient_id,))
    c.execute("""
        INSERT INTO push_subscriptions
        (patient_id, subscription_json, device_name, created_at)
        VALUES (?,?,?,?)
    """, (patient_id, subscription_json, device_name, str(datetime.now())))
    conn.commit()
    conn.close()
    print(f"[Push] Subscription saved for patient_id={patient_id}")


def get_subscriptions_for_patient(patient_id):
    """Returns all push subscriptions for a patient."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT subscription_json FROM push_subscriptions WHERE patient_id=?",
              (patient_id,))
    rows = c.fetchall()
    conn.close()
    return [json.loads(r[0]) for r in rows]


def send_push_to_patient(patient_id, title, body, url="/"):
    """
    Sends a real Web Push notification to all of the patient's devices.
    This appears as an OS popup (like WhatsApp) even when the app is closed.
    """
    if VAPID_PUBLIC_KEY == "PASTE_YOUR_PUBLIC_KEY_HERE":
        print("[Push] VAPID keys not configured — skipping push notification")
        return False

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        print("[Push] pywebpush not installed. Run: pip install pywebpush")
        return False

    subscriptions = get_subscriptions_for_patient(patient_id)
    if not subscriptions:
        print(f"[Push] No subscriptions found for patient_id={patient_id}")
        return False

    payload = json.dumps({
        "title": title,
        "body":  body,
        "url":   url,
        "icon":  "/static/icon-192.png",
        "badge": "/static/icon-192.png"
    })

    sent = 0
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS
            )
            sent += 1
            print(f"[Push] Notification sent successfully")
        except WebPushException as e:
            print(f"[Push] WebPush error: {e}")
        except Exception as e:
            print(f"[Push] Error: {e}")

    return sent > 0


def send_reminder_push(patient_id, full_name, drug_name, drug_id):
    """
    Sends the 3-day follow-up reminder as a real device notification.
    Shows on phone even if the browser is closed.
    """
    return send_push_to_patient(
        patient_id=patient_id,
        title=f"PVPro — Medicine Check-in",
        body=f"Hi {full_name}, how are you feeling after {drug_name}? Tap to report.",
        url=f"/symptom?patient_id={patient_id}&drug_id={drug_id}"
    )