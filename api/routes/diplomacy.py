"""Diplomacy Tracker endpoints (Phase 2c).

Surfaces the `diplomacy_statements` table — third-country stances on the
Taiwan / cross-strait / one-China question, an axis SEPARATE from the core
cross-strait sentiment instrument (which deliberately discards third-party
interactions). See `db/schema.sql` (`diplomacy_statements`) for column
semantics and the two-layer map design (official-tier FILL + non-official
PINS).

Editorial-gate pattern, identical to military_exercises / polls: candidates
land `pending` and are hidden from the public read routes until an analyst
approves them. Admin routes are gated by `Depends(require_admin)`.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import require_admin
from api.review_queue import approve_row, dismiss_row, merge_row
from api.database import db_conn

router = APIRouter(prefix="/api/diplomacy", tags=["diplomacy"])

# Same relaxed VISIBLE predicate the military/exercise routes use: an
# article with no ai_analysis row is treated as visible (defence in depth —
# diplomacy rows always have a backing analysed article today, but the
# LEFT JOIN keeps us consistent and future-proof).
_VISIBLE_ARTICLE = (
    "a.is_hidden = 0 AND ("
    "ai.id IS NULL "
    "OR (a.analyst_approved = 1 AND (ai.needs_human_review = 0 OR ai.review_resolved = 1))"
    ")"
)

_VALID_TIERS = {
    'government', 'head_of_state', 'ruling_party', 'legislator',
    'subnational', 'former_official', 'other',
}
# Tiers that drive the country FILL = honest official national posture.
# Everything else renders as a pin on top.
_OFFICIAL_TIERS = ('government', 'head_of_state')
_VALID_SIDES = {'TW', 'PRC', 'INTL'}
_VALID_STATUSES = {'pending', 'approved', 'dismissed', 'merged'}

# Stance neutral half-band — a statement within ±_NEUTRAL_BAND is "neutral"
# and never counts toward a pro-Taipei / pro-Beijing divergence.
_NEUTRAL_BAND = 0.2


def _stance_label(stance: float) -> str:
    """Bucket a -1..+1 stance into the five fill bands. MUST mirror
    scraper.processors.ai_pipeline._stance_label — duplicated rather than
    imported because api/ does not depend on scraper/."""
    if stance >= 0.6:
        return 'pro_taipei'
    if stance >= 0.2:
        return 'leaning_taipei'
    if stance > -0.2:
        return 'neutral'
    if stance > -0.6:
        return 'leaning_beijing'
    return 'pro_beijing'


_PUBLIC_COLS = """
    d.id, d.country_iso, d.country_name, d.speaker, d.authority_tier,
    d.stance, d.stance_label, d.statement_en, d.statement_zh,
    d.stated_date, d.source_side, d.confidence,
    COALESCE(d.stated_date, date(a.published_at)) AS effective_date,
    a.id AS article_id, a.url AS article_url, a.published_at,
    s.name AS source_name, s.bias AS source_bias
