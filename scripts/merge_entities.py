"""
Interactive entity-name merge tool.

Finds clusters of near-duplicate English entity names (e.g. "Lai Ching-te" /
"Lai Chingte" / "Lai Ching Te") and lets the analyst pick a canonical form.
Variants are bulk-updated to the canonical name across the entire entities
table. Grouping for the dashboard happens on `entity_name_en` alone
(see stats.py leaderboard), so unifying the English spelling is what fixes
mention counts and entity-filter behaviour.

Usage:
    python scripts/merge_entities.py --dry-run                    # survey
    python scripts/merge_entities.py --type person --days 90      # interactive
    python scripts/merge_entities.py --threshold 0.9              # tighter matches
"""
import sys
import os
import argparse
from collections import defaultdict
from difflib import SequenceMatcher

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.utils.db import get_connection

ENTITY_TYPES = [
    'person', 'military_unit', 'ship', 'aircraft',
    'location', 'organisation', 'weapon_system',
]


def similarity(a: str, b: str) -> float:
    """Case-insensitive SequenceMatcher ratio."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def collect_entities(conn, days: int, type_filter: str | None):
    """Return list of (entity_name_en, entity_type, mentions) for visible articles."""
    VISIBLE = (
        "a.is_hidden = 0 AND a.analyst_approved = 1 "
        "AND (ai.needs_human_review = 0 OR ai.review_resolved = 1)"
    )
    sql = f"""
        SELECT e.entity_name_en, e.entity_type, COUNT(*) AS mentions
        FROM entities e
        JOIN articles a ON e.article_id = a.id
        JOIN ai_analysis ai ON ai.article_id = a.id
        WHERE a.published_at >= datetime('now', ?)
          AND {VISIBLE}
          AND e.entity_name_en IS NOT NULL
          AND TRIM(e.entity_name_en) != ''
    """
    params = [f'-{days} days']
    if type_filter:
        sql += " AND e.entity_type = ?"
        params.append(type_filter)
    sql += " GROUP BY e.entity_name_en, e.entity_type ORDER BY mentions DESC"
    return conn.execute(sql, params).fetchall()


def cluster_within_type(names_with_counts, threshold: float):
    """Greedy clustering: seed with highest-mention names, attach near-matches.

    names_with_counts: list of (name, mentions) tuples, pre-sorted by mentions desc.
    Returns: list of clusters, each a list of (name, mentions) of size >= 1.
    """
    assigned = set()
    clusters = []
    for i, (name_i, cnt_i) in enumerate(names_with_counts):
        if name_i in assigned:
            continue
        cluster = [(name_i, cnt_i)]
        assigned.add(name_i)
        for name_j, cnt_j in names_with_counts[i + 1:]:
            if name_j in assigned:
                continue
            if similarity(name_i, name_j) >= threshold:
                cluster.append((name_j, cnt_j))
                assigned.add(name_j)
        clusters.append(cluster)
    return clusters


def find_clusters(rows, threshold: float, min_mentions: int):
    """Group rows by entity_type, cluster within each, filter by thresholds.

    Returns: list of (entity_type, cluster) where cluster is [(name, mentions), ...].
    Only clusters with >=2 members and at least one member >= min_mentions are kept.
    """
    by_type = defaultdict(list)
    for row in rows:
        by_type[row['entity_type']].append((row['entity_name_en'], row['mentions']))

    results = []
    for etype, items in by_type.items():
        items.sort(key=lambda x: -x[1])
        for cluster in cluster_within_type(items, threshold):
            if len(cluster) < 2:
                continue
            if max(c[1] for c in cluster) < min_mentions:
                continue
            results.append((etype, cluster))
    # Largest clusters first for better signal
    results.sort(key=lambda x: -sum(c[1] for c in x[1]))
    return results


def print_cluster(etype, cluster, indent="  "):
    width = max(len(n) for n, _ in cluster)
    print(f"[{etype}] cluster:")
    for i, (name, cnt) in enumerate(cluster, start=1):
        print(f"{indent}{i}) {name.ljust(width)}  ({cnt} mention{'s' if cnt != 1 else ''})")


def prompt_canonical(cluster):
    """Return (canonical_name, variants) tuple, or the strings 'skip' / 'quit'.

    Accepts:
      - A number (1-N): pick that cluster member as canonical
      - Free text:      use as a custom canonical name (merges all cluster members into it)
      - s / skip:       skip this cluster
      - q / quit:       commit progress and exit
    """
    n = len(cluster)
    while True:
        raw = input(f"Canonical? [1-{n}, free text, s=skip, q=quit]: ").strip()
        low = raw.lower()
        if low in ('s', 'skip'):
            return 'skip'
        if low in ('q', 'quit'):
            return 'quit'
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < n:
                canonical = cluster[idx][0]
                variants  = [name for i, (name, _) in enumerate(cluster) if i != idx]
                return canonical, variants
            print(f"  Enter 1-{n}, free text, s, or q.")
        elif raw:
            # Free-text canonical — merge all cluster members into it
            canonical = raw
            variants  = [name for name, _ in cluster]
            return canonical, variants


def confirm(prompt: str) -> bool:
    return input(f"{prompt} (y/N): ").strip().lower() in ('y', 'yes')


def apply_merge(conn, canonical: str, variants: list[str]):
    """Update all rows with entity_name_en in variants to canonical. Returns total rows affected."""
    total = 0
    for variant in variants:
        cur = conn.execute(
            "UPDATE entities SET entity_name_en = ? WHERE entity_name_en = ?",
            (canonical, variant),
        )
        total += cur.rowcount
    conn.commit()
    return total


def main():
    parser = argparse.ArgumentParser(description="Merge near-duplicate entity names")
    parser.add_argument('--type', choices=ENTITY_TYPES, default=None,
                        help="Limit to one entity type (default: all types)")
    parser.add_argument('--days', type=int, default=90,
                        help="Consider entities from articles in last N days (default: 90)")
    parser.add_argument('--threshold', type=float, default=0.85,
                        help="SequenceMatcher similarity threshold 0.0-1.0 (default: 0.85)")
    parser.add_argument('--min-mentions', type=int, default=2,
                        help="Skip clusters where all members have fewer than N mentions (default: 2)")
    parser.add_argument('--dry-run', action='store_true',
                        help="Print proposed clusters without prompting or writing")
    args = parser.parse_args()

    if not 0.0 < args.threshold <= 1.0:
        print("ERROR: --threshold must be between 0.0 and 1.0")
        sys.exit(1)

    conn = get_connection()
    rows = collect_entities(conn, args.days, args.type)
    print(f"Loaded {len(rows)} distinct (entity_name_en, entity_type) pairs "
          f"from last {args.days} days"
          + (f" for type={args.type}" if args.type else "") + ".")

    clusters = find_clusters(rows, args.threshold, args.min_mentions)
    print(f"Found {len(clusters)} cluster(s) with >=2 members at threshold {args.threshold}.\n")

    if not clusters:
        print("Nothing to merge.")
        conn.close()
        return

    if args.dry_run:
        print("DRY RUN — no changes will be made.\n")
        for etype, cluster in clusters:
            print_cluster(etype, cluster)
            print()
        conn.close()
        return

    merges_done = 0
    rows_updated = 0
    for etype, cluster in clusters:
        print()
        print_cluster(etype, cluster)
        result = prompt_canonical(cluster)
        if result == 'quit':
            print("Quitting — committing work done so far.")
            break
        if result == 'skip':
            continue

        canonical_name, variants = result

        print(f"\n  Will update:")
        for variant in variants:
            mention_lookup = {name: cnt for name, cnt in cluster}
            cnt = mention_lookup.get(variant, '?')
            print(f"    '{variant}' → '{canonical_name}'  ({cnt} row{'s' if cnt != 1 else ''})")

        if not confirm("  Proceed?"):
            print("  Skipped.")
            continue

        updated = apply_merge(conn, canonical_name, variants)
        print(f"  ✓ Updated {updated} row{'s' if updated != 1 else ''}.")
        merges_done += 1
        rows_updated += updated

    conn.close()
    print(f"\nDone. {merges_done} merge(s) applied, {rows_updated} row(s) updated.")


if __name__ == '__main__':
    main()
