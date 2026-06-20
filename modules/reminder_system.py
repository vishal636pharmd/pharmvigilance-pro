# modules/reminder_system.py
# PURPOSE: MODULE 2 — Checks for patients whose 3-day follow-up is due,
#          and prepares the follow-up message (symptom report link).
#
# TWO WAYS THIS RUNS IN THIS PROJECT:
#
#   1. STANDALONE SCRIPT (background scheduler):
#        python modules/reminder_system.py
#      Runs continuously, checks every day at 09:00, prints due reminders.
#      (Real email sending requires Gmail SMTP setup — see SMTP_EMAIL below.
#       Without it, runs in DEMO MODE and just prints what would be sent.)
#
#   2. CALLED FROM FLASK (/reminders route in app.py):
#        Lets you check reminders on-demand from the browser — useful for
#        your demo since you don't need a second terminal running.

import sqlite3
import smtplib
import time
import os
import sys
from email.mime.text      import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime              import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.patient_db import get_due_reminders, mark_reminder_sent

# ─────────────────────────────────────────────────────────────────────────────
# EMAIL CONFIGURATION (optional — leave as-is for DEMO MODE)
# ─────────────────────────────────────────────────────────────────────────────
# To send REAL emails:
#   1. Create a free Gmail account for this project
#   2. Enable 2-Step Verification → Google Account → Security → App Passwords
#   3. Put the 16-character App Password below
#   4. Set ENABLE_REAL_EMAIL = True

ENABLE_REAL_EMAIL = False
SMTP_EMAIL        = "your_pvpro_email@gmail.com"
SMTP_PASSWORD     = "your_16_char_app_password"

SYMPTOM_FORM_BASE_URL = "http://localhost:5000/symptom"


def send_reminder_email(to_email: str, patient_name: str, drug_name: str,
                        patient_id: int, drug_id: int) -> bool:
    """Sends a follow-up email asking about side effects. Returns True if sent."""
    form_link = f"{SYMPTOM_FORM_BASE_URL}?patient_id={patient_id}&drug_id={drug_id}"

    if not ENABLE_REAL_EMAIL:
        print(f"  [DEMO MODE] Would email {to_email}:")
        print(f"             'Hi {patient_name}, how are you feeling after "
              f"{drug_name}? Report here: {form_link}'")
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "PVPro — How are you feeling after your medicine?"
    msg["From"]    = SMTP_EMAIL
    msg["To"]      = to_email

    html_body = f"""
    <html><body style="font-family:sans-serif;background:#0D1B2A;color:#E8F4FD;padding:24px;">
      <h2 style="color:#4FC3F7;">Hi {patient_name},</h2>
      <p>It has been 3 days since you started <strong>{drug_name}</strong>.</p>
      <p>Have you noticed any side effects or unusual symptoms?</p>
      <p style="margin-top:20px;">
        <a href="{form_link}"
           style="background:#1565C0;color:#fff;padding:12px 24px;
                  border-radius:8px;text-decoration:none;font-weight:bold;">
          Report symptoms (30 seconds) →
        </a>
      </p>
    </body></html>
    """
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        print(f"  [REMINDER] Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"  [REMINDER ERROR] {e}")
        return False


def run_daily_reminders() -> list:
    """
    Checks DB for due reminders, sends/logs them, marks as sent.
    Returns the list of reminders that were processed (for display in Flask).
    """
    print(f"[SCHEDULER] Checking reminders: {datetime.now()}")
    due = get_due_reminders()

    if not due:
        print("[SCHEDULER] No reminders due.")
        return []

    processed = []
    for item in due:
        print(f"[SCHEDULER] Due: {item['full_name']} -> {item['drug_name']} "
              f"(reminder_date={item['reminder_date']})")

        # 'phone' is used as email when it contains '@', otherwise demo-logged
        if "@" in (item["phone"] or ""):
            sent = send_reminder_email(item["phone"], item["full_name"],
                                       item["drug_name"], item["patient_id"], item["drug_id"])
        else:
            form_link = f"{SYMPTOM_FORM_BASE_URL}?patient_id={item['patient_id']}&drug_id={item['drug_id']}"
            print(f"  [DEMO MODE - SMS] Would send to {item['phone']}:")
            print(f"             'Hi {item['full_name']}, how are you feeling after "
                  f"{item['drug_name']}? Report here: {form_link}'")
            sent = True

        if sent:
            mark_reminder_sent(item["drug_id"])
            processed.append(item)

    return processed


# Schedule to run every day at 9:00 AM
# (schedule library only needed for the standalone background scheduler below;
#  imported lazily here so the Flask app doesn't require it)
if __name__ == "__main__":
    import schedule

    print("=" * 55)
    print("  PVPro — Reminder Scheduler (Module 2)")
    print("  Runs daily at 09:00. Press Ctrl+C to stop.")
    print("=" * 55)

    schedule.every().day.at("09:00").do(run_daily_reminders)

    run_daily_reminders()  # Run once immediately on start

    while True:
        schedule.run_pending()
        time.sleep(60)
