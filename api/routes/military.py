"""Military activity endpoints (Phase 2b).

Surfaces the `pla_incursions` table built by `mnd_incursion_scraper.py`
(live) and the one-shot PLATracker backfill. All endpoints coalesce on
(date) preferring source='mnd' over 'platracker_backfill' — MND's wording
gives us the broader 共機架次 + zone breakdown + vessel/coast-guard
counts, whereas PLATracker only carries the intrusion count.

See `db/schema.sql` (`pla_incursions`) for column semantics; in
particular, `aircraft_intruded` covers both 逾越中線 and 進入空域 forms.
"""
from datetime import date, timedelta
import json
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import require_admin
from api.database import db_conn

router = APIRouter(prefix="/api/military", tags=["military"])

# Exercise-tracker visibility predicate. INTENTIONALLY weaker than the
# main-feed VISIBLE predicate (in api/routes/stats.py) because the
# exercise's own approval_status='approved' is itself the editorial gate
# — the analyst reviewed each candidate against its source article before
# approving. We only enforce that the source article hasn't been hidden.
# This also lets exercise-only articles (those rejected by the keyword
# pre-filter in the parallel YDN extraction pass — no ai_analysis row at
# all) surface once their exercises are approved.
_VISIBLE_ARTICLE = "a.is_hidden = 0"

_VALID_PERFORMERS = {'PRC', 'ROC', 'US', 'JP', 'MULTI'}
_VALID_EXERCISE_KINDS = {'live_fire', 'readiness_drill', 'joint_patrol',
                         'named_exercise', 'cyber', 'amphibious', 'other'}

# Mirror of scraper.processors.ai_pipeline._build_exercise_canonical_key —
# kept in sync because api/ cannot import from scraper/ without inverting
# the project's layering. Strip interchangeable trailing nouns so name
# variants like "Formation Drill" / "Formation Exercise" / "Formation
# Training" all collapse to the same canonical key.
_EXERCISE_SUFFIX_RE = re.compile(
    r'\s+(drills?|exercises?|trainings?)$', re.IGNORECASE
)


def _build_exercise_canonical_key(name_en):
    if not name_en:
        return None
    stripped = _EXERCISE_SUFFIX_RE.sub('', name_en.strip())
    key = stripped.lower().replace(' ', '-').replace('_', '-')
    return key or None

ZONE_LABELS = {
    "N":  "North",
    "C":  "Central",
    "SW": "Southwest",
    "SE": "Southeast",
    "E":  "East",
}

# One row per date, with the preferred source (mnd > platracker_backfill).
# Window functions aren't available on all SQLite builds in old prod, but
# the GROUP BY + MIN(source) trick works because 'mnd' < 'platracker_backfill'
# alphabetically — and we explicitly join back on that to fetch the row body.
_DAILY_SQL = """
WITH picked AS (
    SELECT date, MIN(source) AS source
    FROM pla_incursions
    WHERE date >= :start AND date <= :end
    GROUP BY date
)
SELECT
    p.date,
    p.aircraft_total,
    p.aircraft_intruded,
    p.aircraft_zones,
    p.vessels_total,
    p.coast_guard_total,
    p.source,
    p.source_url
FROM pla_incursions p
JOIN picked USING (date, source)
ORDER BY p.date
"""


def _daily_rows(start: str, end: str):
    with db_conn() as conn:
        rows = conn.execute(_DAILY_SQL, {"start": start, "end": end}).fetchall()
    return [dict(r) for r in rows]


@router.get("/incursions")
def incursions(
    days: int = Query(90, ge=1, le=2000, description="Trailing window size in days."),
    start: Optional[str] = Query(None, description="ISO date (overrides `days`)."),
    end:   Optional[str] = Query(None, description="ISO date (defaults to today)."),
):
    """Daily incursion series. Returns one row per date with the preferred
    source's columns. `aircraft_zones` is a comma-separated list of sector
    codes (N/C/SW/SE/E) where MND named them; map codes to labels with
    `/api/military/zones` if needed."""
    end_d = date.fromisoformat(end) if end else date.today()
    start_d = date.fromisoformat(start) if start else end_d - timedelta(days=days - 1)
    return {
        "start": start_d.isoformat(),
        "end":   end_d.isoformat(),
        "rows":  _daily_rows(start_d.isoformat(), end_d.isoformat()),
    }


