"""
Backfill key_figure_statements for existing processed articles.

Only processes articles where a key figure was already detected as an entity,
so the set is much smaller than a full re-run. Safe to re-run: skips articles
that already have rows in key_figure_statements.

Usage:
    python scripts/backfill_key_figure_statements.py --days 30 --limit 200
"""
import sys
import os
import argparse
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.processors.ai_pipeline import analyse_article, _ALIAS_TO_FIGURE_ID
from scraper.utils.db import get_connection


def main():
    parser = argparse.ArgumentParser(description="Backfill key_figure_statements")
    parser.add_argument('--days', type=int, default=30, help="Look-back window in days (default: 30)")
    parser.add_argument('--limit', type=int, default=200, help="Max articles to process (default: 200)")
    args = parser.parse_args()

    if not _ALIAS_TO_FIGURE_ID:
        print("No key figures loaded — check scraper/processors/key_figures.json.")
        return

    conn = get_connection()

    # Build lowercase alias set for SQL matching
    all_aliases = list(_ALIAS_TO_FIGURE_ID.keys())
    placeholders = ','.join('?' * len(all_aliases))

    # Find processed articles where a key figure entity was detected,
    # that don't yet have any rows in key_figure_statements
    articles = conn.execute(f"""
        SELECT DISTINCT a.id, a.title_original, a.content_original,
               a.language, s.name AS source_name
        FROM articles a
        JOIN entities e ON e.article_id = a.id
        JOIN sources s ON s.id = a.source_id
        WHERE a.ai_processed = 1
          AND a.published_at >= datetime('now', ?)
          AND (LOWER(e.entity_name) IN ({placeholders})
               OR LOWER(e.entity_name_en) IN ({placeholders}))
          AND a.id NOT IN (SELECT DISTINCT article_id FROM key_figure_statements)
        ORDER BY a.published_at DESC
        LIMIT ?
    """, [f'-{args.days} days', *all_aliases, *all_aliases, args.limit]).fetchall()

    print(f"Found {len(articles)} eligible articles (last {args.days} days, limit {args.limit})\n")

    total_inserted = 0
    total_errors = 0

    for i, article in enumerate(articles, 1):
        title = article['title_original']
        print(f"[{i}/{len(articles)}] {title[:70]}...")

        try:
            analysis = analyse_article(
                title=title,
                content=article['content_original'],
                language=article['language'],
                source_name=article['source_name']
            )

            statements = analysis.get('key_figure_statements', [])
            inserted = 0

            for stmt in statements:
                speaker = stmt.get('speaker', '').strip()
                figure_id = _ALIAS_TO_FIGURE_ID.get(speaker.lower())
                text = stmt.get('statement_text', '').strip()
                if not figure_id or not text:
                    continue
                # Drop if model returned Chinese instead of translating
                cjk_ratio = sum(1 for c in text if '\u4e00' <= c <= '\u9fff') / len(text)
                if cjk_ratio > 0.15:
                    continue
                conn.execute("""
                    INSERT INTO key_figure_statements
                    (article_id, figure_id, speaker_raw, statement_text, statement_zh,
                     statement_kind, confidence, approval_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
                """, (
                    article['id'],
                    figure_id,
                    speaker,
                    text,
                    stmt.get('statement_zh'),
                    stmt.get('statement_kind', 'quote'),
                    stmt.get('confidence', 0.8)
                ))
                inserted += 1

            conn.commit()
            total_inserted += inserted

            if inserted:
                print(f"  → {inserted} statement(s) inserted as pending")
            else:
                print(f"  → no attributable statements found")

            time.sleep(0.5)

        except Exception as e:
            total_errors += 1
            print(f"  → ERROR: {e}")

    conn.close()
    print(f"\nDone. {total_inserted} statements inserted, {total_errors} errors.")
    print("Run the pipeline or visit the dashboard to approve candidates.")


if __name__ == '__main__':
    main()
