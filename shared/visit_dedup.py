"""Pre-queue dedup for cross_strait_visits, shared by the pipeline step
(scripts/run_pipeline.py, after Step 3e) and the sweep CLI
(scripts/dedup_visits.py).

A single trip generates one candidate row per article that covers it —
the 2026-08-30 staging backfill produced 495 pending rows for ONE
Cheng Li-wun mainland trip (every outlet covered it daily, in both
script variants 鄭麗文/郑丽文). The analyst queue is unusable without a
collapse, and the queue's manual merge picker is for the residual, not
the bulk.

Deterministic, no AI. A cluster is:

  same direction
  + same visitor  (visitor_figure_id when set — which also folds
                   simplified/traditional script variants, both map to
                   one figure — else the lowercased en name, preferred
                   over the zh name because romanisation is
                   script-agnostic and meets 張榮恭/张荣恭 rows that
                   lack a figure id; else the normalised zh name /
                   delegation description)
  + a date CHAIN: rows sorted by effective date join the cluster while
    the gap to the previous row is <= gap_days (21, matching the review
    queue's merge-picker window). Two genuine trips by the same person
    months apart stay separate; a fortnight of rolling coverage of one
    trip collapses.

Location is deliberately NOT a cluster key: one trip's labels run
"Beijing" / "Mainland China" / "Nanjing, Shanghai, Beijing" (multi-leg),
and bucketing on a noisy field splits real duplicates (the standing
dedup rule — see the dedup-aggression memory).

The keeper is the richest row; approved rows always anchor their
cluster (analyst judgement outranks richness) and are NEVER marked as
duplicates themselves. Pending duplicates get approval_status='merged',
merged_into_id=keeper, reviewed_by='dedup:visits' — same shape the
queue's manual merge writes, so nothing downstream tells them apart.
"""
from __future__ import annotations

from datetime import date

GAP_DAYS = 21

# Later-truth statuses outrank earlier-stage ones: a trip that ended up
# cancelled/blocked must keep that row as the cluster's face even when a
# 'planned' row carries more fields.
STATUS_RANK = {'cancelled': 4, 'blocked': 4, 'reported': 3, 'planned': 2, 'rumoured': 1}

# location_label values that identify no actual place — a row with one of
# these is poorer than a row saying "Nanjing".
GENERIC_LOCATIONS = {'china', 'mainland china', 'the mainland', 'prc', 'taiwan', 'unknown'}


def visitor_key(row) -> str:
    """Cluster identity: direction + the strongest available visitor id."""
    who = (row['visitor_figure_id']
           or (row['visitor_name_en'] or '').strip().lower()
           or ''.join((row['visitor_name_zh'] or '').split())
           or (row['delegation_desc_en'] or '').strip().lower())
    return f"{row['direction']}|{who}"


def _eff_date(row) -> date:
    return date.fromisoformat(str(row['effective_date'])[:10])


def cluster_visits(rows, gap_days: int = GAP_DAYS):
    """Group rows (dict-like, incl. an `effective_date`) into per-trip
    clusters: same visitor_key, chained while consecutive effective dates
    are <= gap_days apart. Returns a list of lists (singletons included)."""
    by_key: dict[str, list] = {}
    for r in rows:
        by_key.setdefault(visitor_key(r), []).append(r)

    clusters = []
    for group in by_key.values():
        group.sort(key=lambda r: (_eff_date(r), r['id']))
        chain = [group[0]]
        for r in group[1:]:
            if (_eff_date(r) - _eff_date(chain[-1])).days <= gap_days:
                chain.append(r)
            else:
                clusters.append(chain)
                chain = [r]
        clusters.append(chain)
    return clusters


def _field_count(row) -> int:
    n = 0
    for k in ('start_date', 'end_date', 'visitor_title', 'visitor_figure_id',
              'counterpart_title', 'counterpart_affiliation', 'counterpart_figure_id',
              'delegation_desc_en', 'purpose_en', 'quote_zh'):
        n += bool(row[k])
    n += bool(row['counterpart_name_en'] or row['counterpart_name_zh'])
    n += bool(row['event_name_en'] or row['event_name_zh'])
    loc = (row['location_label'] or '').strip().lower()
    n += bool(loc and loc not in GENERIC_LOCATIONS)
    return n