@router.get("/incursions/monthly")
def incursions_monthly(months: int = Query(48, ge=1, le=240)):
    """Monthly aggregates over the trailing window. Returns aircraft and
    vessel totals plus a per-zone day-count (number of days each sector
    was touched). Coalesces sources per date, then groups."""
    end_d = date.today()
    # Walk back `months` calendar months — first-of-that-month is `start`.
    y, m = end_d.year, end_d.month - (months - 1)
    while m <= 0:
        y -= 1
        m += 12
    start_iso = f"{y:04d}-{m:02d}-01"

    rows = _daily_rows(start_iso, end_d.isoformat())
    # Each field starts as None and is replaced by a running sum the first
    # time a row carries it — so periods where the only source (PLATracker)
    # never published a field surface as null rather than a phantom zero.
    SUMMED_FIELDS = ("aircraft_total", "aircraft_intruded", "vessels_total", "coast_guard_total")
    buckets: dict = {}
    for r in rows:
        key = r["date"][:7]
        b = buckets.setdefault(key, {
            "period": key,
            "days_observed":   0,
            **{f: None for f in SUMMED_FIELDS},
            "zone_day_counts": None,
        })
        b["days_observed"] += 1
        for f in SUMMED_FIELDS:
            if r[f] is not None:
                b[f] = (b[f] or 0) + r[f]
        if r["aircraft_zones"]:
            if b["zone_day_counts"] is None:
                b["zone_day_counts"] = {code: 0 for code in ZONE_LABELS}
            for code in r["aircraft_zones"].split(","):
                code = code.strip()
                if code in b["zone_day_counts"]:
                    b["zone_day_counts"][code] += 1

    return {
        "start": start_iso,
        "end":   end_d.isoformat(),
        "rows":  sorted(buckets.values(), key=lambda b: b["period"]),
    }


