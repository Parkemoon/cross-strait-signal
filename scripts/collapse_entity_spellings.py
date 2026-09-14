"""
Collapse English-spelling variants of one entity onto a single rendering.

The pipeline keys an entity on its original-language name (`entity_name`,
simplified folded onto traditional), so rows sharing that key are the
same thing the model rendered differently across articles — "United
States" / "USA", "Taipei" / "Taipei City", "Chieh Chung" / "Jie Zhong", or
a stray misattribution ("Cheng Li-wun" on 尹乃菁). `renormalise_entities.py`
repairs the names the canonical file knows; this sweep handles the rest
deterministically: every (type, name) group with more than one non-empty
`entity_name_en` is rewritten to its plurality spelling.

Precision gates (a group is SKIPPED, never partially rewritten):
  * side conflict — two spellings carry different side words ("PRC
    Ministry of National Defense" vs "Ministry of National Defense
    (Taiwan)"): the Chinese name is ambiguous across the strait and the
    plurality would misattribute the minority. A spelling with no side
    word may collapse onto one with a side word and vice versa.
  * person groups whose roles read as both Taiwan-side and PRC-side
    (`shared.romanisation.side_from_role`): namesakes across the strait
    (a Taiwanese 李強 and Premier Li Qiang).
  * person groups on the Taiwan side never collapse onto a Hanyu-marked
    spelling while an unmarked one exists — the plurality is taken over
    the unmarked spellings.
  * names the canonical file or an approved registry row resolves are
    left to `renormalise_entities.py`, which owns them.
  * single-character keys (雷 covered three different destroyers).
  * person groups where a minority spelling on COMPETING_MIN_ROWS or more
    rows shares no token with the target and is not the other
    romanisation of it (Chin Jih-hsin / Qin Ri-xin collapse; Kharis
    Templeman vs Kurlantzick is held and printed for the analyst).

Dry-run by default; --apply writes and drops a revert manifest (id ->
previous spelling) next to the CWD, same convention as dedup_articles.py.

Usage:
    python scripts/collapse_entity_spellings.py                  # dry-run, all types
    python scripts/collapse_entity_spellings.py --type person --days 180
    python scripts/collapse_entity_spellings.py --db /var/www/cross-strait-signal/db/cross_strait_signal.db --apply
"""
import argparse
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.utils.db import get_connection  # noqa: E402
from shared.entity_norm import load_canon, resolve_name_en  # noqa: E402
from shared.name_registry import to_trad, load_approved, merge_canon  # noqa: E402
from shared.romanisation import hanyu_markers, side_from_role  # noqa: E402

# Side words whose presence in an English rendering marks which side of the
# strait (or which third country) the body belongs to. A group whose
# spellings disagree on these is ambiguous and is skipped.
_SIDE_WORDS = {
    'TW': re.compile(r"\b(taiwan|taiwanese|roc|r\.o\.c\.|taipei)\b", re.I),
    'PRC': re.compile(r"\b(prc|china|chinese|mainland|beijing|p\.r\.c\.)\b", re.I),
    'US': re.compile(r"\b(us|u\.s\.|usa|united states|american)\b", re.I),
    'JP': re.compile(r"\b(japan|japanese)\b", re.I),
    'HK': re.compile(r"\b(hong kong|hk|macau|macao)\b", re.I),
}


def side_words(en):
    return frozenset(k for k, rx in _SIDE_WORDS.items() if rx.search(en or ''))


def choose_target(spellings, tw_person):
    """Plurality spelling; ties broken by the longer (fuller) form. For a
    Taiwan-side person the plurality is taken over unmarked spellings
    when any exist."""
    pool = spellings
    if tw_person:
        unmarked = {s: n for s, n in spellings.items() if not hanyu_markers(s)}
        if unmarked:
            pool = unmarked
    return max(pool.items(), key=lambda kv: (kv[1], len(kv[0])))[0]


