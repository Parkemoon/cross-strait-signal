#!/usr/bin/env python3
"""Re-apply the house name style (shared/name_style.py) to every approved
registry row — the catch-up pass for rows that entered before the style
hooks existed, or after a bulk import.

    python scripts/restyle_names.py [--db PATH]          # dry run: prints what would change
    python scripts/restyle_names.py [--db PATH] --apply  # writes, stamps reviewed_by

The write path already styles every new row (registry upsert, Admin ▾ Names
approve / patch), so this normally prints nothing. After an --apply run:
`seed_name_registry.py --export` (files), commit, then
`renormalise_entities.py --type person --apply` so history follows.
Rows whose form still carries a comma after styling are printed under
REVIEW and never written — they are not a single person.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.utils.db import get_connection  # noqa: E402
from shared.name_style import style_change  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', help='target another worktree DB')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--tag', default='style', help="reviewed_by stamp on written rows (default 'style')")
    args = ap.parse_args()
    conn = get_connection(args.db)
    rows = conn.execute("""SELECT id, zh_trad, en, side, role_hint FROM name_registry
                           WHERE status = 'approved' AND en IS NOT NULL""").fetchall()
    changes, review = [], []
    for r in rows:
        new, rule = style_change(r['zh_trad'], r['en'], r['side'], r['role_hint'])
        if ',' in new:
            review.append(r)
        elif rule:
            changes.append((r['id'], r['zh_trad'], r['en'], new, rule))
    for _, zh, old, new, rule in changes:
        print(f"  {rule:8} {zh:8} {old!r:30} -> {new!r}")
    if review:
        print("REVIEW (comma survives — not a single person; reject or edit in Admin ▾ Names):")
        for r in review:
            print(f"  {r['id']:6} {r['zh_trad']} {r['en']!r}")
    if not args.apply:
        print(f"\n{len(changes)} of {len(rows)} approved rows would change. DRY RUN — pass --apply to write.")
        return
    for rid, _, old, new, rule in changes:
        conn.execute("""UPDATE name_registry SET en = ?, reviewed_by = ?, reviewed_at = datetime('now'),
                        evidence_note = COALESCE(evidence_note, '') || ' | ' || ? || ': was ' || ?
                        WHERE id = ?""", (new, args.tag, rule, old, rid))
    conn.commit()
    print(f"\nApplied {len(changes)} of {len(rows)} approved rows.")


if __name__ == '__main__':
    main()