"""


def _row_to_statement(row) -> dict:
    """Shape a statement row for JSON, nesting the article join."""
    d = dict(row)
    d["article"] = {
        "id":           d.pop("article_id", None),
        "url":          d.pop("article_url", None),
        "published_at": d.pop("published_at", None),
        "source_name":  d.pop("source_name", None),
        "source_bias":  d.pop("source_bias", None),
    }
    return d


# ── Public reads ─────────────────────────────────────────────────────────

@router.get("/statements")
def statements(
    days: int = Query(365, ge=1, le=3650, description="Trailing window in days (on effective date)."),
    start: Optional[str] = Query(None, description="ISO start date (overrides `days`)."),
    end:   Optional[str] = Query(None, description="ISO end date (defaults to today)."),
    country: Optional[str] = Query(None, description="ISO 3166-1 alpha-2 country code filter."),
    tier: Optional[str] = Query(None, description="authority_tier filter."),
    side: Optional[str] = Query(None, description="source_side filter: TW|PRC|INTL."),
    official_only: bool = Query(False, description="If true, only official-tier (government/head_of_state) statements."),
    limit: int = Query(500, ge=1, le=2000),
):
    """Approved statements for the map pins + list. `merged`/`dismissed`/
    `pending` rows never appear. Window is on the effective date
    (stated_date, falling back to the article's published date)."""
    end_d = date.fromisoformat(end) if end else date.today()
    start_d = date.fromisoformat(start) if start else end_d - timedelta(days=days - 1)

    clauses = [
        "d.approval_status = 'approved'",
        _VISIBLE_ARTICLE,
        "COALESCE(d.stated_date, date(a.published_at)) BETWEEN :start_d AND :end_d",
    ]
    params = {"start_d": start_d.isoformat(), "end_d": end_d.isoformat(), "limit": limit}

    if country:
        clauses.append("d.country_iso = :country")
        params["country"] = country.strip().upper()
    if tier and tier in _VALID_TIERS:
        clauses.append("d.authority_tier = :tier")
        params["tier"] = tier
    if side and side.strip().upper() in _VALID_SIDES:
        clauses.append("d.source_side = :side")
        params["side"] = side.strip().upper()
    if official_only:
        clauses.append("d.authority_tier IN ('government', 'head_of_state')")

    sql = f"""
        SELECT {_PUBLIC_COLS}
        FROM diplomacy_statements d
        JOIN articles a ON d.article_id = a.id
        JOIN sources s ON s.id = a.source_id
        LEFT JOIN ai_analysis ai ON ai.article_id = a.id
        WHERE {' AND '.join(clauses)}
        ORDER BY COALESCE(d.stated_date, date(a.published_at)) DESC, d.id DESC
        LIMIT :limit
    """
    with db_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    return {
        "start": start_d.isoformat(),
        "end":   end_d.isoformat(),
        "rows":  [_row_to_statement(r) for r in rows],
    }


@router.get("/map")
def country_map(
    stale_days: int = Query(730, ge=30, le=3650,
                            description="Only consider statements within this window for fill/pins."),
):
    """Per-country view for the choropleth. FILL = the AGGREGATE (mean) stance
    of a country's official-tier (government / head_of_state) approved
    statements within `stale_days` = honest national posture, robust to a
    single stray row; `official_count` exposes the sample size and the latest
    official's tier/date is a freshness hint (full statements come from
    /statements). Countries with only non-official statements get `fill: null`
    but still carry voices. Each country also reports `pins_count` /
    `pins_stance` / `pins_label` — the count and aggregate stance of its
    non-official voices, which drive the map's voices-pin layer. `divergent`
    flags the headline feature: a non-official voice whose stance opposes the
    official fill (e.g. a supportive legislator delegation under a one-China
    government)."""
    cutoff = (date.today() - timedelta(days=stale_days - 1)).isoformat()
    sql = f"""
        SELECT {_PUBLIC_COLS}
        FROM diplomacy_statements d
        JOIN articles a ON d.article_id = a.id
        JOIN sources s ON s.id = a.source_id
        LEFT JOIN ai_analysis ai ON ai.article_id = a.id
        WHERE d.approval_status = 'approved'
          AND {_VISIBLE_ARTICLE}
          AND COALESCE(d.stated_date, date(a.published_at)) >= :cutoff
        ORDER BY d.country_iso ASC,
                 COALESCE(d.stated_date, date(a.published_at)) DESC, d.id DESC
    """
    with db_conn() as conn:
        rows = [_row_to_statement(r) for r in conn.execute(sql, {"cutoff": cutoff}).fetchall()]

    # Group by country in Python (rows already sorted newest-first per
    # country, so the first official row we see is the latest = the fill).
    by_country: dict = {}
    for r in rows:
        by_country.setdefault(r["country_iso"], []).append(r)

    countries = []
    for iso, stmts in by_country.items():
        official = [s for s in stmts if s["authority_tier"] in _OFFICIAL_TIERS]
        pins = [s for s in stmts if s["authority_tier"] not in _OFFICIAL_TIERS]

        # FILL = the AGGREGATE (mean) stance of the country's official-tier
        # statements in the window, so one stray row (e.g. a PRC-source
        # paraphrase of a third country) can't define a major power on its
        # own. The latest official is kept as the representative quote;
        # `official_count` exposes how many statements back the average.
        fill = None
        if official:
            agg = sum(s["stance"] for s in official) / len(official)
            rep = official[0]  # latest official — drives the "last updated" hint
            fill = {
                "stance":         round(agg, 3),
                "stance_label":   _stance_label(agg),
                "official_count": len(official),
                "authority_tier": rep["authority_tier"],
                "effective_date": rep["effective_date"],
            }

        # Divergence: a non-official voice pulling across neutral from the
        # aggregate official posture.
        divergent = False
        if fill and fill["stance"] <= -_NEUTRAL_BAND:
            divergent = any(s["stance"] >= _NEUTRAL_BAND for s in pins)
        elif fill and fill["stance"] >= _NEUTRAL_BAND:
            divergent = any(s["stance"] <= -_NEUTRAL_BAND for s in pins)

        # Aggregate of the non-official voices — drives the colour of the
        # voices-pin layer (so a green pin can sit on a red fill = divergence).
        pins_mean = (sum(s["stance"] for s in pins) / len(pins)) if pins else None

        countries.append({
            "country_iso":  iso,
            "country_name": stmts[0]["country_name"],
            "fill":         fill,
            "pins_count":   len(pins),
            "pins_stance":  round(pins_mean, 3) if pins_mean is not None else None,
            "pins_label":   _stance_label(pins_mean) if pins_mean is not None else None,
            "total_count":  len(stmts),
            "divergent":    divergent,
        })

    countries.sort(key=lambda c: c["country_iso"])
    return {"stale_days": stale_days, "as_of": date.today().isoformat(), "countries": countries}


@router.get("/summary")
def summary(stale_days: int = Query(730, ge=30, le=3650)):
    """KPI strip: fill-band breakdown, divergent-country count, latest."""
    data = country_map(stale_days=stale_days)
    bands = {"pro_taipei": 0, "leaning_taipei": 0, "neutral": 0,
             "leaning_beijing": 0, "pro_beijing": 0, "none": 0}
    divergent = 0
    for c in data["countries"]:
        if c["fill"]:
            bands[c["fill"]["stance_label"]] += 1
        else:
            bands["none"] += 1
        if c["divergent"]:
            divergent += 1

    with db_conn() as conn:
        latest = conn.execute(f"""
            SELECT {_PUBLIC_COLS}
            FROM diplomacy_statements d
            JOIN articles a ON d.article_id = a.id
            JOIN sources s ON s.id = a.source_id
            LEFT JOIN ai_analysis ai ON ai.article_id = a.id
            WHERE d.approval_status = 'approved' AND {_VISIBLE_ARTICLE}
            ORDER BY COALESCE(d.stated_date, date(a.published_at)) DESC, d.id DESC
            LIMIT 1
        """).fetchone()

    return {
        "as_of":             data["as_of"],
        "countries_tracked": len([c for c in data["countries"] if c["fill"]]),
        "by_band":           bands,
        "divergent_count":   divergent,
        "latest":            _row_to_statement(latest) if latest else None,
    }


# ── Admin / review queue ─────────────────────────────────────────────────

@router.get("/candidates", dependencies=[Depends(require_admin)])
def candidates():
    """Pending statements awaiting analyst review, grouped by country. No
    VISIBLE filter — analysts review before the article is approved."""
    sql = """
        SELECT d.id, d.country_iso, d.country_name, d.speaker, d.authority_tier,
               d.stance, d.stance_label, d.statement_en, d.statement_zh,
               d.stated_date, d.source_side, d.confidence, d.created_at,
               a.id AS article_id, a.url AS article_url, a.title_original,
               a.published_at, s.name AS source_name, s.bias AS source_bias
        FROM diplomacy_statements d
        JOIN articles a ON d.article_id = a.id
        JOIN sources s ON s.id = a.source_id
        WHERE d.approval_status = 'pending'
        ORDER BY d.country_iso ASC, d.created_at DESC, d.id DESC
    """
    with db_conn() as conn:
        rows = conn.execute(sql).fetchall()

    groups: dict = {}
    for row in rows:
        d = dict(row)
        d["article"] = {
            "id":             d.pop("article_id", None),
            "url":            d.pop("article_url", None),
            "title_original": d.pop("title_original", None),
            "published_at":   d.pop("published_at", None),
            "source_name":    d.pop("source_name", None),
            "source_bias":    d.pop("source_bias", None),
        }
        groups.setdefault(d["country_iso"], []).append(d)

    return {
        "groups": [
            {"country_iso": iso, "country_name": items[0]["country_name"],
             "count": len(items), "statements": items}
            for iso, items in sorted(groups.items())
        ],
        "total": len(rows),
    }


@router.get("/candidates/count", dependencies=[Depends(require_admin)])
def candidates_count():
    """Cheap pending count for the review-button badge — avoids downloading
    the full /candidates payload (thousands of rows) just to show a number."""
    with db_conn() as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM diplomacy_statements WHERE approval_status = 'pending'"
        ).fetchone()[0]
    return {"pending": n}


