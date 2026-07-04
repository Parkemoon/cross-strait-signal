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
import json
import os

from fastapi import APIRouter, Query, HTTPException
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
    # ── TW vs HK CSD direct (third reporter — confirms MAC's compilation
    # of HK Customs figures matches HK CSD's own publication, AND surfaces
    # the same HK→TW transit gap independent of MAC altogether) ──
    {
        "flow_id": "tw_exports_to_hk",
        "kind": "hk_csd_direct",
        "label_en": "Taiwan exports to HK",
        "label_zh": "對香港出口",
        "series_a": "exports_to_hk_usd_b",
        "series_b": "hk_csd_hk_from_tw_imports_usd_b",
        "reporter_a_label": "TW MAC",
        "reporter_b_label": "HK CSD (direct)",
    },
    {
        "flow_id": "tw_imports_from_hk",
        "kind": "hk_csd_direct",
        "label_en": "Taiwan imports from HK",
        "label_zh": "自香港進口",
        "series_a": "imports_from_hk_usd_b",
        "series_b": "hk_csd_hk_to_tw_exports_usd_b",
        "reporter_a_label": "TW MAC",
        "reporter_b_label": "HK CSD (direct)",
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
            # Full-outer-join semantics so periods covered by *either* reporter
            # are returned (SQLite has no FULL OUTER JOIN; the UNION of the
            # two series' periods gives the same result). HK CSD covers
            # 1972+; we don't want MAC's narrower window to crop it.
            rows = conn.execute(
                '''
                WITH periods AS (
                    SELECT period FROM economic_indicators
                    WHERE series_id = ? AND period_type = 'month'
                    UNION
                    SELECT period FROM economic_indicators
                    WHERE series_id = ? AND period_type = 'month'
                )
                SELECT
                    p.period AS period,
                    (SELECT value FROM economic_indicators
                     WHERE series_id = ? AND period_type = 'month' AND period = p.period) AS value_a,
                    (SELECT value FROM economic_indicators
                     WHERE series_id = ? AND period_type = 'month' AND period = p.period) AS value_b
                FROM periods p
                ORDER BY p.period ASC
                ''',
                (pair["series_a"], pair["series_b"], pair["series_a"], pair["series_b"]),
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


# ── TW → PRC investment verification (MAC approved vs MOFCOM actually used) ──
#
# MAC publishes APPROVED outbound TW→PRC investment monthly (via 7887, in
# our economic_indicators table). MOFCOM publishes ACTUALLY UTILISED FDI
# from Taiwan annually (via its country guide PDFs). The two figures
# diverge substantially in both directions:
#   * Approved-vs-utilised lag (MAC counts at approval moment).
#   * Offshore routing: Taiwanese capital via Cayman/BVI/HK shows under
#     those source-countries in MOFCOM's books, not Taiwan.
# Cumulative since 1991: MAC ~$212B vs MOFCOM ~$73B (utilisation/routing
# ratio ~35%). The 65% gap is the "shadow flow" — capital that left
# Taiwan with approval but never appears in MOFCOM as Taiwan-source.

_MOFCOM_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "scraper", "processors",
    "mofcom_tw_fdi_annual.json",
)


@router.get("/investment-verification")
def investment_verification():
    """Pair MAC's annual approved TW→PRC outbound with MOFCOM's annual
    actually-used Taiwan-source FDI figures.

    MAC annuals are summed from monthly `tw_investment_prc_amount_usd_b`
    in economic_indicators. MOFCOM annuals come from the curated JSON.
    """
    import json as _json
    with open(_MOFCOM_PATH, encoding="utf-8") as f:
        mofcom = _json.load(f)

    with db_conn() as conn:
        # MAC cumulative-since-1991 at end of each year — sum across industries
        # at the YYYY-12 snapshot from investment_by_industry. We use these
        # both for the headline cumulative and for deriving annual flows
        # (annual Y = cum end-Y minus cum end-(Y-1)). Coverage goes back to
        # 2016-12 thanks to the manual pre-2019 backfill (see
        # scripts/backfill_invest_industry_pre2019.py); MAC 7887's monthly
        # series in economic_indicators only goes to 2017-08, which is why
        # we don't use it here anymore.
        mac_cum_rows = conn.execute(
            """
            SELECT substr(period, 1, 4) AS year,
                   SUM(amount_usd_k) / 1e6 AS amount_usd_b
            FROM investment_by_industry
            WHERE direction = 'tw_to_prc'
              AND substr(period, 6, 2) = '12'
            GROUP BY year
            ORDER BY year
            """
        ).fetchall()
        mac_cum_by_year = {int(r["year"]): r["amount_usd_b"] for r in mac_cum_rows}

    # Derive MAC annual flows from cumulative differences (more internally
    # consistent than summing monthly flows: same dataset as the headline
    # cumulative figure, no risk of partial-year under-counting). Pairs
    # where either side is missing are dropped so the chart doesn't show
    # half-empty rows.
    pairs = []
    for entry in mofcom["annual"]:
        y = entry["year"]
        cum_end_y    = mac_cum_by_year.get(y)
        cum_end_prev = mac_cum_by_year.get(y - 1)
        if cum_end_y is None or cum_end_prev is None:
            continue
        mac_v = cum_end_y - cum_end_prev
        mof_v = entry["amount_usd_b"]
        util = (mof_v / mac_v * 100) if mac_v > 0 else None
        pairs.append({
            "year":                  y,
            "mac_approved_usd_b":    mac_v,
            "mofcom_actual_usd_b":   mof_v,
            "mofcom_companies":      entry["companies"],
            "gap_usd_b":             mac_v - mof_v,
            "utilisation_ratio_pct": util,
        })

    # Pair the headline cumulatives at the same end year — MOFCOM's
    # cumulative is end of 2024 (from the 2025 country guide), so use
    # MAC end-2024 too rather than the latest MAC snapshot, to keep the
    # comparison apples-to-apples.
    mofcom_cum_year = 2024
    mac_cum_at_mofcom_year = mac_cum_by_year.get(mofcom_cum_year)

    return {
        "pairs":                  pairs,
        "cumulative": {
            "year":                       mofcom_cum_year,
            "mac_amount_usd_b":           mac_cum_at_mofcom_year,
            "mac_start_year":             1991,
            "mofcom_amount_usd_b":        mofcom["cumulative_end_of_2024"]["amount_usd_b"],
            "mofcom_companies":           mofcom["cumulative_end_of_2024"]["companies"],
            "mofcom_start_year_approx":   1988,
            "utilisation_ratio_pct": (
                (mofcom["cumulative_end_of_2024"]["amount_usd_b"] / mac_cum_at_mofcom_year * 100)
                if mac_cum_at_mofcom_year else None
            ),
        },
        "mofcom_source_label":    mofcom["_meta"]["source_pdf_label"],
        "mofcom_source_url":      mofcom["_meta"]["source_pdf_url"],
        "mofcom_extracted_at":    mofcom["_meta"]["extracted_at"],
    }


# ── Cross-strait investment by industry (MAC 7478 + 7473) ────────────────
#
# Cumulative monthly snapshots in both directions:
#   * prc_to_tw (MAC 7478) — cumulative since 2009-07
#   * tw_to_prc (MAC 7473) — cumulative since 1991
# The 4-5 orders of magnitude asymmetry (TW→PRC much larger) IS the story.

_INVESTMENT_DIRECTIONS = {"prc_to_tw", "tw_to_prc"}


@router.get("/investment-by-industry")
def investment_by_industry(
    direction: str = Query("prc_to_tw", description="prc_to_tw | tw_to_prc"),
    top: int       = Query(10, ge=1, le=30, description="Top-N industries to surface in time-series"),
):
    """Return latest industry breakdown + top-N share-evolution for one direction."""
    if direction not in _INVESTMENT_DIRECTIONS:
        # Raise a real 4xx (like the sibling routes) rather than a 200 with an
        # {"error": ...} body — the shared frontend request() wrapper only checks
        # res.ok, so a 200 error body reads as success and renders empty data.
        raise HTTPException(
            status_code=400,
            detail=f"invalid direction {direction!r}; valid: {sorted(_INVESTMENT_DIRECTIONS)}",
        )

    with db_conn() as conn:
        latest_period_row = conn.execute(
            "SELECT MAX(period) AS p FROM investment_by_industry WHERE direction = ?",
            (direction,),
        ).fetchone()
        latest_period = latest_period_row["p"]
        if not latest_period:
            return {"direction": direction, "latest_period": None, "latest": [],
                    "top_industries": [], "series": []}

        latest_rows = conn.execute(
            """
            SELECT industry_zh, industry_en, cases, amount_usd_k, amount_share_pct
            FROM investment_by_industry
            WHERE direction = ? AND period = ?
            ORDER BY amount_usd_k DESC NULLS LAST
            """,
            (direction, latest_period),
        ).fetchall()
        latest = [dict(r) for r in latest_rows]

        top_industries = [r["industry_zh"] for r in latest_rows[:top]]

        if not top_industries:
            return {"direction": direction, "latest_period": latest_period,
                    "latest": latest, "top_industries": [], "series": []}
        placeholders = ",".join("?" for _ in top_industries)
        series_rows = conn.execute(
            f"""
            SELECT period, industry_zh, industry_en, amount_usd_k, amount_share_pct
            FROM investment_by_industry
            WHERE direction = ? AND industry_zh IN ({placeholders})
            ORDER BY period ASC, amount_usd_k DESC
            """,
            [direction, *top_industries],
        ).fetchall()
        series = [dict(r) for r in series_rows]

    return {
        "direction":      direction,
        "latest_period":  latest_period,
        "latest":         latest,
        "top_industries": top_industries,
        "series":         series,
    }


# ── People records: bidirectional cross-strait residency ──
#
# Pulls `cross_strait_population` (TW NIA permit flows + curated PRC-side
# milestones) and pairs it with the existing tw_visitors_prc_10k +
# prc_visitors_tw_10k series so the frontend can present stock (residents)
# alongside flow (visitors).
#
# `policy_timeline` is a hand-curated array in the JSON sidecar — major
# regulatory events that explain inflection points (1992 launch, 2015 visa-
# free + electronic card, 2020 COVID collapse, 2023 reopening, 2025 first-
# time fee waiver). Loaded once at module import so the endpoint stays fast.
_PEOPLE_JSON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "scraper", "processors", "prc_tw_people_records.json",
)
with open(_PEOPLE_JSON_PATH, encoding="utf-8") as _f:
    _PEOPLE_SIDECAR = json.load(_f)


