"""HK Census & Statistics Department — TW-HK trade as a third reporter.

Cross-strait trade verification already pairs MAC (TW Customs) against
UN Comtrade (PRC Customs) and against MAC's compilation of HK Customs
figures (dataset 7459). This adds HK CSD **directly** as a third
reporter — bypassing MAC's compilation entirely so we can also check
MAC's compilation accuracy.

Sources (both via censtatd's JSON API):
  * Table 410-50012 — "Imports from ten main suppliers" (TW is one).
    Gives HK ← TW flow as recorded by HK Customs.
  * Table 410-50013 — "Total exports to ten main destinations".
    Gives HK → TW flow as recorded by HK Customs.

Both publish monthly figures back to 1972-01 in HK$ million. We
normalise to USD billions via the HKD/USD peg (7.78 mid) so the
result is plottable alongside MAC's USD-denominated series. The HKD
has been pegged to USD since 1983; pre-1983 figures use the same
constant for simplicity — small distortion, doesn't affect modern
verification windows.

API endpoint pattern:
    https://www.censtatd.gov.hk/api/get.php?id=410-<table>&lang=en&full_series=1

`full_series=1` is required — without it the API returns "Parameter is
not defined". Each row carries:
    COUNTRY (numeric code), COUNTRYDesc (e.g. "Taiwan"),
    freq ("M" monthly | "Y" annual), period ("YYYYMM" or "YYYY"),
    sv (VAL_IM | VAL_TX), svDesc ("HK$ million" | "Year-on-year %"),
    figure (number or empty), sd_value (status, e.g. "N.A.").
"""
import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

API_URL = 'https://www.censtatd.gov.hk/api/get.php'

# HKD/USD peg mid-rate. Real rate moves in a 7.75-7.85 band but pegged
# since 1983. Using a constant keeps the math reproducible.
HKD_PER_USD = 7.78

# (table_id, country_filter, series_id, source_tag, direction_label)
SPECS = [
    {
        'table_id':   '410-50012',
        'country':    'Taiwan',
        'series_id':  'hk_csd_hk_from_tw_imports_usd_b',
        'source_tag': 'HK_CSD_410_50012',
        'label':      'HK imports from TW (HK Customs direct)',
    },
    {
        'table_id':   '410-50013',
        'country':    'Taiwan',
        'series_id':  'hk_csd_hk_to_tw_exports_usd_b',
        'source_tag': 'HK_CSD_410_50013',
        'label':      'HK exports to TW (HK Customs direct)',
    },
]


def _fetch(table_id: str) -> list[dict]:
    url = API_URL
    params = {'id': table_id, 'lang': 'en', 'full_series': '1'}
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    return data.get('dataSet', [])


def _hkmillion_to_usdb(figure) -> float | None:
    """Convert HK$ million → USD billions via peg.

    HK$ X million / 7.78 = US$ X/7.78 million = US$ X/7780 billion.
    """
    if figure in (None, '', 'N.A.'):
        return None
    try:
        v = float(figure)
    except (TypeError, ValueError):
        return None
    return v / (HKD_PER_USD * 1000.0)


_UPSERT_SQL = """
INSERT INTO economic_indicators
    (series_id, period, period_type, value, unit, yoy_pct, source, source_url)
VALUES (?, ?, 'month', ?, 'usd_billion', NULL, ?, ?)
ON CONFLICT(series_id, period, period_type) DO UPDATE SET
    value      = excluded.value,
    source     = excluded.source,
    source_url = excluded.source_url,
    scraped_at = CURRENT_TIMESTAMP
"""


def _period_iso(period_str: str) -> str | None:
    """Convert censtatd 'YYYYMM' → 'YYYY-MM'. Annual rows are skipped."""
    s = (period_str or '').strip()
    if len(s) != 6 or not s.isdigit():
        return None
    return f'{s[:4]}-{s[4:6]}'


def scrape_hk_census() -> dict:
    """Fetch HK CSD tables 410-50012 and 410-50013, store TW monthly
    figures in economic_indicators (USD billions)."""
    conn = get_connection()
    counts: dict[str, int] = {}

    for spec in SPECS:
        try:
            rows = _fetch(spec['table_id'])
        except Exception as e:
            print(f'[HK CSD] fetch {spec["table_id"]} failed: {e}')
            counts[spec['series_id']] = 0
            continue

        upsert_rows = []
        api_url = f"{API_URL}?id={spec['table_id']}&lang=en&full_series=1"
        for r in rows:
            if r.get('COUNTRYDesc') != spec['country']:
                continue
            if r.get('freq') != 'M':
                continue
            if r.get('svDesc') != 'HK$ million':  # skip YoY rows
                continue
            period = _period_iso(r.get('period'))
            if not period:
                continue
            value_usd_b = _hkmillion_to_usdb(r.get('figure'))
            if value_usd_b is None:
                continue
            upsert_rows.append(
                (spec['series_id'], period, value_usd_b,
                 spec['source_tag'], api_url)
            )

        if upsert_rows:
            conn.executemany(_UPSERT_SQL, upsert_rows)
            counts[spec['series_id']] = len(upsert_rows)
        else:
            counts[spec['series_id']] = 0

    conn.commit()
    conn.close()

    print(f'[HK CSD] {counts}')
    return counts


if __name__ == '__main__':
    scrape_hk_census()
