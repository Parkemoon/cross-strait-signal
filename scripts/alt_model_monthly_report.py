"""Monthly alt-model drift report — emails the live aggregates next to the
frozen write-up numbers so the Alt Models tab's findings text gets a regular
2-minute human review.

Runs scripts/alt_model_aggregates.py against the DB, prepends the frozen
2026-08 reference table from ALT_MODEL_EXPERIMENT_WRITEUP.md §3-4, and emails
the result via the same SMTP setup as weekly_digest.py. The review act: if the
live numbers have moved materially from the frozen ones, update the findings
block in frontend/src/components/AltModelsTab.jsx (and the write-up); if not,
delete the email.

Monthly via cron (1st 08:30) from the prod worktree. Flags: --db, --env-file,
--to (default DIGEST_TO), --no-email (print only).
"""
import argparse
import os
import smtplib
import subprocess
import sys
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent.parent

# Frozen reference — ALT_MODEL_EXPERIMENT_WRITEUP.md §3-4 + §5.6 (refreshed 2026-08-28).
# Update this block whenever the write-up's headline table is revised, so the
# email always compares live vs last-reviewed, not live vs forever-2026-08.
FROZEN_REFERENCE = """\
=== Frozen reference (write-up, refreshed 2026-08-28; V4F n=15,418) ===
  V4F topic agreement overall:            40.3%   (conditional on relevant: 58.8%)
  V4F NOT_RELEVANT rate:                  31.5%   (sovereignty 6.1% vs other 36.7% — anti-selective)
  V4F |dScore| (relevant rows):           0.142   signed bias +0.040
  V4F urgency match:                      75.2%   esc flags 389 vs prod 240
  Gemini-control agreement (ceiling):     71.4%   (conditional: 78.5%)
  Refusals, all models:                   0
  Completeness (audit_summary_completeness.py, not in the live block below):
    V4F alt-only omission 5.7% (control 4.8%); sensitive slice 2.9% (control 8.8%, 8/91)
    V4F extraction recall 75.8% (control 86.7%)
Review trigger: conditional agreement, NR ratio or signed bias moving
materially from these -> update AltModelsTab.jsx findings + the write-up.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(REPO / "db" / "cross_strait_signal.db"))
    ap.add_argument("--env-file", default=str(REPO / ".env"))
    ap.add_argument("--to", default=None, help="override DIGEST_TO recipient")
    ap.add_argument("--no-email", action="store_true", help="print only, don't send")
    args = ap.parse_args()

    load_dotenv(args.env_file)

    agg = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "alt_model_aggregates.py"), "--db", args.db],
        capture_output=True, text=True,
    )
    if agg.returncode != 0:
        print(agg.stdout)
        print(agg.stderr, file=sys.stderr)
        sys.exit(f"alt_model_aggregates.py failed ({agg.returncode})")

    body = FROZEN_REFERENCE + "\n=== Live aggregates ===\n" + agg.stdout

    if args.no_email:
        print(body)
        return

    to = args.to or os.environ.get("DIGEST_TO")
    if not to:
        print(body)
        sys.exit("No recipient: set DIGEST_TO in .env or pass --to")

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    pw = os.environ["SMTP_PASS"]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "Alt-model monthly review — live aggregates vs frozen write-up"
    msg["From"] = user
    msg["To"] = to

    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, pw)
        s.sendmail(user, [to], msg.as_string())
    print(f"Sent to {to} ({len(body)} chars)")


if __name__ == "__main__":
    main()
