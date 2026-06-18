"""
Backfill diplomacy_statements for already-analysed articles.

Historical articles were processed by Tier 1 before the Diplomacy Tracker
existed, so the main side-extract never ran on them. This script runs the
stripped diplomacy-only prompt (`_extract_diplomacy_only`) over a window of
already-analysed articles whose topic suggests a third-country angle, and
inserts pending candidates via the shared `_insert_diplomacy_row` helper —
identical validation to the live pipeline.

Idempotent: skips any article that already has a diplomacy_statements row.
Safe to re-run; cap with --limit and widen with --days.

By default only articles in the diplomacy-relevant topic allowlist are
scanned (cost control — the forward pipeline pass covers ALL topics going
forward). Use --all-topics to scan every analysed article in the window.

Usage:
    python scripts/backfill_diplomacy_statements.py --days 90 --limit 300
    python scripts/backfill_diplomacy_statements.py --dry-run --days 30
    python scripts/backfill_diplomacy_statements.py --db /path/to/prod.db --days 90
"""
import sys
import os
import argparse
import sqlite3
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.processors.ai_pipeline import _extract_diplomacy_only, _insert_diplomacy_row
from scraper.utils.db import get_connection, DB_PATH

# Topics where a third-country stance on Taiwan / cross-strait most often
# appears. The forward pipeline pass runs on every topic; this allowlist
# just bounds backfill API cost. Widen with --topics or --all-topics.
DEFAULT_TOPICS = [
    'DIP_STATEMENT', 'DIP_VISIT', 'DIP_SANCTIONS',
    'US_TAIWAN', 'US_PRC', 'INT_ORG', 'PARTY_VISIT', 'ARMS_SALES',
]


def _connect(db_path):
    if not db_path:
        return get_connection()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def main():
    parser = argparse.ArgumentParser(description="Backfill diplomacy_statements")
    parser.add_argument('--days', type=int, default=90, help="Look-back window in days (default: 90)")
    parser.add_argument('--limit', type=int, default=300, help="Max articles to process (default: 300)")
    parser.add_argument('--topics', type=str, default=None,
                        help="Comma-separated topic_primary allowlist (default: diplomacy-relevant set)")
    parser.add_argument('--all-topics', action='store_true',
                        help="Scan every analysed article in the window, ignoring the topic allowlist")
    parser.add_argument('--db', type=str, default=None,
                        help="Target DB path (default: the canonical worktree DB)")
    parser.add_argument('--dry-run', action='store_true',
                        help="Extract and report, but do not write any rows")
    args = parser.parse_args()

    conn = _connect(args.db)
    print(f"DB: {args.db or DB_PATH}")

    topic_clause = ""
    params = [f'-{args.days} days']
    if not args.all_topics:
        topics = ([t.strip() for t in args.topics.split(',') if t.strip()]
                  if args.topics else DEFAULT_TOPICS)
        placeholders = ','.join('?' * len(topics))
        topic_clause = f"AND ai.topic_primary IN ({placeholders})"
        params.extend(topics)
        print(f"Topic allowlist: {', '.join(topics)}")
    else:
        print("Topic allowlist: (all topics)")
    params.append(args.limit)

    articles = conn.execute(f"""
        SELECT a.id, a.title_original, a.content_original, a.language,
               a.published_at, s.name AS source_name, s.place AS source_place
        FROM articles a
        JOIN ai_analysis ai ON ai.article_id = a.id
        JOIN sources s ON s.id = a.source_id
        WHERE a.ai_processed = 1
          AND a.published_at >= datetime('now', ?)
          {topic_clause}
          AND NOT EXISTS (
              SELECT 1 FROM diplomacy_statements d WHERE d.article_id = a.id
          )
        ORDER BY a.published_at DESC
        LIMIT ?
    """, params).fetchall()

    print(f"Found {len(articles)} eligible articles (last {args.days} days, limit {args.limit})\n")

    total_inserted = 0
    articles_with_rows = 0
    total_errors = 0

    for i, article in enumerate(articles, 1):
        try:
            statements = _extract_diplomacy_only(article)
        except Exception as e:
            print(f"  [{i}/{len(articles)}] article {article['id']}: extract failed — {e}")
            total_errors += 1
            continue

        if not statements:
            continue

        if args.dry_run:
            for st in statements:
                print(f"  [{i}/{len(articles)}] art {article['id']}: "
                      f"{st.get('country')} ({st.get('country_iso')}) "
                      f"{st.get('authority_tier')} stance={st.get('stance')} "
                      f"— {(st.get('statement_en') or '')[:80]}")
            total_inserted += len(statements)
            articles_with_rows += 1
            continue

        inserted = 0
        for st in statements:
            try:
                if _insert_diplomacy_row(conn, article['id'], st,
                                         source_place=article['source_place']):
                    inserted += 1
            except Exception as e:
                print(f"  [{i}/{len(articles)}] article {article['id']}: insert failed — {e}")
                total_errors += 1
        if inserted:
            try:
                conn.commit()
            except Exception as e:
                print(f"  [{i}/{len(articles)}] commit failed: {e}")
                conn.rollback()
                continue
            articles_with_rows += 1
            total_inserted += inserted
            print(f"  [{i}/{len(articles)}] article {article['id']}: +{inserted} statement(s)")

    verb = "would insert" if args.dry_run else "inserted"
    print(f"\nDone. {verb} {total_inserted} statement(s) across "
          f"{articles_with_rows} article(s). Errors: {total_errors}.")
    conn.close()


if __name__ == '__main__':
    main()
