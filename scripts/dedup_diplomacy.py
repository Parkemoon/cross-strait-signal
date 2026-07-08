"""
Semantic dedup for approved diplomacy_statements.

Promotes the 2026-06-30 ad-hoc dedup passes (5 scratchpad one-offs, see
SESSION_LOG) to a repeatable maintenance script. The Tier-1 side-extract
has no canonical key for diplomacy rows (unlike exercises/polls), so the
same policy line reported by several outlets — or re-extracted at
slightly different stances — accumulates as near-duplicate approved rows
that all render in the country drill-in panel.

Method (mirrors the converged "pass 5" design):
  1. Bucket approved rows by (country_iso, official-vs-non-official).
     Buckets deliberately IGNORE speaker and exact authority_tier — the
     AI labels the same voice inconsistently (the National Museums
     Scotland triplet split across `other`×2 + `subnational`×1 and was
     never compared by tier-exact passes).
  2. Embed statement_en (fallback statement_zh) with gemini-embedding-001
     (text-embedding-004 was retired — 404s since ~2026-06). No on-disk
     cache: ~2k short statements cost pennies; a cache just rots when the
     model changes again.
  3. Union-find over pairs with cosine similarity >= --threshold
     (default 0.86, the value Ed picked for the aggressive pass).
  4. Per cluster: if max-min stance spread > --quarantine-spread (0.6),
     leave the cluster untouched and report it (wide spread usually means
     a genuine timeline — e.g. the US arms-sale pause→approve sequence —
     not duplicates). Otherwise the representative is the member whose
     stance is nearest the cluster MEDIAN (kills outlier scores; ties →
     newest), and every other member becomes status='merged',
     merged_into_id=rep.
  5. Chain-flatten: repoint any merged row whose target is itself merged
     (path compression), so the "merge target must be approved" invariant
     holds — bulk SQL in June created 576 two-hop chains by skipping it.

Dry-run by default. Typical cadence: run after big review-queue sessions
or monthly; NOT wired into the 6-hourly pipeline (it re-reads the whole
approved corpus and calls the embedding API).

Usage:
    python scripts/dedup_diplomacy.py                     # dry-run, staging DB
    python scripts/dedup_diplomacy.py --db /var/www/cross-strait-signal/db/cross_strait_signal.db
    python scripts/dedup_diplomacy.py --apply
    python scripts/dedup_diplomacy.py --country US --threshold 0.9
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import scraper.utils.db as dbmod
from scraper.utils.llm import get_gemini_client

EMBED_MODEL = 'gemini-embedding-001'
EMBED_BATCH = 100          # API max contents per embed call
OFFICIAL_TIERS = {'government', 'head_of_state'}


def _client():
    return get_gemini_client()


def _embed_all(client, texts):
    """Embed texts in batches; returns an (n, dims) unit-normalised array."""
    vecs = []
    for i in range(0, len(texts), EMBED_BATCH):
        chunk = texts[i:i + EMBED_BATCH]
        resp = client.models.embed_content(
            model=EMBED_MODEL, contents=chunk,
            config={'task_type': 'SEMANTIC_SIMILARITY'})
        vecs.extend(e.values for e in resp.embeddings)
        print(f"  embedded {min(i + EMBED_BATCH, len(texts))}/{len(texts)}")
    arr = np.asarray(vecs, dtype=np.float32)
    return arr / np.linalg.norm(arr, axis=1, keepdims=True)


class _UnionFind:
    def __init__(self, ids):
        self.parent = {i: i for i in ids}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _pick_representative(members):
    """Member nearest the cluster median stance; ties broken by newest."""
    stances = sorted(m['stance'] for m in members)
    median = stances[len(stances) // 2] if len(stances) % 2 else (
        (stances[len(stances) // 2 - 1] + stances[len(stances) // 2]) / 2)
    return min(members,
               key=lambda m: (abs(m['stance'] - median),
                              -(m['id'])))  # newer id wins ties


def _flatten_chains(conn, apply):
    """Repoint merged rows whose merged_into_id is itself merged."""
    repointed = 0
    while True:
        rows = conn.execute("""
            SELECT c.id, t.merged_into_id AS next_hop
            FROM diplomacy_statements c
            JOIN diplomacy_statements t ON t.id = c.merged_into_id
            WHERE c.approval_status = 'merged' AND t.approval_status = 'merged'
        """).fetchall()
        if not rows:
            break
        for r in rows:
            if apply:
                conn.execute(
                    "UPDATE diplomacy_statements SET merged_into_id = ? WHERE id = ?",
                    (r['next_hop'], r['id']))
            repointed += 1
        if not apply:
            break  # dry-run can't converge — one report round is enough
    return repointed


def main():
    ap = argparse.ArgumentParser(description="Semantic dedup for approved diplomacy statements")
    ap.add_argument('--db', help="Path to another worktree's DB (e.g. prod)")
    ap.add_argument('--apply', action='store_true', help="Write merges (default: dry-run)")
    ap.add_argument('--threshold', type=float, default=0.86,
                    help="Cosine similarity merge threshold (default 0.86)")
    ap.add_argument('--quarantine-spread', type=float, default=0.6,
                    help="Leave clusters whose stance spread exceeds this (default 0.6)")
    ap.add_argument('--country', help="Restrict to one country_iso")
    args = ap.parse_args()

    conn = dbmod.get_connection(args.db)
    tag = f"dedup:diplomacy-{datetime.now(timezone.utc).strftime('%Y%m%d')}"

    where = "approval_status = 'approved'"
    params = []
    if args.country:
        where += " AND country_iso = ?"
        params.append(args.country.upper())
    rows = conn.execute(f"""
        SELECT id, country_iso, authority_tier, stance, statement_en, statement_zh
        FROM diplomacy_statements WHERE {where}
    """, params).fetchall()
    rows = [dict(r) for r in rows
            if (r['statement_en'] or r['statement_zh'] or '').strip()]
    print(f"{len(rows)} approved statements in scope "
          f"({'dry-run' if not args.apply else 'APPLY'}, T={args.threshold})")
    if not rows:
        return

    buckets = defaultdict(list)
    for r in rows:
        side = 'official' if r['authority_tier'] in OFFICIAL_TIERS else 'voice'
        buckets[(r['country_iso'], side)].append(r)

    client = _client()
    merged_total = 0
    quarantined = []
    for (iso, side), members in sorted(buckets.items()):
        if len(members) < 2:
            continue
        texts = [(m['statement_en'] or m['statement_zh'])[:1500] for m in members]
        emb = _embed_all(client, texts)
        sim = emb @ emb.T
        uf = _UnionFind([m['id'] for m in members])
        idx = {i: m['id'] for i, m in enumerate(members)}
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                if sim[i, j] >= args.threshold:
                    uf.union(idx[i], idx[j])

        clusters = defaultdict(list)
        for m in members:
            clusters[uf.find(m['id'])].append(m)
        for cl in clusters.values():
            if len(cl) < 2:
                continue
            spread = max(m['stance'] for m in cl) - min(m['stance'] for m in cl)
            if spread > args.quarantine_spread:
                quarantined.append((iso, side, [m['id'] for m in cl], spread))
                continue
            rep = _pick_representative(cl)
            dupes = [m for m in cl if m['id'] != rep['id']]
            print(f"  [{iso}/{side}] cluster of {len(cl)} -> rep {rep['id']} "
                  f"(stance {rep['stance']:+.2f}): merging {[m['id'] for m in dupes]}")
            if args.apply:
                for m in dupes:
                    conn.execute("""
                        UPDATE diplomacy_statements
                        SET approval_status='merged', merged_into_id=?,
                            reviewed_at=?, reviewed_by=?
                        WHERE id=?
                    """, (rep['id'], datetime.now(timezone.utc).isoformat(),
                          tag, m['id']))
            merged_total += len(dupes)

    repointed = _flatten_chains(conn, args.apply)
    if args.apply:
        conn.commit()
    conn.close()

    verb = 'Merged' if args.apply else 'Would merge'
    print(f"\n=== {verb} {merged_total} row(s); {repointed} chain repoint(s); "
          f"{len(quarantined)} cluster(s) quarantined (spread > "
          f"{args.quarantine_spread}) ===")
    for iso, side, ids, spread in quarantined:
        print(f"  quarantined [{iso}/{side}] ids={ids} spread={spread:.2f}")
    if args.apply:
        print(f"Revert: UPDATE diplomacy_statements SET approval_status='approved', "
              f"merged_into_id=NULL, reviewed_at=NULL, reviewed_by=NULL "
              f"WHERE reviewed_by='{tag}';")


if __name__ == '__main__':
    main()
