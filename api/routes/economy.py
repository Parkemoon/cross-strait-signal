"""Cross-strait economic indicators endpoint (Phase 2a).

Data sourced from MAC (Mainland Affairs Council) monthly publications via
data.gov.tw dataset 7887. See scraper/scrapers/mac_economic_scraper.py.
"""
from fastapi import APIRouter, Query
from typing import Optional

from api.database import get_db

router = APIRouter(prefix="/api/economy", tags=["economy"])


# Display metadata for each indicator. Order here is the order the frontend
# will render them in pickers.
SERIES_META = [
    {
        "id": "trade_total_usd_b",
        "label_en": "Total cross-strait trade",
        "label_zh": "兩岸貿易總額",
        "unit": "USD billions",
        "axis_label": "USD bn",
        "category": "trade",
        "reporter": "MAC",
    },
    {
        "id": "exports_to_prc_usd_b",
        "label_en": "Taiwan exports to PRC",
        "label_zh": "對中國大陸出口",
        "unit": "USD billions",
        "axis_label": "USD bn",
        "category": "trade",
        "reporter": "MAC",
    },
    {
        "id": "imports_from_prc_usd_b",
        "label_en": "Taiwan imports from PRC",
        "label_zh": "自中國大陸進口",
        "unit": "USD billions",
        "axis_label": "USD bn",
        "category": "trade",
        "reporter": "MAC",
    },
    {
        "id": "trade_balance_usd_b",
        "label_en": "Cross-strait trade balance",
        "label_zh": "兩岸貿易出(入)超",
        "unit": "USD billions",
        "axis_label": "USD bn",
        "category": "trade",
        "reporter": "MAC",
    },
    # PRC-reported equivalents (UN Comtrade, reporter=156, partner=490)
    {
        "id": "comtrade_prc_imports_from_tw_usd_b",
        "label_en": "PRC imports from Taiwan (PRC customs)",
        "label_zh": "中國大陸自臺進口（陸方海關）",
        "unit": "USD billions",
        "axis_label": "USD bn",
        "category": "verification",
        "reporter": "Comtrade",
        "compares_with": "exports_to_prc_usd_b",
    },
    {
        "id": "comtrade_prc_exports_to_tw_usd_b",
        "label_en": "PRC exports to Taiwan (PRC customs)",
        "label_zh": "中國大陸對臺出口（陸方海關）",
        "unit": "USD billions",
        "axis_label": "USD bn",
        "category": "verification",
        "reporter": "Comtrade",
        "compares_with": "imports_from_prc_usd_b",
    },
    {
        "id": "tw_investment_prc_amount_usd_b",
        "label_en": "TW investment in PRC (approved)",
        "label_zh": "對中國大陸投資金額",
        "unit": "USD billions",
        "axis_label": "USD bn",
        "category": "investment",
    },
    {
        "id": "tw_investment_prc_count",
        "label_en": "TW investment cases in PRC",
        "label_zh": "對中國大陸投資件數",
        "unit": "cases",
        "axis_label": "cases",
        "category": "investment",
    },
    {
        "id": "prc_visitors_tw_10k",
        "label_en": "PRC visitors to Taiwan",
        "label_zh": "中國大陸人民來臺",
        "unit": "10k persons",
        "axis_label": "10k",
        "category": "people",
    },
    {
        "id": "tw_visitors_prc_10k",
        "label_en": "TW visitors to PRC",
        "label_zh": "國人赴中國大陸",
        "unit": "10k persons",
        "axis_label": "10k",
        "category": "people",
    },
]
SERIES_META_BY_ID = {s["id"]: s for s in SERIES_META}