def _people_flow_series(conn, series_id: str):
    rows = conn.execute(
        """
        SELECT period, value, yoy_pct
        FROM economic_indicators
        WHERE series_id = ? AND period_type = 'month'
        ORDER BY period ASC
        """,
        (series_id,),
    ).fetchall()
    series = [dict(r) for r in rows]
    return {
        "series_id": series_id,
        "series":    series,
        "latest":    series[-1] if series else None,
    }


@router.get("/people-records")
def people_records():
    """Bidirectional cross-strait residency: who lives on the other side."""
    with db_conn() as conn:
        pop_rows = conn.execute(
            """
            SELECT direction, metric, period, period_type, value, unit,
                   source, source_url, notes
            FROM cross_strait_population
            ORDER BY direction, metric, period ASC
            """
        ).fetchall()

        # Pivot rows into nested {direction: {metric: [row, ...]}}.
        directions: dict = {}
        for r in pop_rows:
            d = dict(r)
            directions.setdefault(d["direction"], {}) \
                      .setdefault(d["metric"], []) \
                      .append({
                          "period":      d["period"],
                          "period_type": d["period_type"],
                          "value":       d["value"],
                          "unit":        d["unit"],
                          "source":      d["source"],
                          "source_url":  d["source_url"],
                          "notes":       d["notes"],
                      })

        flows = {
            "tw_visitors_to_prc": {
                "label_en": "TW visitors to PRC",
                "label_zh": "國人赴中國大陸",
                "unit":     "10k persons",
                **_people_flow_series(conn, "tw_visitors_prc_10k"),
            },
            "prc_visitors_to_tw": {
                "label_en": "PRC visitors to Taiwan",
                "label_zh": "中國大陸人民來臺",
                "unit":     "10k persons",
                **_people_flow_series(conn, "prc_visitors_tw_10k"),
            },
        }

    # Tourism Bureau historical annuals pre-date MAC 7887's 2017-08
    # archive window. The inbound JSON splits each year into 華僑 (PRC
    # passport holders) + 外籍 (foreign passport holders flying via
    # mainland) — collapse to a single `visitors` key for the chart,
    # using the column the sidecar nominates in plot_column. Default
    # `huaqiao` matches MAC's 7887 monthly methodology so the annual
    # and monthly lines reconcile.
    def _normalise_annual(block):
        if not block:
            return None
        plot_col = block.get("plot_column", "visitors")
        out = dict(block)
        out["series"] = [
            {"year": r["year"], "visitors": r.get(plot_col, r.get("visitors"))}
            for r in block.get("series", [])
        ]
        return out

    return {
        "meta":            _PEOPLE_SIDECAR.get("_meta", {}),
        "directions":      directions,
        "policy_timeline": _PEOPLE_SIDECAR.get("policy_timeline", []),
        "flows":           flows,
        "annual_flows":    {
            "tw_to_prc":   _normalise_annual(_PEOPLE_SIDECAR.get("tw_outbound_annual")),
            "prc_to_tw":   _normalise_annual(_PEOPLE_SIDECAR.get("prc_inbound_annual")),
        },
    }
