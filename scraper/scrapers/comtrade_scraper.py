"""UN Comtrade scraper — PRC-reported trade with Taiwan.

Independent verification source for MAC's cross-strait trade figures.
PRC reports its trade with Taiwan under partner code 490 ("Other Asia, nes"),
not 158 ("Taiwan, Province of China") — confirmed empirically.

Free public preview API: no auth, ~1 req/sec recommended, 500-row response cap
per call. We query one period at a time with cmdCode=TOTAL → 2 rows per call
(one each for import and export flows).

Stored under series_id prefix 'comtrade_prc_' so the API/frontend can pair
them with the corresponding MAC series for verification.
"""
import os
import sys
import time
from typing import Iterable

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

COMTRADE_URL = 'https://comtradeapi.un.org/public/v1/preview/C/M/HS'
PRC_REPORTER_CODE = 156
TW_PARTNER_CODE = 490   # "Other Asia, nes" — PRC's coding for Taiwan
SOURCE_TAG = 'UN_COMTRADE_156'
RATE_LIMIT_SECONDS = 1.2   # conservative for free preview tier
RECENT_REFRESH_MONTHS = 6  # always re-fetch the last N months (data revisions)

# flowCode in API → our series_id
# Reporter is PRC, so:
#   M (imports) = PRC importing FROM Taiwan = TW exports TO PRC per PRC reckoning
#   X (exports) = PRC exporting TO Taiwan   = TW imports FROM PRC per PRC reckoning
FLOW_TO_SERIES = {
    'M': 'comtrade_prc_imports_from_tw_usd_b',
    'X': 'comtrade_prc_exports_to_tw_usd_b',
}


def iso_to_comtrade_period(iso_period: str) -> str:
    """'2024-03' → '202403'."""
    return iso_period.replace('-', '')


def fetch_month(client: httpx.Client, iso_period: str) -> dict[str, float]:
    """Fetch one month of PRC-reported trade with TW. Returns {series_id: value_usd_billions}."""
    params = {
        'reporterCode': PRC_REPORTER_CODE,
        'period': iso_to_comtrade_period(iso_period),
        'partnerCode': TW_PARTNER_CODE,
        'cmdCode': 'TOTAL',
    }
    r = client.get(COMTRADE_URL, params=params, timeout=30)
    if r.status_code == 429:
        # backoff and retry once
        time.sleep(10)
        r = client.get(COMTRADE_URL, params=params, timeout=30)
    r.raise_for_status()
    payload = r.json()
    out = {}
    for row in payload.get('data', []) or []:
        flow = row.get('flowCode')
        series_id = FLOW_TO_SERIES.get(flow)
        if not series_id:
            continue
        usd = row.get('primaryValue')
        if usd is None:
            continue
        out[series_id] = usd / 1e9  # raw USD → USD billions
    return out


def compute_yoy(conn, series_id: str, period: str, current: float) -> float | None:
    """Compute year-on-year % change vs the same month one year ago."""
    if current is None:
        return None
    year, month = period.split('-')
    prev_period = f'{int(year) - 1:04d}-{month}'
    row = conn.execute(
        '''SELECT value FROM economic_indicators
           WHERE series_id = ? AND period = ? AND period_type = 'month' ''',
        (series_id, prev_period),
    ).fetchone()
    if not row or row['value'] is None or row['value'] == 0:
        return None
    return (current - row['value']) / row['value'] * 100


def periods_needing_fetch(conn, force_recent: int = RECENT_REFRESH_MONTHS) -> list[str]:
    """Periods to fetch this run.

    Logic:
      * Always include the most recent N months where MAC has data
        (handles Comtrade revisions and catches up if MAC moved ahead).
      * Plus any period that MAC has but we haven't loaded yet from Comtrade.
    """
    mac_periods = {
        r['period'] for r in conn.execute(
            '''SELECT DISTINCT period FROM economic_indicators
               WHERE source = 'MAC_7887' AND period_type = 'month' '''
        ).fetchall()
    }
    if not mac_periods:
        return []
    comtrade_periods = {
        r['period'] for r in conn.execute(
            '''SELECT DISTINCT period FROM economic_indicators
               WHERE source = ? AND period_type = 'month' ''',
            (SOURCE_TAG,),
        ).fetchall()
    }
    sorted_mac = sorted(mac_periods)
    refresh_window = set(sorted_mac[-force_recent:])
    missing = mac_periods - comtrade_periods
    return sorted(missing | refresh_window)


def upsert(conn, series_id: str, period: str, value: float, yoy: float | None) -> None:
    conn.execute(
        '''INSERT INTO economic_indicators
               (series_id, period, period_type, value, unit, yoy_pct, source, source_url, scraped_at)
           VALUES (?, ?, 'month', ?, 'usd_billion', ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(series_id, period, period_type) DO UPDATE SET
               value      = excluded.value,
               yoy_pct    = excluded.yoy_pct,
               source_url = excluded.source_url,
               scraped_at = CURRENT_TIMESTAMP''',
        (series_id, period, value, yoy, SOURCE_TAG,
         f'{COMTRADE_URL}?reporterCode={PRC_REPORTER_CODE}&period={iso_to_comtrade_period(period)}'
         f'&partnerCode={TW_PARTNER_CODE}&cmdCode=TOTAL'),
    )


def scrape_comtrade():
    """Main entry point — incremental, polite, idempotent."""
    conn = get_connection()
    periods = periods_needing_fetch(conn)
    if not periods:
        print('[Comtrade] No MAC periods to align against — run MAC scraper first.')
        conn.close()
        return 0

    print(f'[Comtrade] Fetching {len(periods)} periods (PRC reporter, partner=490 Taiwan)…')
    loaded = 0
    failed = 0
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for i, period in enumerate(periods):
            try:
                results = fetch_month(client, period)
                if not results:
                    # Comtrade has no data for this month yet — silent skip
                    pass
                for series_id, value in results.items():
                    yoy = compute_yoy(conn, series_id, period, value)
                    upsert(conn, series_id, period, value, yoy)
                loaded += 1
            except httpx.HTTPError as e:
                print(f'  ! {period} failed: {e}', file=sys.stderr)
                failed += 1
            if i < len(periods) - 1:
                time.sleep(RATE_LIMIT_SECONDS)
            # Commit every 10 to bound rollback on a mid-run crash
            if (i + 1) % 10 == 0:
                conn.commit()

    conn.commit()
    conn.close()
    print(f'[Comtrade] Loaded {loaded} periods, {failed} failures')
    return loaded


if __name__ == '__main__':
    scrape_comtrade()