@router.get("/series")
def get_series(
    ids: Optional[str] = Query(None, description="Comma-separated series IDs. Omit for all."),
    start: Optional[str] = Query(None, description="ISO period (YYYY-MM) inclusive lower bound"),
    end: Optional[str] = Query(None, description="ISO period (YYYY-MM) inclusive upper bound"),
    months: Optional[int] = Query(None, description="Limit to most recent N months"),
):
    """Return time-series data for cross-strait economic indicators.

    Response shape:
      {
        "series": [
          {
            "id": "trade_total_usd_b",
            "label_en": "...", "unit": "...", "category": "...",
            "points": [{"period": "2026-03", "value": 206.1, "yoy_pct": 30.6}, ...]
          },
          ...
        ],
        "last_updated": "2026-03"
      }
    """
    conn = get_db()

    if ids:
        requested_ids = [s.strip() for s in ids.split(",") if s.strip()]
        # Preserve declared order, but only include known series
        ordered_ids = [sid for sid in (s["id"] for s in SERIES_META) if sid in requested_ids]
    else:
        ordered_ids = [s["id"] for s in SERIES_META]

    if not ordered_ids:
        conn.close()
        return {"series": [], "last_updated": None}

    placeholders = ",".join("?" * len(ordered_ids))
    where_clauses = [
        f"series_id IN ({placeholders})",
        "period_type = 'month'",
    ]
    params: list = list(ordered_ids)

    if start:
        where_clauses.append("period >= ?")
        params.append(start)
    if end:
        where_clauses.append("period <= ?")
        params.append(end)

    where_sql = " AND ".join(where_clauses)
    rows = conn.execute(
        f"""
        SELECT series_id, period, value, yoy_pct
        FROM economic_indicators
        WHERE {where_sql}
        ORDER BY series_id, period ASC
        """,
        params,
    ).fetchall()

    # Group rows by series_id
    grouped: dict[str, list[dict]] = {sid: [] for sid in ordered_ids}
    for r in rows:
        grouped[r["series_id"]].append({
            "period": r["period"],
            "value": r["value"],
            "yoy_pct": r["yoy_pct"],
        })

    # Apply per-series tail trim if `months` is set
    if months and months > 0:
        for sid in grouped:
            grouped[sid] = grouped[sid][-months:]

    series_payload = []
    for sid in ordered_ids:
        meta = SERIES_META_BY_ID[sid]
        series_payload.append({
            **meta,
            "points": grouped[sid],
        })

    last_updated_row = conn.execute(
        "SELECT MAX(period) AS latest FROM economic_indicators WHERE period_type = 'month'"
    ).fetchone()
    conn.close()

    return {
        "series": series_payload,
        "last_updated": last_updated_row["latest"] if last_updated_row else None,
    }


@router.get("/series/meta")
def get_series_meta():
    """Return just the indicator catalog (no data) — useful for frontend bootstrap."""
    return {"series": SERIES_META}


# Pairs of (MAC_series, Comtrade_series, flow_label)
VERIFICATION_PAIRS = [
    {
        "flow_id": "tw_exports_to_prc",
        "label_en": "Taiwan exports to PRC",
        "label_zh": "對中國大陸出口",
        "tw_series": "exports_to_prc_usd_b",
        "prc_series": "comtrade_prc_imports_from_tw_usd_b",
        "tw_reporter_label": "TW MAC",
        "prc_reporter_label": "PRC Customs (Comtrade)",
    },
    {
        "flow_id": "tw_imports_from_prc",
        "label_en": "Taiwan imports from PRC",
        "label_zh": "自中國大陸進口",
        "tw_series": "imports_from_prc_usd_b",
        "prc_series": "comtrade_prc_exports_to_tw_usd_b",
        "tw_reporter_label": "TW MAC",
        "prc_reporter_label": "PRC Customs (Comtrade)",
    },
]


@router.get("/verification")
def get_verification(
    months: Optional[int] = Query(None, description="Limit to most recent N months"),
):
    """Pair MAC's TW-reported trade with Comtrade's PRC-reported trade.

    For each flow we return aligned monthly points {period, tw, prc, gap_usd_b,
    gap_pct}. gap_pct = (prc - tw) / tw * 100; positive means PRC reports a
    higher number than TW (commonly because PRC includes HK transit / re-export
    flows that TW books separately).
    """
    conn = get_db()
    pairs_out = []
    for pair in VERIFICATION_PAIRS:
        rows = conn.execute(
            '''
            SELECT tw.period AS period, tw.value AS tw_value, prc.value AS prc_value
            FROM economic_indicators tw
            LEFT JOIN economic_indicators prc
              ON prc.series_id = ?
             AND prc.period = tw.period
             AND prc.period_type = 'month'
            WHERE tw.series_id = ?
              AND tw.period_type = 'month'
            ORDER BY tw.period ASC
            ''',
            (pair["prc_series"], pair["tw_series"]),
        ).fetchall()

        points = []
        for r in rows:
            tw = r["tw_value"]
            prc = r["prc_value"]
            gap = (prc - tw) if (tw is not None and prc is not None) else None
            gap_pct = ((prc - tw) / tw * 100) if (tw and prc is not None) else None
            points.append({
                "period": r["period"],
                "tw": tw,
                "prc": prc,
                "gap_usd_b": gap,
                "gap_pct": gap_pct,
            })

        if months and months > 0:
            points = points[-months:]

        pairs_out.append({**pair, "points": points})

    last_updated_row = conn.execute(
        "SELECT MAX(period) AS latest FROM economic_indicators WHERE period_type = 'month'"
    ).fetchone()
    conn.close()
    return {
        "pairs": pairs_out,
        "last_updated": last_updated_row["latest"] if last_updated_row else None,
    }