@router.post("/{statement_id}/approve", dependencies=[Depends(require_admin)])
def approve(statement_id: int):
    """Mark a statement approved for public display. No auto-merge — unlike
    exercises there is no mechanical canonical key, so duplicate collapsing
    is left to the explicit /merge endpoint (analyst judgement)."""
    with db_conn() as conn:
        result = approve_row(conn, "diplomacy_statements", "statement", statement_id)
        conn.commit()
    return result


@router.post("/{statement_id}/dismiss", dependencies=[Depends(require_admin)])
def dismiss(statement_id: int):
    with db_conn() as conn:
        result = dismiss_row(conn, "diplomacy_statements", "statement", statement_id)
        conn.commit()
    return result


class MergeRequest(BaseModel):
    target_id: int
    reviewed_by: Optional[str] = None


@router.post("/{statement_id}/merge", dependencies=[Depends(require_admin)])
def merge(statement_id: int, body: MergeRequest):
    """Fold a duplicate statement into another — shared review-queue state
    machine (api/review_queue.py): target must be 'approved' so the chain
    can't dangle, source must be pending/approved."""
    with db_conn() as conn:
        result = merge_row(conn, "diplomacy_statements", "statement",
                           statement_id, body.target_id, body.reviewed_by)
        conn.commit()
    return result


