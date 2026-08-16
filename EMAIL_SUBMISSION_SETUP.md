# PvPI email submission setup

This feature sends a generated PDF and E2B XML report **for PvPI review**. It does not confirm VigiFlow submission or regulatory acceptance.

In your Render web service, set:

- `SMTP_FROM_EMAIL`: the sending Gmail address
- `SMTP_APP_PASSWORD`: a Google App Password for that Gmail account (not the normal Gmail password)
- `PVPI_RECIPIENT_EMAIL`: `pvpi@ipcindia.net`, unless PvPI or your AMC provides a different reporting address
- `SUBMISSION_COPY_TO`: your records email address; normally the same as `SMTP_FROM_EMAIL`

For Gmail, enable two-step verification, create a new App Password, and use it only in Render's secret environment-variable settings. Do not put it in source code or GitHub.

After deployment, submit one test report and check the Render log. A successful delivery log says `Sent for PvPI review`; it does not mean the report was accepted by PvPI.
