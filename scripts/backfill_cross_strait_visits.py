"""Backfill `cross_strait_visits` from already-analysed articles.

Historical DIP_VISIT / PARTY_VISIT articles were analysed before the visits
pass (pipeline Step 3e) existed, so the live pass never saw them. This runs
the SAME extractor + insert helper (`scraper/processors/visits_extract.py`)
over the backlog, so the scope gate and validation are identical to the
live path. Idempotent via `cross_strait_visit_scans` (an article is only
ever scanned once, zero-yield included); safe to re-run or interrupt.

Rows land `pending` for the analyst queue. Many articles cover one trip, so
expect several rows per visit — the queue's merge picker collapses them.

Examples:
  python scripts/backfill_cross_strait_visits.py --days 180 --limit 50 --dry-run
  python scripts/backfill_cross_strait_visits.py --days 400 --limit 2000 \
      --db /var/www/cross-strait-signal/db/cross_strait_signal.db

Launch big runs detached (setsid nohup …): ~1,100 articles on prod ≈ 1h.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from scraper.processors.visits_extract import process_visit_articles  # noqa: E402


def _connect(db_path):
    if not db_path:
        from scraper.utils.db import get_connection
        return get_connection()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--db", help="target another worktree's DB (e.g. prod)")
    ap.add_argument("--dry-run", action="store_true", help="extract + validate, write nothing")
    args = ap.parse_args()

    conn = _connect(args.db)
    try:
        scanned, inserted = process_visit_articles(conn, days=args.days, limit=args.limit, dry_run=args.dry_run)
        verb = "would insert" if args.dry_run else "inserted"
        print(f"done: {scanned} articles scanned, {verb} {inserted} pending visits")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
