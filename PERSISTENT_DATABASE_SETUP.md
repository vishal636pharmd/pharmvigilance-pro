# Required: persistent database setup for Render

Render local files are temporary. Do not rely on the `database/pvpro.db` SQLite file in a deployed service. A restart or deploy can erase local SQLite data, which causes lost medicines and makes an existing login look like a new user.

1. In the Render Dashboard, select **New** > **Postgres** and create a PostgreSQL database in the same region as the web service.
2. When the database is ready, open it and copy its **Internal Database URL**.
3. Open the `pharmvigilance-pro` web service, select **Environment**, and add `DATABASE_URL` with that internal URL as its value. Save the change and redeploy.
4. If you create the `pharmvigilance-reminders` cron job, add the exact same `DATABASE_URL` there too.

After the first deploy with `DATABASE_URL`, create a new test account and upload a test medicine. Existing SQLite records are not automatically moved to PostgreSQL.

Verify it: restart/redeploy the web service, sign in again in the same browser, and confirm the test medicine still appears. Do not test in InPrivate/Incognito mode and do not clear site data.
