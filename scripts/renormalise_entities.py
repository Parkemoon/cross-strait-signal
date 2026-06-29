"""
Re-apply entity_canonical.json to existing `entities` rows by EXACT Chinese-name
match, rewriting entity_name_en.

Why this exists: `_normalise_entity_name` in the pipeline only runs at *extraction*
time, so editing entity_canonical.json never touches rows already in the DB. After
adding canonical entries you want the historical rows to match too — this back-fills
them.

EXACT match only — deliberately NOT the pipeline's prefix logic. Prefix matching
(`zh_name.startswith(key)`) corrupts title-prepended rows: e.g. '國防部長顧立雄'
would map to 'Ministry of National Defense (MND)' and a truncated '萬安'
(Mayor Chiang Wan-an) to 'Wan An Exercise'. Exact match sidesteps every such false
positive; the trade-off is it won't fold genuine sub-forms (解放軍海軍 under 解放軍) —
those still rely on the live pipeline at extraction time.

Companion to merge_entities.py: that tool clusters near-duplicate *English* spellings
on approved articles only; this is the canonical-driven counterpart and can target any
scope. Idempotent — re-running after a clean pass reports 0.

Usage:
    python scripts/renormalise_entities.py                       # dry-run, all rows
    python scripts/renormalise_entities.py --scope backlog       # only analyst_approved=0
    python scripts/renormalise_entities.py --type person --apply
    python scripts/renormalise_entities.py --db /path/to/prod.db --scope approved --apply
"""
import sys
import os
import json
import argparse
import sqlite3
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.utils.db import get_connection, DB_PATH

CANON_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'scraper', 'processors', 'entity_canonical.json'
)

# Scope predicates over articles a / ai_analysis ai (LEFT JOINed).
SCOPE_SQL = {
    'all':      "1=1",
    'backlog':  "a.analyst_approved = 0 AND a.is_hidden = 0 AND COALESCE(ai.is_hidden, 0) = 0",
    'approved': "a.analyst_approved = 1 AND a.is_hidden = 0 AND COALESCE(ai.is_hidden, 0) = 0",
}


def _connect(db_path):
    """Mirror get_connection()'s pragmas for an arbitrary DB path (cross-worktree)."""
    if not db_path:
        return get_connection()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def collect_updates(conn, canon, scope, type_filter):
    """Return {entity_id: (new_en, zh, old_en)} for rows whose exact zh name is
    in canon and whose current English spelling differs.

    The article scope is resolved once (article-level, ~12k rows) and entities are
    matched against it in a single scan — `entities.article_id` is unindexed, so a
    per-entity join to ai_analysis would scan the table for every row."""
    sql = f"""
        SELECT e.id, e.entity_name AS zh, e.entity_name_en AS en
        FROM entities e
        WHERE e.article_id IN (
            SELECT a.id
            FROM articles a
            LEFT JOIN ai_analysis ai ON ai.article_id = a.id
            WHERE {SCOPE_SQL[scope]}
        )
          AND e.entity_name IS NOT NULL
    """
    params = []
    if type_filter:
        sql += " AND e.entity_type = ?"
        params.append(type_filter)

    updates = {}
    for r in conn.execute(sql, params):
        zh = r['zh']
        if zh in canon and canon[zh] != (r['en'] or ''):
            updates[r['id']] = (canon[zh], zh, r['en'])
    return updates


def main():
    parser = argparse.ArgumentParser(
        description="Re-apply entity_canonical.json to existing entity rows (exact zh match)")
    parser.add_argument('--scope', choices=list(SCOPE_SQL), default='all',
                        help="Which articles' entities to touch (default: all)")
    parser.add_argument('--type', default=None,
                        help="Limit to one entity_type, e.g. person (default: all types)")
    parser.add_argument('--canon', default=CANON_PATH,
                        help="Path to entity_canonical.json")
    parser.add_argument('--db', default=None,
                        help="Target DB path (default: this worktree's project DB)")
    parser.add_argument('--apply', action='store_true',
                        help="Write changes (default: dry-run)")
    parser.add_argument('--limit', type=int, default=40,
                        help="Max distinct change lines to print (default: 40)")
    args = parser.parse_args()

    with open(args.canon, encoding='utf-8') as f:
        canon = json.load(f)

    conn = _connect(args.db)
    print(f"DB:    {args.db or DB_PATH}")
    print(f"Canon: {len(canon)} entries | scope={args.scope}"
          + (f" | type={args.type}" if args.type else ""))

    updates = collect_updates(conn, canon, args.scope, args.type)
    print(f"{len(updates)} entity rows would change (exact zh match).\n")

    agg = Counter((zh, old, new) for new, zh, old in updates.values())
    for (zh, old, new), n in sorted(agg.items(), key=lambda x: -x[1])[:args.limit]:
        print(f"  {n:>4}  {zh:<12} {(old or '∅')!r:<26} -> {new!r}")
    if len(agg) > args.limit:
        print(f"  ... and {len(agg) - args.limit} more distinct (name, spelling) changes")

    if not args.apply:
        print("\nDRY RUN — pass --apply to write.")
        return
    if not updates:
        print("\nNothing to apply.")
        return

    conn.executemany(
        "UPDATE entities SET entity_name_en = ? WHERE id = ?",
        [(new, eid) for eid, (new, _zh, _old) in updates.items()],
    )
    conn.commit()
    print(f"\nApplied {len(updates)} updates.")


if __name__ == '__main__':
    main()
