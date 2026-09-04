"""One SMTP sender for the analyst-facing emails (weekly digest, LinkedIn
proposer). Same env contract as before: SMTP_HOST / SMTP_PORT / SMTP_USER /
SMTP_PASS in .env, loaded by the calling script.

Was a private copy inside scripts/weekly_digest.py; lifted here so the
proposer could reuse it instead of a third copy (check_scraper_health.py
and alt_model_monthly_report.py still carry their own plain-text
variants — fold them in when they are next touched).
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email(subject: str, text: str, to: str, html: str | None = None) -> None:
    """Send `text` (and an optional HTML alternative) to `to`. Raises on
    any SMTP failure — callers decide how to log and whether to exit 1."""
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    pw = os.environ["SMTP_PASS"]

    if html is None:
        msg = MIMEText(text, "plain", "utf-8")
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to

    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, pw)
        s.sendmail(user, [to], msg.as_string())
