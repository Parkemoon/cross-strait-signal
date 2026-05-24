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
from typing import Optional

from fastapi import APIRouter, Query

from api.database import db_conn

router = APIRouter(prefix="/api/military", tags=["military"])

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
