#!/usr/bin/env python3
"""Scraper staleness monitor — emails when a source stops producing.

With ~30 article sources plus a dozen dedicated-table pipelines, an
individual scraper going dark is invisible in the aggregate feed (UDN was
403ing for five weeks before anyone noticed, 2026-06/07). This script
compares each source/table's most recent row against a per-check staleness
threshold and emails on STATE CHANGES only (newly stale, recovered) — not
every run — so a long outage nags once, not daily.

Thresholds are deliberately per-source: LTN posts hourly, TAO holds a
presser fortnightly, TVBS publishes a poll when it feels like it. A
threshold of None disables the check (used for known-dead upstreams, e.g.
UN Comtrade — PRC has published nothing after 2024-12).

    python3 scripts/check_scraper_health.py --no-email   # print table only
    python3 scripts/check_scraper_health.py --force-email

Cron: daily 08:15 from the prod worktree (after the 06:00 pipeline tick).
State lives in /var/log/scraper-health-state.json. SMTP creds come from
.env (same as weekly_digest.py); recipient HEALTH_TO, falling back to
DIGEST_TO.
"""
import argparse
import json
import os
import smtplib
import sqlite3
import sys
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "db", "cross_strait_signal.db")
DEFAULT_ENV = os.path.join(ROOT, ".env")
DEFAULT_STATE = "/var/log/scraper-health-state.json"

# --- Article sources ---------------------------------------------------------
# Max days of silence before a source counts as stale. Keyed on sources.name;
# anything not listed uses ARTICLE_DEFAULT_DAYS. Value None = don't monitor.
ARTICLE_DEFAULT_DAYS = 3
ARTICLE_OVERRIDES = {
    # Official pressers / low-cadence editorial
    "PRC MFA Spokesperson": 10,     # weekday pressers
    "Taiwan Affairs Office": 30,    # ~fortnightly pressers
    "PLA Daily": 45,                # MoD monthly press conference
    "Guancha": 14,                  # section updates in bursts
    "Ming Pao Editorial": 7,        # one print editorial/day, holiday gaps
    # Poll scrapers are event-driven — pollsters publish when they publish.
    "TVBS Poll Center": 90,
    "ETtoday Polls": 90,
    "My-Formosa": 90,
}

# --- Dedicated-table pipelines ----------------------------------------------
# (check_id, sql returning one latest-date scalar, threshold_days, note)
# Dates may be YYYY-MM-DD... timestamps or YYYY-MM periods (compared as the
# 1st of the month, so monthly thresholds must absorb cadence + publish lag).
TABLE_CHECKS = [
    ("social_pulse:weibo",
     "SELECT MAX(scraped_at) FROM social_pulse WHERE platform='weibo'", 2, ""),
    ("social_pulse:ptt",
     "SELECT MAX(scraped_at) FROM social_pulse WHERE platform='ptt'", 2, ""),
    ("pla_incursions:mnd",
     "SELECT MAX(date) FROM pla_incursions WHERE source='mnd'", 5,
     "MND daily briefing"),
    ("coast_guard:gfw_pull",
     "SELECT MAX(substr(pulled_at,1,10)) FROM coast_guard_pulls WHERE status='ok'", 3,
     "GFW presence pull runs every pipeline tick (Step 2n)"),
    ("coast_guard:presence",
     "SELECT MAX(date) FROM coast_guard_presence", 12,
     "GFW data lags ~5 days; 12 = lag + a quiet week"),
    ("econ:MAC_7887",
     "SELECT MAX(period) FROM economic_indicators WHERE source='MAC_7887'", 100,
     "monthly, ~2mo publish lag"),
    ("econ:MAC_7888",
     "SELECT MAX(period) FROM economic_indicators WHERE source='MAC_7888'", 100,
     "monthly, ~2mo publish lag"),
    ("econ:MAC_7459",
     "SELECT MAX(period) FROM economic_indicators WHERE source='MAC_7459'", 210,
     "monthly, slow publisher (~4mo lag observed)"),
    ("econ:HK_CSD",
     "SELECT MAX(period) FROM economic_indicators WHERE source LIKE 'HK_CSD%'", 150,
     "monthly, ~2mo publish lag"),
    # PRC stopped reporting monthly trade to UN Comtrade after 2024-12; the
    # scraper runs clean but gets empty periods. Re-enable if PRC resumes.
    ("econ:UN_COMTRADE",
     "SELECT MAX(period) FROM economic_indicators WHERE source LIKE 'UN_COMTRADE%'", None,
     "DISABLED — upstream dead (PRC stopped reporting, last 2024-12)"),
    ("cifer_snapshots",
     "SELECT MAX(snapshot_date) FROM cifer_snapshots", 45,
     "monthly cron, 1st 03:00"),
    ("invest:prc_to_tw",
     "SELECT MAX(period) FROM investment_by_industry WHERE direction='prc_to_tw'", 150,
     "MAC monthly CSV, ~2-3mo lag"),
    ("invest:tw_to_prc",
     "SELECT MAX(period) FROM investment_by_industry WHERE direction='tw_to_prc'", 150,
     "MAC monthly CSV, ~2-3mo lag"),
    ("alt_model:v4f_sweep",
     "SELECT MAX(created_at) FROM alt_model_analysis "
     "WHERE model='deepseek/deepseek-v4-flash' AND outcome='ok'", 5,
     "daily full-window incremental sweep (04:00); rows only land when new "
     "approvals exist, so the threshold allows a few review-free days"),
]