def richness(row):
    """Sort key for the keeper: analyst approval, then latest-truth status,
    then field richness, extraction confidence, purpose length; lowest id
    (the earliest insert) breaks ties for idempotency."""
    return (
        1 if row['approval_status'] == 'approved' else 0,
        STATUS_RANK.get(row['visit_status'], 0),
        _field_count(row),
        row['confidence'] or 0.0,
        len(row['purpose_en'] or ''),
        -row['id'],
    )


def plan_dedup(rows, gap_days: int = GAP_DAYS):
    """Cluster + pick keepers. Returns a list of
    {keeper, dupes, span:(first,last), n} — clusters that need no write
    (singletons, or nothing pending beside the keeper) are omitted.
    Only PENDING rows are ever listed as dupes; a second approved row in
    the same cluster is left alone (two analyst-approved rows are the
    analyst's call to merge, not ours)."""
    out = []
    for cluster in cluster_visits(rows, gap_days):
        if len(cluster) < 2:
            continue
        keeper = max(cluster, key=richness)
        dupes = [r for r in cluster
                 if r['id'] != keeper['id'] and r['approval_status'] == 'pending']
        if not dupes:
            continue
        dates = sorted(_eff_date(r) for r in cluster)
        out.append({'keeper': keeper, 'dupes': dupes,
                    'span': (dates[0].isoformat(), dates[-1].isoformat()),
                    'n': len(cluster)})
    return out


SELECT_SQL = """
    SELECT v.id, v.direction, v.visit_status, v.visitor_name_en, v.visitor_name_zh,
           v.visitor_title, v.visitor_affiliation, v.visitor_figure_id,
           v.delegation_desc_en, v.counterpart_name_en, v.counterpart_name_zh,
           v.counterpart_title, v.counterpart_affiliation, v.counterpart_figure_id,
           v.event_name_en, v.event_name_zh, v.location_label,
           v.start_date, v.end_date, v.purpose_en, v.quote_zh, v.confidence,
           v.approval_status,
           COALESCE(v.start_date, date(a.published_at)) AS effective_date
    FROM cross_strait_visits v
    JOIN articles a ON a.id = v.article_id
    WHERE v.approval_status IN ('pending', 'approved')
      AND COALESCE(v.start_date, date(a.published_at)) >= ?
"""


def dedup_visits(conn, days: int | None = None, gap_days: int = GAP_DAYS,
                 apply: bool = False, log=print):
    """Load pending+approved rows (optionally windowed on the effective
    date), plan, and — with apply — mark pending duplicates merged into
    their keeper. Returns (n_clusters, n_merged). Caller owns the
    connection; this commits only when it wrote something."""
    since = '0001-01-01'
    if days is not None:
        from datetime import timedelta
        since = (date.today() - timedelta(days=days)).isoformat()
    rows = [dict(r) for r in conn.execute(SELECT_SQL, (since,)).fetchall()]
    plans = plan_dedup(rows, gap_days)
    merged = 0
    for p in plans:
        k = p['keeper']
        log(f"  {p['span'][0]}..{p['span'][1]}  {k['direction']}  "
            f"{k['visitor_name_en'] or k['visitor_name_zh'] or k['delegation_desc_en'] or '?'}: "
            f"{p['n']} rows -> keep #{k['id']} ({k['approval_status']}, {k['visit_status']}, "
            f"{k['location_label'] or 'no location'}), merge {len(p['dupes'])}")
        if apply:
            ids = [r['id'] for r in p['dupes']]
            conn.executemany(
                """UPDATE cross_strait_visits
                   SET approval_status='merged', merged_into_id=?,
                       reviewed_at=datetime('now'), reviewed_by='dedup:visits'
                   WHERE id=? AND approval_status='pending'""",
                [(k['id'], i) for i in ids])
        merged += len(p['dupes'])
    if apply and merged:
        conn.commit()
    log(f"  {'Merged' if apply else 'Would merge'} {merged} duplicate rows across {len(plans)} trips.")
    return len(plans), merged
