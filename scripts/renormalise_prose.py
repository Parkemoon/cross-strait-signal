#!/usr/bin/env python3
"""Prose history pass: bring the English text of already-analysed articles into
line with the name registry.

The write path (`shared.name_registry.apply_to_analysis`) rewrites the model's
own rendering of a person's name in title / summary / key quote / reasoning as
each new article is analysed. Articles analysed before a name was settled keep
the old rendering in the prose while the entity chip already shows the settled
form. This script recovers those renderings from the text itself
(`shared/prose_names.py`: a capitalised span counts only when it reads exactly
as the person's characters in pinyin or Wade-Giles) and rewrites them with the
same whole-word helper the pipeline uses.

    python scripts/renormalise_prose.py [--db PATH] [--days N] [--limit N] [--show 40]   # dry run
    python scripts/renormalise_prose.py --apply [--statements]                            # writes + manifest

Fields: articles.title_en, ai_analysis.summary_en / key_quote_en /
sentiment_reasoning. A field whose analyst override is set is skipped (the
override is what the site shows; the model's text under it is left as
evidence). key_figure_statements.statement_text only with --statements (those
rows are hand-approved). Idempotent; revert manifest
`prose-names-<db>-<ts>.manifest` (JSONL: table, id, field, old, new).
"""
import argparse
import datetime
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.utils.db import get_connection  # noqa: E402
from shared.name_registry import rewrite_renderings, to_trad  # noqa: E402
from shared.prose_names import find_pairs  # noqa: E402

FIELDS = (  # (table, column, override column on articles or None)
    ('articles', 'title_en', 'title_en_override'),
    ('ai_analysis', 'summary_en', 'summary_en_override'),
    ('ai_analysis', 'key_quote_en', 'key_quote_override'),
    ('ai_analysis', 'sentiment_reasoning', None),
)


def persons_by_article(conn, ids):
    """{article_id: [(zh_trad, en_now), …]} — one form per Chinese name (the most frequent)."""
    out = defaultdict(Counter)
    q = "SELECT article_id, entity_name, entity_name_en FROM entities WHERE entity_type = 'person' AND entity_name_en IS NOT NULL"
    for aid, zh, en in conn.execute(q):
        if aid in ids and zh and en:
            out[aid][(to_trad(zh), en.strip())] += 1
    result = {}
    for aid, cnt in out.items():
        best = {}
        for (zh, en), n in cnt.most_common():
            best.setdefault(zh, en)
        result[aid] = list(best.items())
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db')
    ap.add_argument('--days', type=int, help='only articles published in the last N days')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--show', type=int, default=40, help='sample changes to print')
    ap.add_argument('--statements', action='store_true', help='also rewrite key_figure_statements.statement_text')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    conn = get_connection(args.db)

    sql = """SELECT a.id, a.title_en, a.title_en_override, a.summary_en_override, a.key_quote_override,
                    ai.id AS ai_id, ai.summary_en, ai.key_quote_en, ai.sentiment_reasoning
             FROM articles a JOIN ai_analysis ai ON ai.article_id = a.id"""
    params = []
    if args.days:
        sql += " WHERE a.published_at >= datetime('now', ?)"
        params.append(f'-{args.days} days')
    sql += " ORDER BY a.id DESC"
    if args.limit:
        sql += " LIMIT ?"
        params.append(args.limit)
    rows = conn.execute(sql, params).fetchall()
    persons = persons_by_article(conn, {r['id'] for r in rows})

    changes = []          # (table, row_id, field, old, new)
    pair_tally = Counter()
    for r in rows:
        ps = persons.get(r['id'])
        if not ps:
            continue
        for table, col, ovr in FIELDS:
            if ovr and r[ovr]:
                continue
            text = r[col]
            if not text:
                continue
            pairs = find_pairs(text, ps)
            if not pairs:
                continue
            new = rewrite_renderings(text, pairs)
            if new != text:
                changes.append((table, r['id'] if table == 'articles' else r['ai_id'], col, text, new))
                for p in pairs:
                    pair_tally[p] += 1
    stmt_changes = []
    if args.statements:
        ids = {r['id'] for r in rows}
        for s in conn.execute("SELECT id, article_id, statement_text FROM key_figure_statements WHERE statement_text IS NOT NULL"):
            if s['article_id'] not in ids or not persons.get(s['article_id']):
                continue
            pairs = find_pairs(s['statement_text'], persons[s['article_id']])
            if pairs:
                new = rewrite_renderings(s['statement_text'], pairs)
                if new != s['statement_text']:
                    stmt_changes.append(('key_figure_statements', s['id'], 'statement_text', s['statement_text'], new))

    print(f"{len(rows)} analysed articles scanned; {len(changes)} field rewrites"
          f"{f' + {len(stmt_changes)} statements' if args.statements else ''}; "
          f"{len(pair_tally)} distinct (rendering → form) pairs")
    print("\nMost frequent pairs:")
    for (old, new), n in pair_tally.most_common(args.show):
        print(f"  {n:5d}  {old!r:28} -> {new!r}")
    print("\nSample field changes:")
    for table, rid, col, old, new in changes[:args.show]:
        print(f"  {table}.{col} #{rid}\n    - {old[:160]}\n    + {new[:160]}")
    if not args.apply:
        print("\nDRY RUN — pass --apply to write.")
        return
    ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
    name = os.path.splitext(os.path.basename(args.db or 'db'))[0]
    manifest = f"prose-names-{name}-{ts}.manifest"
    with open(manifest, 'w', encoding='utf-8') as fh:
        for table, rid, col, old, new in changes + stmt_changes:
            fh.write(json.dumps({'table': table, 'id': rid, 'field': col, 'old': old, 'new': new}, ensure_ascii=False) + '\n')
            conn.execute(f"UPDATE {table} SET {col} = ? WHERE id = ? AND {col} = ?", (new, rid, old))
    conn.commit()
    print(f"\nApplied {len(changes) + len(stmt_changes)} rewrites. Manifest: {manifest}")


if __name__ == '__main__':
    main()
