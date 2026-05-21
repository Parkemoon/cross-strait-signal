"""Cross-strait economic indicators endpoint.

Data sources:
  * MAC dataset 7887 — cross-strait monthly indicators (TW Customs)
  * MAC dataset 7459 — TW-HK trade with TW + HK Customs both reporting
  * MAC dataset 7888 — TW vs PRC macro side-by-side (GDP, CPI, FX, FX rate)
  * UN Comtrade — PRC Customs reporting (reporter 156, partner 490)

The verification endpoint pairs alternative reporters for the same trade
flow. Two pair kinds today: TW MAC vs PRC Customs (the HK transit gap on
the cross-strait leg), and TW MAC vs HK Customs (the same transit visible
from the HK side).
"""
from fastapi import APIRouter, Query
from typing import Optional

from api.database import db_conn

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
    # TW-HK trade (MAC dataset 7459, dual reporter)
    {
        "id": "exports_to_hk_usd_b",
        "label_en": "Taiwan exports to HK",
        "label_zh": "對香港出口",
        "unit": "USD billions",
        "axis_label": "USD bn",
        "category": "trade",
        "reporter": "MAC",
    },
    {
        "id": "imports_from_hk_usd_b",
        "label_en": "Taiwan imports from HK",
        "label_zh": "自香港進口",
        "unit": "USD billions",
        "axis_label": "USD bn",
        "category": "trade",
        "reporter": "MAC",
    },
    {
        "id": "hk_customs_tw_exports_usd_b",
        "label_en": "TW→HK exports (HK customs)",
        "label_zh": "臺輸港（港方海關）",
        "unit": "USD billions",
        "axis_label": "USD bn",
        "category": "verification",
        "reporter": "HK Customs",
        "compares_with": "exports_to_hk_usd_b",
    },
    {
        "id": "hk_customs_tw_imports_usd_b",
        "label_en": "HK→TW exports (HK customs)",
        "label_zh": "港輸臺（港方海關）",
        "unit": "USD billions",
        "axis_label": "USD bn",
        "category": "verification",
        "reporter": "HK Customs",
        "compares_with": "imports_from_hk_usd_b",
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
    # ── Macro: TW vs PRC side-by-side (MAC dataset 7888) ──
    # GDP is quarterly; stored at end-of-quarter month with period_type='month'
    # so the existing series endpoint returns it alongside monthly indicators.
    {
        "id": "tw_gdp_usd_b",
        "label_en": "Taiwan GDP",
        "label_zh": "臺灣 GDP",
        "unit": "USD billions",
        "axis_label": "USD bn",
        "category": "macro",
        "reporter": "MAC",
        "side": "TW",
        "compares_with": "prc_gdp_usd_b",
    },
    {
        "id": "prc_gdp_usd_b",
        "label_en": "PRC GDP",
        "label_zh": "中國大陸 GDP",
        "unit": "USD billions",
        "axis_label": "USD bn",
        "category": "macro",
        "reporter": "MAC",
        "side": "PRC",
        "compares_with": "tw_gdp_usd_b",
    },
    {
        "id": "tw_gdp_growth_pct",
        "label_en": "Taiwan real GDP growth",
        "label_zh": "臺灣經濟成長率",
        "unit": "percent",
        "axis_label": "%",
        "category": "macro",
        "reporter": "MAC",
        "side": "TW",
        "compares_with": "prc_gdp_growth_pct",
    },
    {
        "id": "prc_gdp_growth_pct",
        "label_en": "PRC real GDP growth",
        "label_zh": "中國大陸經濟成長率",
        "unit": "percent",
        "axis_label": "%",
        "category": "macro",
        "reporter": "MAC",
        "side": "PRC",
        "compares_with": "tw_gdp_growth_pct",
    },
    {
        "id": "tw_cpi_yoy_pct",
        "label_en": "Taiwan CPI YoY",
        "label_zh": "臺灣消費者物價",
        "unit": "percent",
        "axis_label": "%",
        "category": "macro",
        "reporter": "MAC",
        "side": "TW",
        "compares_with": "prc_cpi_yoy_pct",
    },
    {
        "id": "prc_cpi_yoy_pct",
        "label_en": "PRC CPI YoY",
        "label_zh": "中國大陸居民消費價格",
        "unit": "percent",
        "axis_label": "%",
        "category": "macro",
        "reporter": "MAC",
        "side": "PRC",
        "compares_with": "tw_cpi_yoy_pct",
    },
    {
        "id": "tw_fx_reserves_usd_b",
        "label_en": "Taiwan FX reserves",
        "label_zh": "臺灣外匯存底",
        "unit": "USD billions",
        "axis_label": "USD bn",
        "category": "macro",
        "reporter": "MAC",
        "side": "TW",
        "compares_with": "prc_fx_reserves_usd_b",
    },
    {
        "id": "prc_fx_reserves_usd_b",
        "label_en": "PRC FX reserves",
        "label_zh": "中國大陸外匯存底",
        "unit": "USD billions",
        "axis_label": "USD bn",
        "category": "macro",
        "reporter": "MAC",
        "side": "PRC",
        "compares_with": "tw_fx_reserves_usd_b",
    },
    {
        "id": "twd_usd_rate",
        "label_en": "TWD per 1 USD",
        "label_zh": "新臺幣兌1美元",
        "unit": "rate",
        "axis_label": "TWD",
        "category": "macro",
        "reporter": "MAC",
        "side": "TW",
    },
    {
        "id": "cny_usd_rate",
        "label_en": "CNY per 1 USD",
        "label_zh": "人民幣兌1美元",
        "unit": "rate",
        "axis_label": "CNY",
        "category": "macro",
        "reporter": "MAC",
        "side": "PRC",
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
    if ids:
        requested_ids = [s.strip() for s in ids.split(",") if s.strip()]
        ordered_ids = [sid for sid in (s["id"] for s in SERIES_META) if sid in requested_ids]
    else:
        ordered_ids = [s["id"] for s in SERIES_META]

    if not ordered_ids:
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
    with db_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT series_id, period, value, yoy_pct
            FROM economic_indicators
            WHERE {where_sql}
            ORDER BY series_id, period ASC
            """,
            params,
        ).fetchall()
        last_updated_row = conn.execute(
            "SELECT MAX(period) AS latest FROM economic_indicators WHERE period_type = 'month'"
        ).fetchone()

    grouped: dict[str, list[dict]] = {sid: [] for sid in ordered_ids}
    for r in rows:
        grouped[r["series_id"]].append({
            "period": r["period"],
            "value": r["value"],
            "yoy_pct": r["yoy_pct"],
        })

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

    return {
        "series": series_payload,
        "last_updated": last_updated_row["latest"] if last_updated_row else None,
    }


@router.get("/series/meta")
def get_series_meta():
    """Return just the indicator catalog (no data) — useful for frontend bootstrap."""
    return {"series": SERIES_META}


# Verification pairs: two reporters disclosing the same trade flow.
# `series_a` is the TW-perspective baseline (always TW MAC); `series_b` is
# the second reporter (PRC Customs via Comtrade, or HK Customs via MAC 7459).
# `kind` groups pairs in the UI: a "prc_customs" section and a "hk_customs"
# section, each with its own narrative.
VERIFICATION_PAIRS = [
    # ── TW vs PRC Customs (the original cross-strait verification) ──
    {
        "flow_id": "tw_exports_to_prc",
        "kind": "prc_customs",
        "label_en": "Taiwan exports to PRC",
        "label_zh": "對中國大陸出口",
        "series_a": "exports_to_prc_usd_b",
        "series_b": "comtrade_prc_imports_from_tw_usd_b",
        "reporter_a_label": "TW MAC",
        "reporter_b_label": "PRC Customs (Comtrade)",
    },
    {
        "flow_id": "tw_imports_from_prc",
        "kind": "prc_customs",
        "label_en": "Taiwan imports from PRC",
        "label_zh": "自中國大陸進口",
        "series_a": "imports_from_prc_usd_b",
        "series_b": "comtrade_prc_exports_to_tw_usd_b",
        "reporter_a_label": "TW MAC",
        "reporter_b_label": "PRC Customs (Comtrade)",
    },
    # ── TW vs HK Customs (HK transit gap from HK's side) ──
    {
        "flow_id": "tw_exports_to_hk",
        "kind": "hk_customs",
        "label_en": "Taiwan exports to HK",
        "label_zh": "對香港出口",
        "series_a": "exports_to_hk_usd_b",
        "series_b": "hk_customs_tw_exports_usd_b",
        "reporter_a_label": "TW MAC",
        "reporter_b_label": "HK Customs",
    },
    {
        "flow_id": "tw_imports_from_hk",
        "kind": "hk_customs",
        "label_en": "Taiwan imports from HK",
        "label_zh": "自香港進口",
        "series_a": "imports_from_hk_usd_b",
        "series_b": "hk_customs_tw_imports_usd_b",
        "reporter_a_label": "TW MAC",
        "reporter_b_label": "HK Customs",
    },
]


@router.get("/verification")
def get_verification(
    months: Optional[int] = Query(None, description="Limit to most recent N months"),
):
    """Pair each TW-reported trade flow with an alternative reporter.

    Returns pairs grouped by `kind` (prc_customs / hk_customs). Each point
    carries {period, value_a, value_b, gap_usd_b, gap_pct}; gap_pct =
    (b - a) / a * 100 — positive means the second reporter records more
    than TW, typically because HK transit / re-export flows are booked
    differently.
    """
    pairs_out = []
    with db_conn() as conn:
        for pair in VERIFICATION_PAIRS:
            rows = conn.execute(
                '''
                SELECT a.period AS period, a.value AS value_a, b.value AS value_b
                FROM economic_indicators a
                LEFT JOIN economic_indicators b
                  ON b.series_id = ?
                 AND b.period = a.period
                 AND b.period_type = 'month'
                WHERE a.series_id = ?
                  AND a.period_type = 'month'
                ORDER BY a.period ASC
                ''',
                (pair["series_b"], pair["series_a"]),
            ).fetchall()

            points = []
            for r in rows:
                va = r["value_a"]
                vb = r["value_b"]
                gap = (vb - va) if (va is not None and vb is not None) else None
                gap_pct = ((vb - va) / va * 100) if (va and vb is not None) else None
                points.append({
                    "period": r["period"],
                    "value_a": va,
                    "value_b": vb,
                    "gap_usd_b": gap,
                    "gap_pct": gap_pct,
                })

            if months and months > 0:
                points = points[-months:]

            pairs_out.append({**pair, "points": points})

        last_updated_row = conn.execute(
            "SELECT MAX(period) AS latest FROM economic_indicators WHERE period_type = 'month'"
        ).fetchone()

    return {
        "pairs": pairs_out,
        "last_updated": last_updated_row["latest"] if last_updated_row else None,
    }
