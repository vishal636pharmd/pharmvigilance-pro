# modules/reminder_system.py
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.patient_db import get_due_reminders, mark_reminder_sent

SYMPTOM_FORM_BASE_URL = "http://localhost:5000/symptom"


def run_daily_reminders():
    """
    Checks for due reminders and fires them.
    Called from /reminders route in app.py.
    """
    print(f"[SCHEDULER] Checking reminders: {datetime.now()}")
    due = get_due_reminders()

    if not due:
        print("[SCHEDULER] No reminders due.")
        return []

    processed = []
    for item in due:
        form_link = (f"{SYMPTOM_FORM_BASE_URL}"
                     f"?patient_id={item['patient_id']}"
                     f"&drug_id={item['drug_id']}")

        print(f"  [REMINDER] {item['full_name']} -> {item['drug_name']}")
        print(f"             Follow-up link: {form_link}")

        # Try real push notification
        try:
            from modules.push_notifications import send_reminder_push
            push_sent = send_reminder_push(
                patient_id=item["patient_id"],
                full_name=item["full_name"],
                drug_name=item["drug_name"],
                drug_id=item["drug_id"]
            )
            if push_sent:
                print(f"  [PUSH] Real notification sent to {item['full_name']}")
            else:
                print(f"  [REMINDER] Push not available — link: {form_link}")
        except Exception as e:
            print(f"  [REMINDER] Push error ({e}) — link: {form_link}")

        mark_reminder_sent(item["drug_id"])
        processed.append(item)

    return processed


if __name__ == "__main__":
    # Run once manually if needed
    print("[Manual] Running reminder check once...")
    run_daily_reminders()