@router.get("/incursions/summary")
def incursions_summary():
    """Headline KPIs for the MilitaryTab strip. Returns today, 7-day, 30-day
    rolling averages (of `aircraft_intruded`, the universally-available
    metric), and year-over-year delta on the trailing 30-day window. Also
    reports the latest available date so the UI can flag staleness."""
    today = date.today()

    with db_conn() as conn:
        latest_row = conn.execute(
            "SELECT MAX(date) AS d FROM pla_incursions"
        ).fetchone()
    latest = latest_row["d"] if latest_row else None

    def _window_avg(end_d: date, days: int) -> Optional[float]:
        start = (end_d - timedelta(days=days - 1)).isoformat()
        rows = _daily_rows(start, end_d.isoformat())
        vals = [r["aircraft_intruded"] for r in rows if r["aircraft_intruded"] is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    def _window_rows(end_d: date, days: int):
        start = (end_d - timedelta(days=days - 1)).isoformat()
        return _daily_rows(start, end_d.isoformat())

    today_rows = _daily_rows(today.isoformat(), today.isoformat())
    today_row = today_rows[0] if today_rows else None

    avg_7d = _window_avg(today, 7)
    avg_30d = _window_avg(today, 30)
    avg_30d_ya = _window_avg(today.replace(year=today.year - 1), 30)
    yoy_delta_pct = None
    if avg_30d is not None and avg_30d_ya and avg_30d_ya > 0:
        yoy_delta_pct = round((avg_30d - avg_30d_ya) / avg_30d_ya * 100, 1)

    # "Days with any intrusion this month" — a commonly-cited stat.
    month_start = today.replace(day=1).isoformat()
    month_rows = _daily_rows(month_start, today.isoformat())
    days_with_intrusions = sum(
        1 for r in month_rows
        if (r["aircraft_intruded"] or 0) > 0
    )

    return {
        "latest_date":           latest,
        "today":                 today_row,
        "avg_7d_intruded":       avg_7d,
        "avg_30d_intruded":      avg_30d,
        "avg_30d_year_ago":      avg_30d_ya,
        "yoy_delta_pct":         yoy_delta_pct,
        "days_with_intrusions_mtd": days_with_intrusions,
        "mtd_days_observed":     len(month_rows),
    }


@router.get("/zones")
def zones():
    """Static lookup mapping internal sector codes to display labels."""
    return {"zones": [{"code": k, "label": v} for k, v in ZONE_LABELS.items()]}


# ============================================================
# MILITARY EXERCISES (Phase 2b.2)
# ============================================================
# Editorial-gated exercise tracker — AI-extracted candidates land with
# approval_status='pending' from the Tier 1 pipeline; analyst confirms /
# edits / dismisses / merges through the admin UI. Public endpoints
# hard-filter approval_status='approved' AND join to articles with the
# VISIBLE predicate above — defence in depth.

_EXERCISE_PUBLIC_COLS = """
    e.id, e.canonical_name, e.name_en, e.name_zh, e.name_raw,
    e.performer, e.participants_json, e.exercise_kind,
    e.start_date, e.end_date, e.location_label,
    e.latitude, e.longitude,
    e.description_en, e.description_zh, e.confidence,
    a.id AS article_id, a.url AS article_url, a.published_at,
    s.name AS source_name, s.bias AS source_bias
"""


def _row_to_exercise(row):
    """Shape an exercise row for JSON serialisation. Inflates
    `participants_json` to a list and packages the article join as a nested
    dict so the frontend can read it cleanly."""
    d = dict(row)
    raw_parts = d.pop("participants_json", None)
    try:
        d["participants"] = json.loads(raw_parts) if raw_parts else None
    except (TypeError, ValueError):
        d["participants"] = None
    d["article"] = {
        "id":           d.pop("article_id", None),
        "url":          d.pop("article_url", None),
        "published_at": d.pop("published_at", None),
        "source_name":  d.pop("source_name", None),
        "source_bias":  d.pop("source_bias", None),
    }
    return d


@router.get("/exercises")
def exercises(
    days: int = Query(90, ge=1, le=1000, description="Trailing window in days."),
    start: Optional[str] = Query(None, description="ISO start date (overrides `days`)."),
    end:   Optional[str] = Query(None, description="ISO end date (defaults to today)."),
    performer: Optional[str] = Query(None, description="Comma-separated subset of PRC,ROC,US,JP,MULTI."),
    kind: Optional[str] = Query(None, description="Filter by exercise_kind."),
    with_geo: bool = Query(False, description="If true, return only rows with latitude+longitude set."),
):
    """Approved exercises for the public map + list. Coalesces by the
    `merged_into_id` chain — `merged` and `dismissed` rows never appear.
    Joined article must pass the same VISIBLE predicate the rest of the
    dashboard uses."""
    end_d = date.fromisoformat(end) if end else date.today()
    start_d = date.fromisoformat(start) if start else end_d - timedelta(days=days - 1)

    clauses = [
        "e.approval_status = 'approved'",
        _VISIBLE_ARTICLE,
        # An exercise overlaps the window if EITHER its start_date OR end_date
        # falls inside the window. Rows without a start_date fall back to the
        # source article's published date.
        "(COALESCE(e.start_date, date(a.published_at)) <= :end_d "
        " AND COALESCE(e.end_date, e.start_date, date(a.published_at)) >= :start_d)",
    ]
    params = {"start_d": start_d.isoformat(), "end_d": end_d.isoformat()}

    if performer:
        wanted = [p.strip().upper() for p in performer.split(",") if p.strip()]
        wanted = [p for p in wanted if p in _VALID_PERFORMERS]
        if wanted:
            placeholders = ",".join(f":p{i}" for i in range(len(wanted)))
            clauses.append(f"e.performer IN ({placeholders})")
            for i, p in enumerate(wanted):
                params[f"p{i}"] = p
    if kind and kind in _VALID_EXERCISE_KINDS:
        clauses.append("e.exercise_kind = :kind")
        params["kind"] = kind
    if with_geo:
        clauses.append("e.latitude IS NOT NULL AND e.longitude IS NOT NULL")

    sql = f"""
        SELECT {_EXERCISE_PUBLIC_COLS}
        FROM military_exercises e
        JOIN articles a ON e.article_id = a.id
        JOIN sources s ON s.id = a.source_id
        LEFT JOIN ai_analysis ai ON ai.article_id = a.id
        WHERE {' AND '.join(clauses)}
        ORDER BY COALESCE(e.start_date, date(a.published_at)) DESC, e.id DESC
    """
    with db_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    return {
        "start": start_d.isoformat(),
        "end":   end_d.isoformat(),
        "rows":  [_row_to_exercise(r) for r in rows],
    }


@router.get("/exercises/summary")
def exercises_summary():
    """Headline KPI strip for the EXERCISE TRACKER section: 30-day count,
    breakdown by performer, latest approved exercise."""
    today = date.today()
    start_30 = (today - timedelta(days=29)).isoformat()
    with db_conn() as conn:
        by_performer = conn.execute(f"""
            SELECT e.performer, COUNT(*) AS n
            FROM military_exercises e
            JOIN articles a ON e.article_id = a.id
            LEFT JOIN ai_analysis ai ON ai.article_id = a.id
            WHERE e.approval_status = 'approved'
              AND {_VISIBLE_ARTICLE}
              AND COALESCE(e.start_date, date(a.published_at)) >= :start_30
            GROUP BY e.performer
        """, {"start_30": start_30}).fetchall()

        latest = conn.execute(f"""
            SELECT {_EXERCISE_PUBLIC_COLS}
            FROM military_exercises e
            JOIN articles a ON e.article_id = a.id
            JOIN sources s ON s.id = a.source_id
            LEFT JOIN ai_analysis ai ON ai.article_id = a.id
            WHERE e.approval_status = 'approved' AND {_VISIBLE_ARTICLE}
            ORDER BY COALESCE(e.start_date, date(a.published_at)) DESC, e.id DESC
            LIMIT 1
        """).fetchone()

    counts = {row["performer"]: row["n"] for row in by_performer}
    return {
        "window_start": start_30,
        "window_end":   today.isoformat(),
        "total_30d":    sum(counts.values()),
        "by_performer": {p: counts.get(p, 0) for p in _VALID_PERFORMERS},
        "latest":       _row_to_exercise(latest) if latest else None,
    }


@router.get("/exercises/candidates", dependencies=[Depends(require_admin)])
def exercise_candidates():
    """Pending candidates awaiting analyst review, grouped by canonical_name
    (NULL canonical → '_unnamed_' bucket). No VISIBLE filter — analysts
    need to see candidates regardless of whether the underlying article has
    been approved yet (often the same review pass)."""
    with db_conn() as conn:
        rows = conn.execute(f"""
            SELECT {_EXERCISE_PUBLIC_COLS}, e.created_at AS candidate_created_at,
                   ai.topic_primary
            FROM military_exercises e
            JOIN articles a ON e.article_id = a.id
            JOIN sources s ON s.id = a.source_id
            LEFT JOIN ai_analysis ai ON ai.article_id = a.id
            WHERE e.approval_status = 'pending'
            ORDER BY COALESCE(e.start_date, date(a.published_at)) DESC, e.id DESC
        """).fetchall()

    by_group = {}
    for r in rows:
        ex = _row_to_exercise(r)
        ex["topic_primary"] = r["topic_primary"]
        ex["candidate_created_at"] = r["candidate_created_at"]
        key = ex.get("canonical_name") or "_unnamed_"
        by_group.setdefault(key, []).append(ex)

    return {"candidates": by_group, "total_pending": len(rows)}


@router.post("/exercises/{exercise_id}/approve", dependencies=[Depends(require_admin)])
def approve_exercise(exercise_id: int):
    """Mark an exercise candidate as approved for public display.

    Side effect — auto-merge: any OTHER `pending` candidates with the same
    non-null canonical_name are silently marked as merged into this one,
    collapsing duplicate reports of the same named exercise without the
    analyst having to click Merge on each. Unnamed drills (canonical_name
    NULL) are NOT auto-merged because there's no reliable key — those
    still require manual review per row.
    """
    with db_conn() as conn:
        row = conn.execute(
            "SELECT canonical_name FROM military_exercises WHERE id = ?",
            (exercise_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, f"exercise {exercise_id} not found")

        conn.execute("""
            UPDATE military_exercises
            SET approval_status = 'approved', reviewed_at = datetime('now')
            WHERE id = ?
        """, (exercise_id,))

        auto_merged = 0
        canonical = row["canonical_name"]
        if canonical:
            cur = conn.execute("""
                UPDATE military_exercises
                SET approval_status = 'merged',
                    merged_into_id = :target,
                    reviewed_at = datetime('now')
                WHERE approval_status = 'pending'
                  AND canonical_name = :canonical
                  AND id != :target
            """, {"target": exercise_id, "canonical": canonical})
            auto_merged = cur.rowcount
        conn.commit()
    return {"status": "approved", "id": exercise_id, "auto_merged": auto_merged}


@router.post("/exercises/{exercise_id}/dismiss", dependencies=[Depends(require_admin)])
def dismiss_exercise(exercise_id: int):
    """Mark an exercise candidate as dismissed (not surfaced publicly)."""
    with db_conn() as conn:
        cur = conn.execute("""
            UPDATE military_exercises
            SET approval_status = 'dismissed', reviewed_at = datetime('now')
            WHERE id = ?
        """, (exercise_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, f"exercise {exercise_id} not found")
        conn.commit()
    return {"status": "dismissed", "id": exercise_id}


class MergeRequest(BaseModel):
    target_id: int


@router.post("/exercises/{exercise_id}/merge", dependencies=[Depends(require_admin)])
def merge_exercise(exercise_id: int, body: MergeRequest):
    """Mark exercise as a duplicate of `target_id` — sets status='merged'
    and merged_into_id. Public list/map ignore merged rows."""
    if body.target_id == exercise_id:
        raise HTTPException(400, "cannot merge an exercise into itself")
    with db_conn() as conn:
        target = conn.execute(
            "SELECT id, approval_status FROM military_exercises WHERE id = ?",
            (body.target_id,)
        ).fetchone()
        if not target:
            raise HTTPException(404, f"target {body.target_id} not found")
        cur = conn.execute("""
            UPDATE military_exercises
            SET approval_status = 'merged', merged_into_id = ?, reviewed_at = datetime('now')
            WHERE id = ?
        """, (body.target_id, exercise_id))
        if cur.rowcount == 0:
            raise HTTPException(404, f"exercise {exercise_id} not found")
        conn.commit()
    return {"status": "merged", "id": exercise_id, "merged_into_id": body.target_id}


class ExercisePatch(BaseModel):
    # All optional; only provided fields are written. Use sentinel None
    # to mean "don't change"; clients that want to NULL a field must use
    # explicit empty string for text fields or a separate clear flag.
    name_en:        Optional[str] = None
    name_zh:        Optional[str] = None
    performer:      Optional[str] = None
    participants:   Optional[List[str]] = None
    exercise_kind:  Optional[str] = None
    start_date:     Optional[str] = None
    end_date:       Optional[str] = None
    location_label: Optional[str] = None
    latitude:       Optional[float] = None
    longitude:      Optional[float] = None
    description_en: Optional[str] = None


@router.patch("/exercises/{exercise_id}", dependencies=[Depends(require_admin)])
def patch_exercise(exercise_id: int, patch: ExercisePatch):
    """Analyst edits to a candidate row during review. Empty strings null
    text fields; explicit numeric values overwrite lat/lng. Re-derives
    canonical_name from name_en if name_en changes."""
    data = patch.model_dump(exclude_unset=True)

    if "performer" in data:
        if data["performer"] not in _VALID_PERFORMERS:
            raise HTTPException(400, f"invalid performer {data['performer']!r}")
    if "exercise_kind" in data and data["exercise_kind"] not in _VALID_EXERCISE_KINDS:
        raise HTTPException(400, f"invalid exercise_kind {data['exercise_kind']!r}")

    # Recompute canonical_name from name_en if the analyst edited the name.
    if "name_en" in data:
        en = (data["name_en"] or "").strip()
        data["name_en"] = en or None
        data["canonical_name"] = _build_exercise_canonical_key(en)

    if "participants" in data:
        parts = data.pop("participants")
        data["participants_json"] = json.dumps(parts) if parts else None

    # Empty strings for text fields → NULL
    for k in ("name_zh", "location_label", "description_en", "start_date", "end_date"):
        if k in data and isinstance(data[k], str) and data[k].strip() == "":
            data[k] = None

    if not data:
        raise HTTPException(400, "no fields to update")

    set_clause = ", ".join(f"{k} = :{k}" for k in data)
    params = {**data, "id": exercise_id}
    with db_conn() as conn:
        cur = conn.execute(
            f"UPDATE military_exercises SET {set_clause} WHERE id = :id",
            params,
        )
        if cur.rowcount == 0:
            raise HTTPException(404, f"exercise {exercise_id} not found")
        row = conn.execute(f"""
            SELECT {_EXERCISE_PUBLIC_COLS}
            FROM military_exercises e
            JOIN articles a ON e.article_id = a.id
            JOIN sources s ON s.id = a.source_id
            WHERE e.id = ?
        """, (exercise_id,)).fetchone()
        conn.commit()
    return _row_to_exercise(row)