def parse_when(raw):
    """'2026-07-21 06:04:36' / ISO timestamps / '2026-07' / '2026' → datetime."""
    if not raw:
        return None
    raw = str(raw)
    if len(raw) == 4:
        raw += "-01-01"
    elif len(raw) == 7:
        raw += "-01"
    try:
        return datetime.fromisoformat(raw[:10])
    except ValueError:
        return None


def run_checks(conn, now):
    """Returns list of dicts: {id, last, age_days, limit, status, note}."""
    results = []

    rows = conn.execute(
        """SELECT s.name, MAX(a.scraped_at) AS last
           FROM sources s LEFT JOIN articles a ON a.source_id = s.id
           WHERE s.is_active = 1
           GROUP BY s.id ORDER BY s.name"""
    ).fetchall()
    for r in rows:
        limit = ARTICLE_OVERRIDES.get(r["name"], ARTICLE_DEFAULT_DAYS)
        results.append(assess(f"source:{r['name']}", r["last"], limit, "", now))

    for check_id, sql, limit, note in TABLE_CHECKS:
        last = conn.execute(sql).fetchone()[0]
        results.append(assess(check_id, last, limit, note, now))

    return results


def assess(check_id, last_raw, limit_days, note, now):
    if limit_days is None:
        return {"id": check_id, "last": last_raw, "age_days": None,
                "limit": None, "status": "disabled", "note": note}
    when = parse_when(last_raw)
    age = (now - when).days if when else None
    stale = age is None or age > limit_days
    return {"id": check_id, "last": last_raw or "never", "age_days": age,
            "limit": limit_days, "status": "STALE" if stale else "ok",
            "note": note}


def render(results, transitions):
    lines = []
    if transitions:
        lines.append("State changes since last check:")
        for t in transitions:
            lines.append(f"  {t}")
        lines.append("")
    stale = [r for r in results if r["status"] == "STALE"]
    lines.append(f"{len(stale)} stale / {len(results)} checks")
    lines.append("")
    lines.append(f"{'check':<38} {'status':<9} {'last':<20} {'age':>5}  limit")
    for r in results:
        age = "-" if r["age_days"] is None else f"{r['age_days']}d"
        limit = "-" if r["limit"] is None else f"{r['limit']}d"
        note = f"  ({r['note']})" if r["note"] else ""
        lines.append(f"{r['id']:<38} {r['status']:<9} {str(r['last'])[:19]:<20}"
                     f" {age:>5}  {limit}{note}")
    return "\n".join(lines)


def send_email(subject, body, to):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    pw = os.environ["SMTP_PASS"]
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, pw)
        s.sendmail(user, [to], msg.as_string())


def main():
    ap = argparse.ArgumentParser(description="Scraper staleness monitor.")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--env-file", default=DEFAULT_ENV)
    ap.add_argument("--state-file", default=DEFAULT_STATE)
    ap.add_argument("--to", default=None, help="override HEALTH_TO/DIGEST_TO")
    ap.add_argument("--no-email", action="store_true", help="print only")
    ap.add_argument("--force-email", action="store_true",
                    help="email even without state changes")
    args = ap.parse_args()

    load_dotenv(args.env_file)
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    now = datetime.now()
    results = run_checks(conn, now)
    conn.close()

    try:
        with open(args.state_file) as f:
            prev = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        prev = None

    transitions = []
    if prev is not None:
        for r in results:
            was = prev.get(r["id"])
            if was is not None and was != r["status"] and "disabled" not in (was, r["status"]):
                arrow = "WENT STALE" if r["status"] == "STALE" else "recovered"
                transitions.append(f"{r['id']}: {arrow} (last row {r['last']})")

    body = render(results, transitions)
    print(body)

    with open(args.state_file, "w") as f:
        json.dump({r["id"]: r["status"] for r in results}, f, indent=1)

    first_run = prev is None
    if args.no_email:
        return
    if transitions or first_run or args.force_email:
        stale_n = sum(1 for r in results if r["status"] == "STALE")
        if transitions:
            subject = f"[Cross-Strait Signal] scraper health: {'; '.join(transitions[:3])}"
        elif first_run:
            subject = f"[Cross-Strait Signal] scraper health baseline ({stale_n} stale)"
        else:
            subject = f"[Cross-Strait Signal] scraper health report ({stale_n} stale)"
        to = args.to or os.environ.get("HEALTH_TO") or os.environ["DIGEST_TO"]
        send_email(subject, body, to)
        print(f"\nEmailed {to}")


if __name__ == "__main__":
    main()