class StatementPatch(BaseModel):
    country_iso: Optional[str] = None
    country_name: Optional[str] = None
    speaker: Optional[str] = None
    authority_tier: Optional[str] = None
    stance: Optional[float] = None
    statement_en: Optional[str] = None
    statement_zh: Optional[str] = None
    stated_date: Optional[str] = None
    source_side: Optional[str] = None


@router.patch("/{statement_id}", dependencies=[Depends(require_admin)])
def patch(statement_id: int, patch: StatementPatch):
    """Analyst edits. Send only changed fields. `stance_label` is always
    recomputed from the final stance; `authority_tier` / `source_side` are
    validated against their enums; `stance` is clamped to [-1, 1];
    `stated_date` must be ISO yyyy-mm-dd if set."""
    fields = patch.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "no fields to update")

    sets, params = [], {}

    if "country_iso" in fields:
        code = (fields["country_iso"] or "").strip().upper()
        if not code:
            raise HTTPException(400, "country_iso cannot be empty")
        sets.append("country_iso = :country_iso")
        params["country_iso"] = code
    if "country_name" in fields:
        sets.append("country_name = :country_name")
        params["country_name"] = (fields["country_name"] or "").strip() or None
    if "speaker" in fields:
        sets.append("speaker = :speaker")
        params["speaker"] = (fields["speaker"] or "").strip() or None
    if "authority_tier" in fields:
        tier = (fields["authority_tier"] or "").strip().lower()
        if tier not in _VALID_TIERS:
            raise HTTPException(400, f"invalid authority_tier: {tier}")
        sets.append("authority_tier = :authority_tier")
        params["authority_tier"] = tier
    if "stance" in fields and fields["stance"] is not None:
        stance = max(-1.0, min(1.0, float(fields["stance"])))
        sets.append("stance = :stance")
        sets.append("stance_label = :stance_label")
        params["stance"] = stance
        params["stance_label"] = _stance_label(stance)
    if "statement_en" in fields:
        sets.append("statement_en = :statement_en")
        params["statement_en"] = (fields["statement_en"] or "").strip() or None
    if "statement_zh" in fields:
        sets.append("statement_zh = :statement_zh")
        params["statement_zh"] = (fields["statement_zh"] or "").strip() or None
    if "stated_date" in fields:
        sd = (fields["stated_date"] or "").strip() or None
        if sd:
            try:
                date.fromisoformat(sd)
            except ValueError:
                raise HTTPException(400, "stated_date must be YYYY-MM-DD")
        sets.append("stated_date = :stated_date")
        params["stated_date"] = sd
    if "source_side" in fields:
        ss = (fields["source_side"] or "").strip().upper() or None
        if ss and ss not in _VALID_SIDES:
            raise HTTPException(400, f"invalid source_side: {ss}")
        sets.append("source_side = :source_side")
        params["source_side"] = ss

    if not sets:
        raise HTTPException(400, "no valid fields to update")

    params["id"] = statement_id
    with db_conn() as conn:
        row = conn.execute(
            "SELECT id FROM diplomacy_statements WHERE id = ?", (statement_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"statement {statement_id} not found")
        conn.execute(
            f"UPDATE diplomacy_statements SET {', '.join(sets)} WHERE id = :id", params
        )
        conn.commit()
        updated = conn.execute(f"""
            SELECT {_PUBLIC_COLS}
            FROM diplomacy_statements d
            JOIN articles a ON d.article_id = a.id
            JOIN sources s ON s.id = a.source_id
            WHERE d.id = :id
        """, {"id": statement_id}).fetchone()
    return {"status": "updated", "statement": _row_to_statement(updated)}
