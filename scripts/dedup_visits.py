"""Pre-queue dedup sweep for cross_strait_visits — clustering/keeper logic
in shared/visit_dedup.py (same visitor + direction, effective dates chained
<=21 days; approved rows anchor, pending duplicates are marked
approval_status='merged' into the keeper, exactly what the queue's manual
merge writes).

Two callers:
  - CLI (dry-run default; --apply writes + drops a revert manifest):
        python scripts/dedup_visits.py                    # dry-run, full history
        python scripts/dedup_visits.py --apply
        python scripts/dedup_visits.py --db /var/www/cross-strait-signal/db/cross_strait_signal.db --apply
  - run_pipeline.py (after Step 3e) calls dedup_recent_visits() every tick
    over the last 60 days, so a fresh extraction lands on an existing
    trip's keeper before the analyst ever sees it.

Idempotent: merged rows leave the pending pool, and the keeper choice is
deterministic (ties break on lowest id)."""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.visit_dedup import GAP_DAYS, dedup_visits
from scraper.utils.db import DB_PATH, get_connection


def dedup_recent_visits(days=60, apply=True):
    """Pipeline entry point (Step 3e follow-up)."""
    conn = get_connection()
    try:
        return dedup_visits(conn, days=days, apply=apply)
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(
        description="Collapse per-article duplicate visit rows into one keeper per trip (dry-run by default).")
    ap.add_argument('--db', help='DB path (default: this worktree\'s DB)')
    ap.add_argument('--days', type=int, default=None,
                    help='only cluster rows with an effective date in the last N days (default: full history)')
    ap.add_argument('--gap', type=int, default=GAP_DAYS,
                    help=f'max day-gap that chains two rows into one trip (default {GAP_DAYS})')
    ap.add_argument('--apply', action='store_true', help='write the merges (dry-run without)')
    args = ap.parse_args()

    conn = get_connection(args.db)
    try:
        before = conn.execute(
            "SELECT COUNT(*) FROM cross_strait_visits WHERE approval_status='pending'").fetchone()[0]
        plans, merged = dedup_visits(conn, days=args.days, gap_days=args.gap, apply=args.apply)
        after = conn.execute(
            "SELECT COUNT(*) FROM cross_strait_visits WHERE approval_status='pending'").fetchone()[0]
        print(f"pending queue: {before} -> {after}" if args.apply
              else f"pending queue: {before} (would become {before - merged})")
        if args.apply and merged:
            ts = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
            # Tag by the DB actually written — the default DB is the worktree's
            # own, so a run from the prod checkout without --db is a prod run.
            db_path = os.path.realpath(args.db or DB_PATH)
            name = 'prod' if '/cross-strait-signal/' in db_path else 'staging'
            path = f"dedup-visits-{name}-{ts}.manifest"
            ids = [str(r[0]) for r in conn.execute(
                "SELECT id FROM cross_strait_visits WHERE approval_status='merged' AND reviewed_by='dedup:visits'")]
            with open(path, 'w', encoding='utf-8') as f:
                f.write("-- revert: every row this tool has EVER merged (reviewed_by='dedup:visits')\n")
                f.write("UPDATE cross_strait_visits SET approval_status='pending', merged_into_id=NULL, "
                        "reviewed_at=NULL, reviewed_by=NULL WHERE reviewed_by='dedup:visits' "
                        f"AND id IN ({','.join(ids)});\n")
            print(f"revert manifest: {path}")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
