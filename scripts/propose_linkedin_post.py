#!/usr/bin/env python3
"""LinkedIn post proposer for Cross-Strait Signal.

Selects ONE cross-strait story — the event cluster with the broadest
coverage on both sides of the strait in the last 48 h — drafts a LinkedIn
post from the stored analysis, and emails the draft to the analyst. It
never posts anything anywhere; the email is the whole output.

Selection: shared/linkedin_selector.py (deterministic, every ranking
factor exposed). Drafting: scraper/processors/linkedin_draft.py (Gemini,
Tier-1 rule blocks, hard-validated format). Dedup/log: the
`linkedin_drafts` table (migration 0011) — nothing in it feeds any
editorial queue.

Usage:
    python3 scripts/propose_linkedin_post.py                    # select, draft, email, log
    python3 scripts/propose_linkedin_post.py --no-email         # print instead of sending (no row)
    python3 scripts/propose_linkedin_post.py --no-record --to me@x  # test send, no row written
    python3 scripts/propose_linkedin_post.py --dry-run-days 14 --out dryrun.md --db /path/prod.db
        # simulate a daily run over the last 14 days (read-only, no email, no DB row)

The DB path defaults to this worktree's db/ (a prod cron hits the prod
DB); --db targets another worktree's DB. --dry-run-days opens it
read-only. --as-of pins "now" (ISO, e.g. 2026-09-02T07:00) for
reproducible runs.

Runs Tuesday and Thursday 07:00 UK time from the prod worktree (see
.claude/rules/deployment.md → Cron schedule). If no cluster qualifies
the script logs one line and sends nothing.
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scraper.utils.mail import send_email  # noqa: E402
from shared.linkedin_selector import (  # noqa: E402
    EXCLUDED_TOPICS, TOP_N, WINDOW_HOURS, fetch_proposed, select_candidates,
)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.join(os.path.dirname(__file__), "..")
DEFAULT_DB = os.path.join(ROOT, "db", "cross_strait_signal.db")
DEFAULT_ENV = os.path.join(ROOT, ".env")
LONDON = ZoneInfo("Europe/London")


def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] linkedin-proposer: {msg}", flush=True)


def window_for(now_utc: datetime, hours: int):
    """(start_iso, end_iso) as naive-UTC 'T' strings, matching published_at."""
    end = now_utc.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0)
    start = end - timedelta(hours=hours)
    return start.isoformat(), end.isoformat()


def open_db(path, read_only=False):
    if read_only:
        conn = sqlite3.connect(f"file:{os.path.abspath(path)}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn
    from scraper.utils.db import get_connection
    return get_connection(path)


# ── rendering ────────────────────────────────────────────────────────────────

def factors_line(c):
    return (f"breadth {c['breadth']} (TW {len(c['tw_outlets'])} outlet(s): {', '.join(c['tw_outlets']) or '-'}; "
            f"PRC {len(c['prc_outlets'])} outlet(s): {', '.join(c['prc_outlets']) or '-'}) · "
            f"divergence {c['divergence']} (TW mean {c['tw_mean']}, PRC mean {c['prc_mean']}) · "
            f"{c['n_articles']} approved articles (TW {c['tw_n']} / PRC {c['prc_n']} / intl {c['intl_n']}"
            + (f"; {c['pending_n']} pending, not used" if c['pending_n'] else "") + ") · "
            f"topic {c['dominant_topic']}")


def side_links(c):
    """First TW and first PRC article URL — the source links for a runner-up line."""
    out = []
    for side in ("TW", "PRC"):
        rows = c['sides'].get(side) or []
        if rows:
            out.append(f"{side}: {rows[0].get('url')}")
    return " · ".join(out)


def public_factors(c):
    """Ranking factors as stored/emailed — the per-article material stripped."""
    keep = ('cluster_id', 'headline', 'rank', 'n_articles', 'tw_n', 'prc_n', 'intl_n',
            'tw_outlets', 'prc_outlets', 'breadth', 'tw_mean', 'prc_mean', 'divergence',
            'dominant_topic', 'topics', 'oldest_published', 'newest_published',
            'pending_n', 'n_members', 'excluded_because')
    return {k: c[k] for k in keep if k in c}


def render_day_md(day_label, start, end, ranked, excluded, draft, err=None):
    md = [f"## {day_label}", "", f"Window: `{start}` → `{end}` (UTC, {WINDOW_HOURS} h)", ""]
    if not ranked:
        md.append("**No cluster qualifies.** Nothing would have been sent.")
    else:
        md.append(f"### Top {len(ranked)} candidates")
        md.append("")
        for c in ranked:
            md.append(f"{c['rank']}. **{c['headline']}** (cluster `{c['cluster_id']}`)")
            md.append(f"   - {factors_line(c)}")
            md.append(f"   - topics: {c['topics']} · {c['oldest_published'][:16]} → {c['newest_published'][:16]}")
            md.append(f"   - links: {side_links(c)}")
        md.append("")
        md.append("### Draft for #1")
        md.append("")
        if err:
            md.append(f"_Draft generation failed: {err}_")
        elif draft:
            md.append(f"_{draft['chars']} chars · {draft['attempts']} attempt(s) · {draft['model']}"
                      + (f" · NEEDS EDIT: {'; '.join(draft['violations'])}" if draft['needs_edit'] else " · passes all rules")
                      + "_")
            md.append("")
            md.append("```text")
            md.append(draft['post'])
            md.append("```")
    md.append("")
    md.append(f"### Excluded ({len(excluded)})")
    md.append("")
    if not excluded:
        md.append("_none_")
    for c in excluded:
        md.append(f"- `{c['cluster_id']}` {c['headline'][:110]} — **{', '.join(c['excluded_because'])}** · "
                  f"TW {len(c['tw_outlets'])} / PRC {len(c['prc_outlets'])} outlets, {c['n_articles']} approved"
                  + (f" + {c['pending_n']} pending" if c['pending_n'] else "") + ", "
                  f"topic {c['dominant_topic']}")
    md.append("")
    return "\n".join(md)


# ── modes ────────────────────────────────────────────────────────────────────

def run_dry_run(conn, days, out_path, hours, top_n, as_of=None, no_draft=False):
    """Simulate the proposer running daily at 07:00 London for the last
    `days` days. The already-proposed set accumulates across simulated
    days exactly as the linkedin_drafts table would. Read-only; no email."""
    from scraper.processors.linkedin_draft import generate_draft

    now_london = (as_of or datetime.now(timezone.utc)).astimezone(LONDON)
    proposed = {'cluster_ids': set(), 'article_ids': set()}
    sections = []
    summary = []
    for i in range(days - 1, -1, -1):
        day = (now_london - timedelta(days=i)).replace(hour=7, minute=0, second=0, microsecond=0)
        if day > now_london:
            day = now_london
        start, end = window_for(day, hours)
        ranked, excluded = select_candidates(conn, start, end, proposed, top_n)
        draft, err = None, None
        if ranked:
            top = ranked[0]
            if not no_draft:
                try:
                    draft = generate_draft(top)
                except Exception as e:  # keep the simulation going
                    err = f"{type(e).__name__}: {e}"
            proposed['cluster_ids'].add(top['cluster_id'])
            proposed['article_ids'].update(top['article_ids'])
        label = day.strftime("%Y-%m-%d (%a) 07:00 %Z")
        sections.append(render_day_md(label, start, end, ranked, excluded, draft, err))
        summary.append((label, ranked[0]['headline'] if ranked else None,
                        ranked[0]['breadth'] if ranked else None, len(excluded),
                        (draft or {}).get('needs_edit'), err))
        log(f"{label}: {len(ranked)} candidate(s), {len(excluded)} excluded"
            + (f", draft {draft['chars']} chars" if draft else "") + (f", ERROR {err}" if err else ""))

    head = [
        "# LinkedIn proposer — dry run",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · simulated daily at 07:00 Europe/London · "
        f"window {hours} h · top {top_n} · excluded topics: {', '.join(sorted(EXCLUDED_TOPICS))}",
        "",
        "Caveat: cluster ids and approval flags are read as they are NOW, not as they were on each simulated day "
        "(cluster_events.py regenerates ids every tick and approvals happen in batches), so a day's candidate set is a reconstruction.",
        "",
        "| Simulated run | Proposed | Breadth | Excluded | Draft |",
        "|---|---|---|---|---|",
    ]
    for label, headline, breadth, n_ex, needs_edit, err in summary:
        status = "error" if err else ("needs edit" if needs_edit else ("ok" if headline else "nothing sent"))
        head.append(f"| {label} | {(headline or '—')[:80]} | {breadth if breadth is not None else '—'} | {n_ex} | {status} |")
    head.append("")
    text = "\n".join(head) + "\n" + "\n".join(sections)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    log(f"wrote {out_path}")


def render_email(ranked, excluded, draft, start, end):
    """Plain text: the draft first (copy-ready), then the two runner-ups as
    one line each with source links, then the ranking factors."""
    top = ranked[0]
    out = []
    if draft['needs_edit']:
        out.append("NEEDS EDIT before posting: " + "; ".join(draft['violations']))
        out.append("")
    out.append("DRAFT (copy from the next line to the link):")
    out.append("-" * 60)
    out.append(draft['post'])
    out.append("-" * 60)
    out.append(f"{draft['chars']} characters · {draft['attempts']} attempt(s) · {draft['model']}")
    out.append("")
    out.append("Sources behind the draft:")
    for side in ("TW", "PRC"):
        for r in top['sides'].get(side, [])[:4]:
            out.append(f"  [{side}] {r['outlet']}: {r['title_en']} — {r['url']}")
    out.append("")
    out.append("Runner-ups:")
    if len(ranked) < 2:
        out.append("  (none — only one cluster qualified)")
    for c in ranked[1:]:
        out.append(f"  {c['rank']}. {c['headline']} · breadth {c['breadth']} · {side_links(c)}")
    out.append("")
    out.append("Ranking factors:")
    for c in ranked:
        out.append(f"  #{c['rank']} [{c['cluster_id']}] {factors_line(c)}")
    out.append("")
    ex_counts = {}
    for c in excluded:
        for reason in c['excluded_because']:
            key = reason.split(':')[0]
            ex_counts[key] = ex_counts.get(key, 0) + 1
    out.append(f"Window {start} → {end} UTC · {len(excluded)} cluster(s) excluded: "
               + ", ".join(f"{k} {v}" for k, v in sorted(ex_counts.items())))
    out.append("")
    out.append("This is a proposal only. Nothing has been posted anywhere.")
    return "\n".join(out)


def run_live(conn, hours, top_n, as_of, to, no_email, no_record):
    """Select → draft → email → record. Sends nothing when nothing
    qualifies. The linkedin_drafts row is written only AFTER a successful
    send, so a failed send leaves the story proposable next run instead of
    a row claiming it went out. --no-email never records."""
    from scraper.processors.linkedin_draft import generate_draft

    now = as_of or datetime.now(timezone.utc)
    start, end = window_for(now, hours)
    proposed = fetch_proposed(conn)
    ranked, excluded = select_candidates(conn, start, end, proposed, top_n)
    log(f"window {start} → {end}: {len(ranked)} candidate(s), {len(excluded)} excluded, "
        f"{len(proposed['cluster_ids'])} previously proposed")
    if not ranked:
        log("no cluster qualifies — nothing sent")
        return 0

    top = ranked[0]
    draft = generate_draft(top)
    log(f"drafted [{top['cluster_id']}] {top['headline'][:80]} — {draft['chars']} chars, "
        f"{draft['attempts']} attempt(s)"
        + (f", NEEDS EDIT: {'; '.join(draft['violations'])}" if draft['needs_edit'] else ""))

    subject = f"LinkedIn draft: {top['headline'][:90]}"
    body = render_email(ranked, excluded, draft, start, end)

    if no_email:
        print(f"Subject: {subject}\n\n{body}")
        return 0

    to = to or os.environ.get("LINKEDIN_TO") or os.environ.get("DIGEST_TO")
    if not to:
        log("no recipient: set LINKEDIN_TO or DIGEST_TO in the env file, or pass --to")
        return 2
    try:
        send_email(subject, body, to)
    except Exception as e:
        log(f"send FAILED: {type(e).__name__}: {e} — story left proposable")
        return 1
    log(f"sent to {to}")

    if no_record:
        log("--no-record: linkedin_drafts row not written")
        return 0
    factors = {
        'winner': public_factors(top),
        'runner_ups': [public_factors(c) for c in ranked[1:]],
        'excluded': [public_factors(c) for c in excluded],
        'draft': {k: draft[k] for k in ('violations', 'needs_edit', 'attempts', 'model', 'chars')},
        'window': {'start': start, 'end': end, 'hours': hours},
    }
    conn.execute(
        "INSERT INTO linkedin_drafts (cluster_id, article_ids, draft, ranking_factors, emailed_at, emailed_to) "
        "VALUES (?,?,?,?,?,?)",
        (top['cluster_id'], json.dumps(top['article_ids']), draft['post'],
         json.dumps(factors, ensure_ascii=False),
         datetime.now(timezone.utc).replace(microsecond=0).isoformat(), to),
    )
    conn.commit()
    log(f"recorded linkedin_drafts row for cluster {top['cluster_id']}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Propose one LinkedIn post from the dashboard DB (never posts).")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--env-file", default=DEFAULT_ENV)
    ap.add_argument("--hours", type=int, default=WINDOW_HOURS)
    ap.add_argument("--top", type=int, default=TOP_N)
    ap.add_argument("--as-of", default=None, help="pin 'now' (ISO, UTC unless offset given)")
    ap.add_argument("--dry-run-days", type=int, default=0,
                    help="simulate N daily runs into --out (read-only, no email, no DB row)")
    ap.add_argument("--out", default=None, help="markdown output path for --dry-run-days")
    ap.add_argument("--no-draft", action="store_true", help="dry run: selection only, skip Gemini")
    ap.add_argument("--to", default=None, help="override DIGEST_TO recipient")
    ap.add_argument("--no-email", action="store_true", help="print the email instead of sending")
    ap.add_argument("--no-record", action="store_true",
                    help="don't write the linkedin_drafts row (test sends; the story stays proposable)")
    args = ap.parse_args()

    load_dotenv(args.env_file)
    as_of = None
    if args.as_of:
        as_of = datetime.fromisoformat(args.as_of)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)

    if args.dry_run_days:
        if not args.out:
            sys.exit("--dry-run-days needs --out")
        conn = open_db(args.db, read_only=True)
        try:
            run_dry_run(conn, args.dry_run_days, args.out, args.hours, args.top, as_of, args.no_draft)
        finally:
            conn.close()
        return

    conn = open_db(args.db)
    try:
        rc = run_live(conn, args.hours, args.top, as_of, args.to, args.no_email, args.no_record)
    finally:
        conn.close()
    sys.exit(rc)


if __name__ == "__main__":
    main()
