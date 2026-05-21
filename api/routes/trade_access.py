"""Cross-strait trade access endpoint.

Surfaces the import permission regime that runs alongside trade volumes:
which HS codes each side bans, which are conditionally allowed, which
enjoy ECFA tariff preferences, and which have had those preferences
suspended.

Powered by ``trade_access_scraper.py``. See that file's docstring for the
underlying source materials.
"""
from fastapi import APIRouter, Query
from typing import Optional

from api.database import db_conn

router = APIRouter(prefix="/api/trade-access", tags=["trade-access"])


# Status display order — surface bans first so they dominate the eye when
# scanning. Keep aligned with the status values written by the scraper.
STATUS_ORDER = ["banned", "ecfa_suspended", "partial_lift", "conditional", "ecfa_active", "allowed"]
STATUS_LABELS = {
    "banned":         "Banned",
    "ecfa_suspended": "ECFA preference suspended",
    # 'partial_lift' is distinct from BOFT's longstanding 'conditional' list:
    # it marks PRC bans that have been partially lifted via selective
    # exporter approval — usually as a politically-brokered concession.
    "partial_lift":   "Partial lift (selective approval)",
    "conditional":    "Conditionally allowed",
    "ecfa_active":    "ECFA preference active",
    "allowed":        "Allowed",
}

# Suspension waves — the analytical timeline ribbon above the table.
SUSPENSION_WAVES = [
    {
        "wave":          1,
        "effective":     "2024-01-01",
        "announced":     "2023-12-21",
        "source_label":  "MOF Announcement 2023 No. 9",
        "item_count":    12,
        "category":      "Petrochemicals",
        "notes":         "Propylene, butadiene, p-xylene and related chemicals.",
    },
    {
        "wave":          2,
        "effective":     "2024-06-15",
        "announced":     "2024-05-31",
        "source_label":  "MOF Announcement 2024 No. 4 (second batch)",
        "item_count":    134,
        "category":      "Petrochemicals, textiles, machinery, steel, vehicles",
        "notes":         "Largest single suspension to date; raises rates to 1–12% MFN.",
    },
]


@router.get("/items")
def list_items(
    direction: Optional[str] = Query(None, description="tw_imports_from_prc | prc_imports_from_tw"),
    status:    Optional[str] = Query(None, description="banned | conditional | ecfa_active | ecfa_suspended | allowed"),
    hs_prefix: Optional[str] = Query(None, description="HS-code prefix (1–8 digits)"),
    search:    Optional[str] = Query(None, description="Substring match on Chinese or English name"),
    limit:     int           = Query(200, ge=1, le=2000),
    offset:    int           = Query(0,   ge=0),
):
    """Filtered slice of the trade_access table.

    Default sort is by status priority (bans first), then HS code ascending.
    """
    clauses, params = [], []
    if direction:
        clauses.append("direction = ?")
        params.append(direction)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if hs_prefix:
        clauses.append("hs_code LIKE ?")
        params.append(f"{hs_prefix.strip()}%")
    if search:
        clauses.append("(product_zh LIKE ? OR product_en LIKE ?)")
        like = f"%{search.strip()}%"
        params.extend([like, like])
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    # Status priority via CASE so banned/suspended bubble to the top.
    status_case = "CASE status " + " ".join(
        f"WHEN '{s}' THEN {i}" for i, s in enumerate(STATUS_ORDER)
    ) + f" ELSE {len(STATUS_ORDER)} END"

    sql_items = f"""
        SELECT direction, hs_code, product_zh, product_en, status,
               effective_date, source, notes, ban_announcement_url
        FROM trade_access
        {where}
        ORDER BY {status_case}, hs_code
        LIMIT ? OFFSET ?
    """
    sql_count = f"SELECT COUNT(*) AS n FROM trade_access {where}"

    with db_conn() as conn:
        total = conn.execute(sql_count, params).fetchone()["n"]
        rows = conn.execute(sql_items, params + [limit, offset]).fetchall()

    return {
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "items":  [dict(r) for r in rows],
    }


@router.get("/summary")
def summary():
    """Headline counts + suspension wave timeline for the tab header strip."""
    sql_counts = """
        SELECT direction, status, COUNT(*) AS n
        FROM trade_access
        GROUP BY direction, status
    """
    sql_latest = """
        SELECT MAX(scraped_at) AS latest FROM trade_access
    """
    with db_conn() as conn:
        count_rows = conn.execute(sql_counts).fetchall()
        latest = conn.execute(sql_latest).fetchone()["latest"]

    # Pivot into {direction: {status: count}}
    by_direction: dict[str, dict[str, int]] = {
        "tw_imports_from_prc": {},
        "prc_imports_from_tw": {},
    }
    for r in count_rows:
        by_direction.setdefault(r["direction"], {})[r["status"]] = r["n"]

    return {
        "last_updated":     latest,
        "by_direction":     by_direction,
        "status_labels":    STATUS_LABELS,
        "suspension_waves": SUSPENSION_WAVES,
    }


@router.get("/cifer-snapshot")
def cifer_snapshot():
    """Latest CIFER snapshot of TW food exporter registrations, paired with
    a short history of prior snapshots for trend context.

    Powered by `scraper/scrapers/cifer_snapshot_scraper.py` — runs monthly
    via cron, scraping `ciferquery.singlewindow.cn` via Playwright/Chromium.
    """
    with db_conn() as conn:
        latest_rows = conn.execute(
            """
            SELECT status, status_zh, count, snapshot_date
            FROM cifer_snapshots
            WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM cifer_snapshots)
            """
        ).fetchall()
        history_rows = conn.execute(
            """
            SELECT snapshot_date, status, count
            FROM cifer_snapshots
            ORDER BY snapshot_date ASC, status
            """
        ).fetchall()

    if not latest_rows:
        return {"latest": None, "history": []}

    latest = {r["status"]: {"count": r["count"], "status_zh": r["status_zh"]} for r in latest_rows}
    snapshot_date = latest_rows[0]["snapshot_date"]
    return {
        "latest": {
            "snapshot_date": snapshot_date,
            "suspended":     latest.get("suspended", {}).get("count"),
            "valid":         latest.get("valid", {}).get("count"),
        },
        "history": [dict(r) for r in history_rows],
    }
