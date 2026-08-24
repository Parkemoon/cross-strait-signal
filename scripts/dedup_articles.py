"""Same-outlet duplicate article sweep — detection in shared/article_dedup.py
(R1 content-hash / R2 content-sim>=0.90 / R3 title-same-day; same source
only, cross-outlet duplication is signal and never touched).

Two callers:
  - CLI (dry-run default; --apply hides): the historical/backlog sweep.
    Writes a manifest with revert SQL next to the CWD on --apply.
        python scripts/dedup_articles.py                    # dry-run, analysed articles, full history
        python scripts/dedup_articles.py --days 30 --apply
        python scripts/dedup_articles.py --db /var/www/cross-strait-signal/db/cross_strait_signal.db --apply
  - run_pipeline.py Step 2m calls dedup_recent_articles() every tick over
    the last 8 days INCLUDING unanalysed rows, hiding dupes before Tier-1
    selects them (the selection queries exclude is_hidden=1) — so a dupe
    never reaches the feed or the Gemini bill.

Duplicates are hidden (articles.is_hidden=1), never deleted; the richest
copy is kept (visible > approved > analyst-overridden > analysed > longest
content > earliest). Idempotent — already-hidden rows are never re-hidden
and never chosen as keeper over a visible copy.
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.article_dedup import find_duplicate_groups, choose_keeper, prepare
from scraper.utils.db import get_connection


def _collect(conn, days=None, include_unanalysed=False):
    where = ["1=1"]
    params = []
    if days is not None:
        where.append("a.published_at >= strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)")
        params.append(f'-{days} days')
    if not include_unanalysed:
        where.append("ai.id IS NOT NULL")
    rows = conn.execute(f"""
        SELECT a.id, a.source_id, a.title_original, a.content_original,
               a.published_at, a.scraped_at, a.is_hidden, a.analyst_approved,
               (a.title_en_override IS NOT NULL OR a.summary_en_override IS NOT NULL
                OR a.key_quote_override IS NOT NULL) AS has_override,
               (ai.id IS NOT NULL) AS has_analysis
        FROM articles a
        LEFT JOIN ai_analysis ai ON ai.article_id = a.id
        WHERE {' AND '.join(where)}
    """, params).fetchall()
    return [p for p in (prepare(dict(r)) for r in rows) if p is not None]


def run_dedup(conn, days=None, include_unanalysed=False, apply=False, verbose=True):
    """Detect and (optionally) hide same-outlet dupes. Returns the list of
    (dupe_id, keeper_id, rule) actions — only visible non-keepers are acted on."""
    prepared = _collect(conn, days=days, include_unanalysed=include_unanalysed)
    groups, rules = find_duplicate_groups(prepared)

    source_names = {r['id']: r['name'] for r in conn.execute("SELECT id, name FROM sources")}
    actions = []
    for group in sorted(groups, key=lambda g: min(p['id'] for p in g)):
        keeper = choose_keeper(group)
        dupes = [p for p in group if p['id'] != keeper['id'] and not p['is_hidden']]
        if not dupes:
            continue  # already fully collapsed — idempotent re-run
        if verbose:
            print(f"[{source_names.get(keeper['source_id'], keeper['source_id'])}] "
                  f"keep {keeper['id']} ({keeper['ts'].date()}, "
                  f"ap={keeper['analyst_approved']}, {keeper['content_len']}ch) "
                  f"— hide {len(dupes)}:")
            for p in sorted(dupes, key=lambda p: p['id']):
                print(f"    {p['id']} ({p['ts'].date()}, ap={p['analyst_approved']}) "
                      f"[{rules.get(p['id'], '?')}]")
        actions.extend((p['id'], keeper['id'], rules.get(p['id'], '?')) for p in dupes)

    if verbose:
        print(f"\n{len(groups)} duplicate group(s); "
              f"{len(actions)} article(s) to hide ({len(prepared)} scanned).")
    if apply and actions:
        conn.executemany(
            "UPDATE articles SET is_hidden = 1 WHERE id = ? AND is_hidden = 0",
            [(dupe_id,) for dupe_id, _, _ in actions])
        conn.commit()
        if verbose:
            print(f"Applied: {len(actions)} article(s) hidden.")
    return actions


def dedup_recent_articles(days=8, apply=True):
    """Pipeline Step 2m entry point: sweep the recent window, all articles
    (analysed or not — the point is to hide dupes BEFORE Tier-1 pays for
    them). 8 days covers R1's 7-day window with margin. Returns hide count."""
    conn = get_connection()
    try:
        actions = run_dedup(conn, days=days, include_unanalysed=True, apply=apply)
    finally:
        conn.close()
    return len(actions)


def _write_manifest(path, actions, db_path):
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    ids = [str(dupe_id) for dupe_id, _, _ in actions]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f"# Same-outlet duplicate sweep — scripts/dedup_articles.py, {now}\n")
        f.write(f"# DB: {db_path or 'default'}\n")
        f.write(f"# {len(ids)} articles hidden (is_hidden 0 -> 1). Revert with:\n")
        f.write("#   UPDATE articles SET is_hidden=0 WHERE id IN (<ids below>);\n")
        f.write("# dupe_id -> keeper_id [rule]\n")
        for dupe_id, keeper_id, rule in actions:
            f.write(f"{dupe_id} -> {keeper_id} [{rule}]\n")
        f.write("ids: " + ",".join(ids) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Hide same-outlet near-duplicate articles (dry-run by default).")
    ap.add_argument('--db', help="path to another worktree's DB (e.g. prod)")
    ap.add_argument('--days', type=int, default=None,
                    help="only scan articles published in the last N days (default: full history)")
    ap.add_argument('--all', action='store_true',
                    help="include unanalysed articles (default: analysed only — the feed-relevant set)")
    ap.add_argument('--apply', action='store_true', help="hide the detected dupes (default: dry-run)")
    args = ap.parse_args()

    conn = get_connection(args.db)
    try:
        actions = run_dedup(conn, days=args.days, include_unanalysed=args.all, apply=args.apply)
        if args.apply and actions:
            # Tag with the target DB's worktree so a prod run and a staging
            # run on the same day can't overwrite each other's manifest.
            tag = 'default'
            if args.db:
                tag = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(args.db)))) or 'db'
            stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
            manifest = f"dedup-articles-{tag}-{stamp}.manifest"
            _write_manifest(manifest, actions, args.db)
            print(f"Manifest: {manifest}")
        elif not args.apply and actions:
            print("Dry-run — re-run with --apply to hide.")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