def plan(conn, entity_type=None, days=None, canon=None):
    """Return (actions, skipped, held): actions = [(row_id, old_en, new_en,
    group_key)], skipped = Counter of skip reasons, held = competing-identity
    groups for the analyst. `canon` defaults to the JSON canon with the DB's
    approved registry rows layered over it (same precedence as the pipeline
    and renormalise_entities.py)."""
    if canon is None:
        canon = merge_canon(load_canon(), load_approved(conn))
    where, params = ["e.entity_name_en IS NOT NULL", "TRIM(e.entity_name_en) != ''"], []
    if entity_type:
        where.append("e.entity_type = ?")
        params.append(entity_type)
    if days:
        where.append("a.published_at >= date('now', ?)")
        params.append(f'-{days} days')
    rows = conn.execute(f"""
        SELECT e.id, e.entity_type, e.entity_name, e.entity_name_en, e.entity_role
        FROM entities e JOIN articles a ON a.id = e.article_id
        WHERE {' AND '.join(where)}""", params).fetchall()

    groups = defaultdict(list)
    for r in rows:
        zh = (r['entity_name'] or '').strip()
        if not zh:
            continue
        groups[(r['entity_type'], to_trad(zh))].append(r)

    actions, skipped, held = [], Counter(), []
    for (etype, key), members in groups.items():
        spellings = Counter((m['entity_name_en'] or '').strip() for m in members)
        if len(spellings) < 2:
            continue
        if len(key) < 2:
            # a single character is not a name: 雷 covered three different
            # Japanese destroyers in one group
            skipped['single-character key'] += 1
            continue
        # Names the canonical file / registry own belong to renormalise_entities.py
        if resolve_name_en(key, canon):
            skipped['canonical (renormalise owns it)'] += 1
            continue
        sides = {s: side_words(s) for s in spellings}
        distinct_sides = {v for v in sides.values() if v}
        if len(distinct_sides) > 1:
            skipped['side conflict between spellings'] += 1
            continue
        tw_person = False
        if etype == 'person':
            role_sides = Counter(side_from_role(m['entity_role']) for m in members)
            if role_sides['TW'] and role_sides['PRC']:
                skipped['person: roles on both sides'] += 1
                continue
            tw_person = role_sides['TW'] > 0
        target = choose_target(spellings, tw_person)
        if etype == 'person':
            # A minority spelling sharing no token with the target, carried
            # by several rows, is a competing identity the model attached
            # consistently (祁凱立: Kharis Templeman ×14 vs Kurlantzick) —
            # not a slip to overwrite. Held for the analyst, listed in the report.
            # A pair where one side is Hanyu-marked and the other is not is
            # the same person in two romanisations (Chin Jih-hsin / Qin
            # Ri-xin, Chou Hsuan / Zhou Xuan) — not a rival; that is the
            # collapse this sweep exists for, whichever side the role reads.
            rivals = [(s, n) for s, n in spellings.items()
                      if s != target and n >= COMPETING_MIN_ROWS and not _share_token(s, target)
                      and not (bool(hanyu_markers(s)) != bool(hanyu_markers(target)))]
            if rivals:
                skipped['person: competing identity (held for review)'] += 1
                held.append((f"{etype}:{key}", target, spellings[target], rivals))
                continue
        for m in members:
            old = (m['entity_name_en'] or '').strip()
            if old != target:
                actions.append((m['id'], old, target, f"{etype}:{key}"))
    return actions, skipped, held


COMPETING_MIN_ROWS = 3
_TOKEN = re.compile(r"[A-Za-z]+")


def _share_token(a, b):
    ta = {t.lower() for t in _TOKEN.findall(a)}
    tb = {t.lower() for t in _TOKEN.findall(b)}
    return bool(ta & tb)


def _write_manifest(path, actions, db_path):
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f"# Entity spelling collapse — scripts/collapse_entity_spellings.py, {now}\n")
        f.write(f"# DB: {db_path or 'default'}\n")
        f.write(f"# {len(actions)} entity rows rewritten. Revert with the UPDATEs below.\n")
        for row_id, old, new, key in actions:
            old_sql = old.replace("'", "''")
            f.write(f"UPDATE entities SET entity_name_en='{old_sql}' WHERE id={row_id}; -- {key}: '{new}' -> '{old}'\n")


def main():
    ap = argparse.ArgumentParser(description="Collapse English-spelling variants per entity (dry-run by default).")
    ap.add_argument('--db', help="path to another worktree's DB (e.g. prod)")
    ap.add_argument('--type', dest='entity_type', help="one entity_type (e.g. person)")
    ap.add_argument('--days', type=int, default=None, help="only rows on articles published in the last N days")
    ap.add_argument('--show', type=int, default=30, help="groups to print in the report")
    ap.add_argument('--apply', action='store_true', help="write the rewrites (default: dry-run)")
    args = ap.parse_args()

    conn = get_connection(args.db)
    try:
        actions, skipped, held = plan(conn, entity_type=args.entity_type, days=args.days)
        by_group = defaultdict(list)
        for row_id, old, new, key in actions:
            by_group[key].append((old, new))
        print(f"DB: {args.db or 'default'} | groups to collapse: {len(by_group)} | rows to rewrite: {len(actions)}")
        for reason, n in skipped.most_common():
            print(f"  skipped {n:>5}  {reason}")
        if held:
            print("\nHeld for review — competing identities on one Chinese name (nothing written):")
            for key, target, n, rivals in sorted(held, key=lambda h: -sum(r[1] for r in h[3])):
                print(f"  {key:<32} '{target}'×{n}  vs  " + ", ".join(f"'{s}'×{c}" for s, c in rivals))
            print()
        for key, changes in sorted(by_group.items(), key=lambda kv: -len(kv[1]))[:args.show]:
            olds = Counter(o for o, _ in changes)
            new = changes[0][1]
            print(f"  {len(changes):>4}  {key:<40} -> '{new}'   from " +
                  ", ".join(f"'{o}'×{n}" for o, n in olds.most_common(4)))
        if len(by_group) > args.show:
            print(f"  ... and {len(by_group) - args.show} more groups")

        if not args.apply:
            if actions:
                print("\nDRY RUN — pass --apply to write.")
            return
        if not actions:
            print("Nothing to do.")
            return
        conn.executemany("UPDATE entities SET entity_name_en = ? WHERE id = ?",
                         [(new, row_id) for row_id, _, new, _ in actions])
        conn.commit()
        tag = 'default'
        if args.db:
            tag = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(args.db)))) or 'db'
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        manifest = f"collapse-entities-{tag}-{stamp}.manifest"
        _write_manifest(manifest, actions, args.db)
        print(f"\nApplied {len(actions)} updates. Manifest: {manifest}")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
