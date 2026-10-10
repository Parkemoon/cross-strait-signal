"""Bin exercise and poll candidates that could never be approved — rules and
their measured cost in shared/queue_rules.py. A binned row is dismissed with
reviewed_by = 'rule:<name>', so it can be listed or put back.

Two callers:
  - CLI (dry-run default):
        python scripts/bin_queue_candidates.py               # what would be binned
        python scripts/bin_queue_candidates.py --apply
        python scripts/bin_queue_candidates.py --revert no-location   # or --revert all
        python scripts/bin_queue_candidates.py --db /var/www/cross-strait-signal/db/cross_strait_signal.db --apply
  - run_pipeline.py (Step 3g) calls bin_new_candidates() every tick, after
    the side-extractions, so a binned row never reaches the analyst queue.

Idempotent: binned rows leave the pending pool."""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.queue_rules import RULES, bin_candidates, revert_bins
from scraper.utils.db import get_connection

LABEL_SQL = {
    'military_exercises': "SELECT COALESCE(name_en, name_zh, name_raw), start_date, location_label"
                          " FROM military_exercises WHERE id = ?",
    'polls': "SELECT s.slug, p.fielded_start, p.sample_size FROM polls p"
             " JOIN pollsters s ON s.id = p.pollster_id WHERE p.id = ?",
}


def bin_new_candidates():
    """Pipeline entry point (Step 3g). Returns the number of rows binned."""
    conn = get_connection()
    try:
        results = bin_candidates(conn, apply=True)
    finally:
        conn.close()
    for table, rule, ids in results:
        if ids:
            print(f"  {table}: {len(ids)} binned ({rule})")
    return sum(len(ids) for _, _, ids in results)


def main():
    ap = argparse.ArgumentParser(
        description="Bin exercise/poll candidates that fail the queue rules (dry-run by default).")
    ap.add_argument('--db', help="DB path (default: this worktree's DB)")
    ap.add_argument('--apply', action='store_true', help='dismiss the matches (dry-run without)')
    ap.add_argument('--revert', metavar='RULE',
                    help="put rule-binned rows back in the queue: a rule name or 'all'")
    ap.add_argument('--show', type=int, default=5, help='example rows to print per rule (default 5)')
    args = ap.parse_args()

    conn = get_connection(args.db)
    try:
        if args.revert:
            names = {name for rules in RULES.values() for name, _ in rules}
            if args.revert != 'all' and args.revert not in names:
                ap.error(f"unknown rule {args.revert!r}; one of: all, {', '.join(sorted(names))}")
            restored = revert_bins(conn, None if args.revert == 'all' else args.revert)
            print(f"restored {restored} row(s) to pending")
            return
        for table, rule, ids in bin_candidates(conn, apply=args.apply):
            verb = 'binned' if args.apply else 'would bin'
            print(f"{table:20s} {rule:18s} {verb} {len(ids)}")
            for i in ids[:args.show]:
                print(f"    #{i} {tuple(conn.execute(LABEL_SQL[table], (i,)).fetchone())}")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
