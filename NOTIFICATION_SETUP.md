# Background phone notifications

This project now sends Web Push notifications through the device's browser service worker. These can appear while the PVPro tab is closed.

## Deploy on Render

1. Run `pip install -r requirements.txt`, then run `python scripts/generate_vapid_keys.py` once on your computer. Keep the two values private.
2. In Render, set `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` on both the web service and the `pharmvigilance-reminders` cron service.
3. Set the same PostgreSQL `DATABASE_URL` on both services. Do not use SQLite in production: a Render cron service cannot share a web service's local SQLite file.
4. Sync the updated `render.yaml` as a Render Blueprint. It runs the reminder job every day at 09:00 UTC (14:30 India time). Change `schedule` if you want another reminder time.
5. Open PVPro over HTTPS on the phone, sign in, press **Enable phone notifications**, and allow browser notifications. On iPhone, first add PVPro to the Home Screen, then enable notifications from the installed app.

## Test

After enabling notifications, open `/push/test` while signed in. The response should show `"sent": true`, and a device notification should appear even after closing the PVPro tab.

The browser/device notification permission and battery-saver settings still control whether the operating system displays notifications.
