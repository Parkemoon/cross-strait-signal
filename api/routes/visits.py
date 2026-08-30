"""Cross-strait visits tracker endpoints (Phase 2f).

Surfaces `cross_strait_visits` — publicly reported official- / party-level
visits, meetings and exchanges between Taiwan and the mainland (incl. HK /
Macao). Cross-strait scope ONLY by design: Taiwan↔third-country travel is
the diplomacy axis. See `db/migrations/0010_cross_strait_visits.sql`.

Editorial-gate pattern identical to diplomacy_statements: rows land
`pending`, public reads show `approved` only, admin routes are gated by
`Depends(require_admin)`, and the shared review_queue primitives own the
state machine. No auto-merge — several articles on one trip yield several
candidates the analyst folds together with /merge.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import require_admin
from api.database import db_conn
from api.review_queue import approve_row, dismiss_row, merge_row

router = APIRouter(prefix="/api/visits", tags=["visits"])

_VISIBLE_ARTICLE = (
    "a.is_hidden = 0 AND ("
    "ai.id IS NULL "
    "OR (a.analyst_approved = 1 AND (ai.needs_human_review = 0 OR ai.review_resolved = 1))"
    ")"
)

# Enums — MUST mirror scraper/processors/visits_extract.py (api/ does not
# import scraper/).
TW_AFFILIATIONS = {'DPP', 'KMT', 'TPP', 'NPP', 'PFP', 'NP', 'TW_OTHER_PARTY',
                   'TW_GOV', 'SEF', 'TW_LEGISLATURE', 'TW_LOCAL', 'TW_IND'}
PRC_AFFILIATIONS = {'CCP', 'TAO', 'ARATS', 'PRC_GOV', 'PRC_LOCAL', 'HKMO_GOV', 'PRC_OTHER'}
AFFILIATIONS = TW_AFFILIATIONS | PRC_AFFILIATIONS
LEVELS = {'head_of_state_govt', 'party_leader', 'party_senior', 'minister', 'legislator',
          'local_executive', 'local_official', 'youth_delegation', 'delegation', 'other'}
DIRECTIONS = {'TW_TO_PRC', 'PRC_TO_TW', 'THIRD_VENUE'}
STATUSES = {'reported', 'planned', 'rumoured', 'cancelled', 'blocked'}

_EFFECTIVE_DATE = "COALESCE(v.start_date, date(a.published_at))"

_COLS = f"""
    v.id, v.direction, v.visit_status,
    v.visitor_name_en, v.visitor_name_zh, v.visitor_title, v.visitor_affiliation,
    v.visitor_side, v.visitor_figure_id, v.visit_level, v.delegation_desc_en,
    v.counterpart_name_en, v.counterpart_name_zh, v.counterpart_title,
    v.counterpart_affiliation, v.counterpart_figure_id,
    v.event_name_en, v.event_name_zh, v.location_label,
    v.start_date, v.end_date, v.purpose_en, v.quote_zh, v.confidence,
    v.approval_status, v.created_at,
    {_EFFECTIVE_DATE} AS effective_date,
    a.id AS article_id, a.url AS article_url, a.title_original, a.title_en,
    a.published_at, s.name AS source_name, s.bias AS source_bias
"""

_FROM = """
    FROM cross_strait_visits v
    JOIN articles a ON a.id = v.article_id
    JOIN sources s ON s.id = a.source_id
    LEFT JOIN ai_analysis ai ON ai.article_id = a.id
