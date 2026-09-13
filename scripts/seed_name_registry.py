"""Seed / export the name registry (table name_registry, migration 0014).

Seed (default): every person-shaped entry in scraper/processors/glossary.json
and entity_canonical.json becomes an APPROVED registry row (source
'glossary' / 'canonical'), simplified keys folded onto the traditional row.
Idempotent — existing rows are left alone, so analyst edits survive a
re-seed. Run on BOTH worktrees (DBs are separate).

Export (--export): writes approved rows the worker or the analyst produced
(source wikidata / search / generated / analyst) back into glossary.json
and entity_canonical.json, both scripts, so the decision travels through
git to the other worktree — review the diff and commit, the way
refresh_officials.py output is handled.

    python scripts/seed_name_registry.py                 # seed the worktree DB
    python scripts/seed_name_registry.py --db /var/www/cross-strait-signal/db/cross_strait_signal.db
    python scripts/seed_name_registry.py --export        # registry → JSON (then git diff)
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.utils.db import get_connection
from shared.name_registry import to_simp, to_trad, upsert
from shared.romanisation import CJK_NAME

REPO = os.path.join(os.path.dirname(__file__), '..')
GLOSSARY = os.path.join(REPO, 'scraper', 'processors', 'glossary.json')
CANON = os.path.join(REPO, 'scraper', 'processors', 'entity_canonical.json')

# A person entry: 2–4 CJK characters mapping to a short capitalised English
# name with no digits ("Lai Ching-te", "Joseph Wu", "Xi Jinping",
# "Simon Teng-Chi Chang"); organisations, exercises and places fail one of
# the tests ("Taiwan Foundation for Democracy", "Joint Sword 2024B", "PLA").
_PERSON_EN = re.compile(r"^(?:[A-Z][A-Za-z'.\-]*\s){1,3}[A-Z][A-Za-z'.\-]*$")
_NOT_PERSON_ZH = re.compile(r"[會部院局黨軍署處委司隊團社報網站校所館廳市縣區島]$|演習|[0-9]")


def person_entries(mapping):
    for zh, en in mapping.items():
        if not CJK_NAME.match(zh) or _NOT_PERSON_ZH.search(zh):
            continue
        if not isinstance(en, str) or not _PERSON_EN.match(en.strip()) or en.split()[-1] in ('Party', 'Office', 'Council', 'Yuan', 'Ministry', 'Foundation', 'Navy', 'Army', 'Forum'):
            continue
        yield zh, en.strip()


def seed(conn):
    g = json.load(open(GLOSSARY, encoding='utf-8'))
    c = json.load(open(CANON, encoding='utf-8'))
    c = c.get('canonical', c)
    seen, added = set(), 0
    for source, mapping in (('glossary', g), ('canonical', c)):
        for zh, en in person_entries(mapping):
            key = to_trad(zh)
            if key in seen:
                continue
            seen.add(key)
            before = conn.execute("SELECT COUNT(*) FROM name_registry").fetchone()[0]
            upsert(conn, zh, en, None, source, 'approved', evidence_note=f'seeded from {source}.json')
            after = conn.execute("SELECT COUNT(*) FROM name_registry").fetchone()[0]
            added += after - before
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM name_registry WHERE status = 'approved'").fetchone()[0]
    print(f"seed: {len(seen)} person entries in the JSON files, {added} new rows, {total} approved rows in the registry")


def export(conn):
    rows = conn.execute("""SELECT zh_trad, zh_simp, en FROM name_registry
        WHERE status = 'approved' AND en IS NOT NULL AND source IN ('wikidata', 'search', 'generated', 'analyst')""").fetchall()
    graw = open(GLOSSARY, encoding='utf-8').read()
    craw = open(CANON, encoding='utf-8').read()
    g, c = json.loads(graw), json.loads(craw)
    gi = 2 if graw.startswith('{\n  "') else 4
    ci = 2 if craw.startswith('{\n  "') else 4
    ng = nc = 0
    for r in rows:
        for form in {r['zh_trad'], r['zh_simp'] or to_simp(r['zh_trad'])}:
            if g.get(form) != r['en']:
                g[form] = r['en']
                ng += 1
            if c['canonical'].get(form) != r['en']:
                c['canonical'][form] = r['en']
                nc += 1
    with open(GLOSSARY, 'w', encoding='utf-8') as f:
        f.write(json.dumps(g, ensure_ascii=False, indent=gi) + '\n')
    with open(CANON, 'w', encoding='utf-8') as f:
        f.write(json.dumps(c, ensure_ascii=False, indent=ci) + '\n')
    print(f"export: {len(rows)} approved worker/analyst rows → glossary.json {ng} key(s) written, entity_canonical.json {nc} key(s) written; review the diff and commit")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', help='target another worktree DB')
    ap.add_argument('--export', action='store_true', help='write approved worker/analyst rows back into the JSON files')
    args = ap.parse_args()
    conn = get_connection(args.db)
    if args.export:
        export(conn)
    else:
        seed(conn)
    conn.close()


if __name__ == '__main__':
    main()