"""


def _shape(row) -> dict:
    d = dict(row)
    d["article"] = {
        "id":             d.pop("article_id", None),
        "url":            d.pop("article_url", None),
        "title_original": d.pop("title_original", None),
        "title_en":       d.pop("title_en", None),
        "published_at":   d.pop("published_at", None),
        "source_name":    d.pop("source_name", None),
        "source_bias":    d.pop("source_bias", None),
    }
    return d


def _window(days: int, start: Optional[str], end: Optional[str]):
    if start or end:
        return start or "0000-01-01", end or "9999-12-31"
    today = date.today()
    return (today - timedelta(days=days)).isoformat(), today.isoformat()


# ── Public reads ─────────────────────────────────────────────────────────

@router.get("/list")
def list_visits(
    days: int = Query(365, ge=1, le=3660),
    start: Optional[str] = None,
    end: Optional[str] = None,
    direction: Optional[str] = None,
    affiliation: Optional[str] = None,
    side: Optional[str] = Query(None, description="visitor side: TW | PRC"),
    level: Optional[str] = None,
    status: Optional[str] = Query(None, description="visit_status"),
    figure: Optional[str] = Query(None, description="visitor_figure_id"),
    limit: int = Query(500, ge=1, le=2000),
):
    """Approved visits, newest first, on the effective date (start_date, else
    the article's published date). Filters are exact-match enums."""
    if direction and direction not in DIRECTIONS:
        raise HTTPException(400, f"direction must be one of {sorted(DIRECTIONS)}")
    if affiliation and affiliation not in AFFILIATIONS:
        raise HTTPException(400, "unknown affiliation")
    if side and side not in ('TW', 'PRC'):
        raise HTTPException(400, "side must be TW or PRC")
    if level and level not in LEVELS:
        raise HTTPException(400, "unknown level")
    if status and status not in STATUSES:
        raise HTTPException(400, "unknown status")

    lo, hi = _window(days, start, end)
    where = [f"v.approval_status = 'approved'", _VISIBLE_ARTICLE, f"{_EFFECTIVE_DATE} BETWEEN ? AND ?"]
    args: list = [lo, hi]
    for col, val in (("v.direction", direction), ("v.visitor_affiliation", affiliation),
                     ("v.visitor_side", side), ("v.visit_level", level),
                     ("v.visit_status", status), ("v.visitor_figure_id", figure)):
        if val:
            where.append(f"{col} = ?")
            args.append(val)
    sql = f"SELECT {_COLS} {_FROM} WHERE {' AND '.join(where)} ORDER BY effective_date DESC, v.id DESC LIMIT ?"
    with db_conn() as conn:
        rows = conn.execute(sql, args + [limit]).fetchall()
    return {"start": lo, "end": hi, "count": len(rows), "visits": [_shape(r) for r in rows]}


@router.get("/summary")
def summary(days: int = Query(90, ge=7, le=3660)):
    """KPI strip: counts by direction / status this window vs the previous
    one, affiliation breakdown, most frequent visitors, coverage bounds."""
    today = date.today()
    start = today - timedelta(days=days)
    prev_start = start - timedelta(days=days)
    base = f"{_FROM} WHERE v.approval_status = 'approved' AND {_VISIBLE_ARTICLE}"

    def counts(lo: date, hi: date):
        rows = conn.execute(
            f"""SELECT v.direction, v.visit_status, COUNT(*) AS n {base}
                AND {_EFFECTIVE_DATE} > ? AND {_EFFECTIVE_DATE} <= ?
                GROUP BY v.direction, v.visit_status""",
            (lo.isoformat(), hi.isoformat())).fetchall()
        out = {"total": 0, "by_direction": {}, "by_status": {}}
        for r in rows:
            out["total"] += r["n"]
            out["by_direction"][r["direction"]] = out["by_direction"].get(r["direction"], 0) + r["n"]
            out["by_status"][r["visit_status"]] = out["by_status"].get(r["visit_status"], 0) + r["n"]
        return out

    with db_conn() as conn:
        cur = counts(start, today)
        prev = counts(prev_start, start)
        aff = conn.execute(
            f"""SELECT v.visitor_affiliation AS affiliation, v.visitor_side AS side, COUNT(*) AS n {base}
                AND {_EFFECTIVE_DATE} > ? GROUP BY 1, 2 ORDER BY n DESC""",
            (start.isoformat(),)).fetchall()
        top = conn.execute(
            f"""SELECT COALESCE(v.visitor_figure_id, v.visitor_name_en, v.visitor_name_zh) AS key,
                       MAX(v.visitor_name_en) AS name_en, MAX(v.visitor_name_zh) AS name_zh,
                       MAX(v.visitor_title) AS title, v.visitor_affiliation AS affiliation,
                       v.visitor_figure_id AS figure_id, COUNT(*) AS n,
                       MAX({_EFFECTIVE_DATE}) AS last_date
                {base} AND {_EFFECTIVE_DATE} > ?
                GROUP BY key, v.visitor_affiliation ORDER BY n DESC, last_date DESC LIMIT 8""",
            ((today - timedelta(days=365)).isoformat(),)).fetchall()
        bounds = conn.execute(
            f"SELECT MIN({_EFFECTIVE_DATE}) AS first, MAX({_EFFECTIVE_DATE}) AS last, COUNT(*) AS n {base}"
        ).fetchone()
    return {
        "days": days, "window_start": start.isoformat(), "as_of": today.isoformat(),
        "current": cur, "previous": prev,
        "by_affiliation": [dict(r) for r in aff],
        "frequent_visitors": [dict(r) for r in top],
        "coverage": dict(bounds) if bounds else None,
    }


@router.get("/monthly")
def monthly(months: int = Query(24, ge=1, le=120)):
    """Per-month visit counts by direction for the bar chart. Blocked and
    cancelled visits are counted separately so the bars stay honest."""
    first_month = (date.today().replace(day=1) - timedelta(days=31 * (months - 1))).strftime("%Y-%m")
    with db_conn() as conn:
        rows = conn.execute(
            f"""SELECT substr({_EFFECTIVE_DATE}, 1, 7) AS month, v.direction,
                       SUM(CASE WHEN v.visit_status IN ('cancelled','blocked') THEN 0 ELSE 1 END) AS n,
                       SUM(CASE WHEN v.visit_status IN ('cancelled','blocked') THEN 1 ELSE 0 END) AS n_blocked
                {_FROM} WHERE v.approval_status = 'approved' AND {_VISIBLE_ARTICLE}
                AND substr({_EFFECTIVE_DATE}, 1, 7) >= ?
                GROUP BY month, v.direction ORDER BY month""",
            (first_month,)).fetchall()
    return {"from": first_month, "rows": [dict(r) for r in rows]}


# ── Admin ────────────────────────────────────────────────────────────────

@router.get("/candidates", dependencies=[Depends(require_admin)])
def candidates(limit: int = Query(300, ge=1, le=2000)):
    """Pending rows newest first, plus recent approved rows the analyst can
    merge duplicates into. No VISIBLE filter — analysts review before the
    article is approved."""
    with db_conn() as conn:
        pend = conn.execute(
            f"SELECT {_COLS} {_FROM} WHERE v.approval_status = 'pending' "
            f"ORDER BY effective_date DESC, v.id DESC LIMIT ?", (limit,)).fetchall()
        targets = conn.execute(
            f"""SELECT v.id, v.direction, v.visitor_name_en, v.visitor_name_zh, v.visitor_affiliation,
                       v.event_name_en, v.location_label, {_EFFECTIVE_DATE} AS effective_date
                {_FROM} WHERE v.approval_status = 'approved'
                AND {_EFFECTIVE_DATE} >= ? ORDER BY effective_date DESC LIMIT 400""",
            ((date.today() - timedelta(days=365)).isoformat(),)).fetchall()
    return {"total": len(pend), "candidates": [_shape(r) for r in pend],
            "merge_targets": [dict(r) for r in targets]}


@router.get("/candidates/count", dependencies=[Depends(require_admin)])
def candidates_count():
    with db_conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM cross_strait_visits WHERE approval_status = 'pending'").fetchone()[0]
    return {"pending": n}


@router.post("/{visit_id}/approve", dependencies=[Depends(require_admin)])
def approve(visit_id: int):
    with db_conn() as conn:
        result = approve_row(conn, "cross_strait_visits", "visit", visit_id)
        conn.commit()
    return result


@router.post("/{visit_id}/dismiss", dependencies=[Depends(require_admin)])
def dismiss(visit_id: int):
    with db_conn() as conn:
        result = dismiss_row(conn, "cross_strait_visits", "visit", visit_id)
        conn.commit()
    return result


class MergeRequest(BaseModel):
    target_id: int
    reviewed_by: Optional[str] = None


@router.post("/{visit_id}/merge", dependencies=[Depends(require_admin)])
def merge(visit_id: int, body: MergeRequest):
    with db_conn() as conn:
        result = merge_row(conn, "cross_strait_visits", "visit", visit_id, body.target_id, body.reviewed_by)
        conn.commit()
    return result


class VisitPatch(BaseModel):
    direction: Optional[str] = None
    visit_status: Optional[str] = None
    visitor_name_en: Optional[str] = None
    visitor_name_zh: Optional[str] = None
    visitor_title: Optional[str] = None
    visitor_affiliation: Optional[str] = None
    visit_level: Optional[str] = None
    delegation_desc_en: Optional[str] = None
    counterpart_name_en: Optional[str] = None
    counterpart_name_zh: Optional[str] = None
    counterpart_title: Optional[str] = None
    counterpart_affiliation: Optional[str] = None
    event_name_en: Optional[str] = None
    event_name_zh: Optional[str] = None
    location_label: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    purpose_en: Optional[str] = None


@router.patch("/{visit_id}", dependencies=[Depends(require_admin)])
def patch(visit_id: int, body: VisitPatch):
    """Analyst edits — only fields present in the body change. Enums are
    validated; visitor_side is recomputed from visitor_affiliation so the
    scope gate can't be edited away."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "empty patch")
    for k, allowed in (("direction", DIRECTIONS), ("visit_status", STATUSES), ("visit_level", LEVELS),
                       ("visitor_affiliation", AFFILIATIONS)):
        if k in fields and fields[k] not in allowed:
            raise HTTPException(400, f"{k} must be one of {sorted(allowed)}")
    if "counterpart_affiliation" in fields and fields["counterpart_affiliation"] not in (None, "") \
            and fields["counterpart_affiliation"] not in AFFILIATIONS:
        raise HTTPException(400, "unknown counterpart_affiliation")
    for k in ("start_date", "end_date"):
        if k in fields and fields[k]:
            try:
                date.fromisoformat(fields[k])
            except ValueError:
                raise HTTPException(400, f"{k} must be YYYY-MM-DD")
    if "visitor_affiliation" in fields:
        fields["visitor_side"] = "TW" if fields["visitor_affiliation"] in TW_AFFILIATIONS else "PRC"
    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = [(v if v != "" else None) for v in fields.values()]
    with db_conn() as conn:
        if not conn.execute("SELECT 1 FROM cross_strait_visits WHERE id = ?", (visit_id,)).fetchone():
            raise HTTPException(404, f"visit {visit_id} not found")
        conn.execute(f"UPDATE cross_strait_visits SET {sets} WHERE id = ?", vals + [visit_id])
        conn.commit()
        row = conn.execute(f"SELECT {_COLS} {_FROM} WHERE v.id = ?", (visit_id,)).fetchone()
    return _shape(row)
