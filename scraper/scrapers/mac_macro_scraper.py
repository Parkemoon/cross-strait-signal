"""MAC macro indicators scraper (dataset 7888 — 兩岸重要經濟指標統計速報).

Companion to mac_economic_scraper.py (dataset 7887). 7887 covers
cross-strait trade and investment flows; 7888 covers the *macro* state of
both economies side-by-side: GDP, CPI, FX reserves and exchange rates,
each indicator reported for both Taiwan and PRC in the same monthly CSV.

CSV layout per snapshot (35 cols, three rows):
    row 0  headers
    row 1  Taiwan          ('臺灣')
    row 2  Mainland China  ('中國大陸')

Column groups (each group has its own period column because indicators
have different reporting cadences):
    col  0           entity label
    col  1           GDP period (quarterly, e.g. '106年4-6月')
    cols 2-5         GDP values (TWD, RMB, USD) + growth rate
    col  6           prices period (monthly, e.g. '106年8月')
    cols 7-10        TW CPI, TW WPI, PRC CPI, PRC RPI
    cols 11-19       foreign trade (skipped — 7887 already covers TW side)
    cols 20-30       approved foreign investment YTD (skipped — narrower)
    col  31          FX/rates period (end-of-month, e.g. '106年8月底')
    col  32          FX reserves (億美元)
    col  33          TWD/USD rate (TW row only)
    col  34          CNY/USD rate (PRC row only)

URL formats vary across the dataset's lifetime — the older half goes
through the ``Download.ashx?u=<b64>`` proxy; the newer half are already
direct paths under ``ws.mac.gov.tw/001/Upload/295/relfile/…``. The
``direct_url`` helper from 7887 handles both (returns plain URLs as-is).

Period handling: quarterly GDP values are stored at the *last* month of
the quarter (Q2 → '2017-06') with ``period_type='month'``. Visual outcome
on charts is one sparse dot per quarter, aligned to the monthly series.
"""
import csv
import io
import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection
from scraper.utils.dates import roc_year_to_gregorian
from scraper.scrapers.mac_economic_scraper import (
    CATALOG_URL, direct_url, parse_number, parse_pct, roc_to_iso,
)

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DATASET_ID = '7888'
SOURCE_TAG = 'MAC_7888'

# Convert 億 (10^8) USD to USD billions
USD_TO_BILLIONS = 0.1

# Per-entity column extraction rules. Each entry is
#   (series_id, period_col, value_col, unit, scale, parser, period_kind)
# where period_kind controls how the period cell is interpreted:
#   'quarter'  expect 'XXX年A-B月' or 'XXX年A月底' — store at end-of-quarter
#   'month'    expect 'XXX年A月' or 'XXX年A月底' — straight monthly
TW_RULES = [
    ('tw_gdp_usd_b',         1,  4, 'usd_billion', USD_TO_BILLIONS, parse_number, 'quarter'),
    ('tw_gdp_growth_pct',    1,  5, 'pct',         1.0,             parse_pct,    'quarter'),
    ('tw_cpi_yoy_pct',       6,  7, 'pct',         1.0,             parse_pct,    'month'),
    ('tw_fx_reserves_usd_b', 31, 32, 'usd_billion', USD_TO_BILLIONS, parse_number, 'month'),
    ('twd_usd_rate',         31, 33, 'rate',        1.0,             parse_number, 'month'),
]
PRC_RULES = [
    ('prc_gdp_usd_b',         1,  4, 'usd_billion', USD_TO_BILLIONS, parse_number, 'quarter'),
    ('prc_gdp_growth_pct',    1,  5, 'pct',         1.0,             parse_pct,    'quarter'),
    ('prc_cpi_yoy_pct',       6,  9, 'pct',         1.0,             parse_pct,    'month'),  # col 9, not 7
    ('prc_fx_reserves_usd_b', 31, 32, 'usd_billion', USD_TO_BILLIONS, parse_number, 'month'),
    ('cny_usd_rate',          31, 34, 'rate',        1.0,             parse_number, 'month'),
]


def parse_period_to_month(cell: str, kind: str) -> str | None:
    """Parse a MAC period label into 'YYYY-MM'.

    'XXX年A月'       (monthly)        → 'YYYY-MM'
    'XXX年A月底'     (end-of-month)   → 'YYYY-MM'
    'XXX年A-B月'     (quarter range)  → 'YYYY-MM' using B (the end month of the quarter)
    'XXX年A-B月底'   (rare)           → same as range
    'XXX年1-X月'     (YTD when X > 3) → None (we don't store YTD here)

    The ``kind`` arg is the *expected* cadence; we use it to reject
    out-of-shape cells rather than guess.
    """
    if not cell:
        return None
    s = cell.strip().rstrip('底').strip()  # drop trailing 底 if present
    if '年' not in s or '月' not in s:
        return None
    try:
        roc_year_str, rest = s.split('年', 1)
        year = roc_year_to_gregorian(roc_year_str.strip())
        month_part = rest.replace('月', '').strip()
    except (ValueError, IndexError):
        return None

    if '-' in month_part:
        try:
            a, b = (int(x) for x in month_part.split('-', 1))
        except ValueError:
            return None
        if kind == 'quarter':
            # accept only proper quarter ranges aligned to calendar quarters
            if (b - a) == 2 and a in (1, 4, 7, 10):
                month = b
            else:
                return None  # likely YTD, skip
        else:
            return None  # range when we expected single month — skip
    else:
        try:
            month = int(month_part)
        except ValueError:
            return None
        if kind == 'quarter':
            # Some snapshots tag a single-month column as quarter — accept it
            # so we still capture the data, mapping to its enclosing quarter.
            month = ((month - 1) // 3) * 3 + 3  # round up to quarter end
        elif not (1 <= month <= 12):
            return None
    if not (1 <= month <= 12):
        return None
    return f'{year:04d}-{month:02d}'


def fetch_dataset_urls() -> list[str]:
    """Return all monthly CSV URLs for dataset 7888 from the data.gov.tw catalog."""
    with httpx.Client(timeout=60) as client:
        r = client.get(CATALOG_URL)
        r.raise_for_status()
    text = r.content.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        if row.get('資料集識別碼') == DATASET_ID:
            return [u.strip() for u in row.get('資料下載網址', '').split(';') if u.strip()]
    raise RuntimeError(f'Dataset {DATASET_ID} not found in catalog')


def fetch_csv(url: str, client: httpx.Client) -> list[list[str]] | None:
    try:
        r = client.get(url, timeout=30)
        r.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        print(f'  ! fetch failed: {e}', file=sys.stderr)
        return None
    try:
        text = r.content.decode('big5', errors='replace')
    except UnicodeDecodeError:
        text = r.content.decode('utf-8', errors='replace')
    rows = list(csv.reader(io.StringIO(text)))
    return rows or None


def upsert_row(conn, rules: list, csv_row: list[str], source_url: str) -> int:
    """Apply a row of rules (TW_RULES or PRC_RULES) to one data row."""
    count = 0
    for series_id, period_col, value_col, unit, scale, parser, kind in rules:
        if period_col >= len(csv_row) or value_col >= len(csv_row):
            continue
        period = parse_period_to_month(csv_row[period_col], kind)
        if period is None:
            continue
        raw = parser(csv_row[value_col])
        if raw is None:
            continue
        value = raw * scale
        conn.execute(
            '''
            INSERT INTO economic_indicators
                (series_id, period, period_type, value, unit, source, source_url, scraped_at)
            VALUES (?, ?, 'month', ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(series_id, period, period_type) DO UPDATE SET
                value = excluded.value,
                source_url = excluded.source_url,
                scraped_at = CURRENT_TIMESTAMP
            ''',
            (series_id, period, value, unit, SOURCE_TAG, source_url),
        )
        count += 1
    return count


def scrape_mac_macro() -> int:
    print(f'[MAC 7888] Fetching catalog…')
    urls = fetch_dataset_urls()
    print(f'[MAC 7888] {len(urls)} monthly snapshots')

    conn = get_connection()
    snapshots_loaded = 0
    snapshots_failed = 0
    total_rows = 0

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for i, raw_url in enumerate(urls):
            url = direct_url(raw_url)
            rows = fetch_csv(url, client)
            if not rows or len(rows) < 3:
                snapshots_failed += 1
                continue
            # rows[0] = headers, rows[1] = TW, rows[2] = PRC
            tw_row = rows[1]
            prc_row = rows[2]
            # Sanity check entity labels (occasionally column 0 has stray
            # whitespace or different chars — accept any non-empty prefix match)
            if not tw_row[0].strip().startswith('臺灣') and not tw_row[0].strip().startswith('台灣'):
                print(f'  ! row 1 not Taiwan: {tw_row[0][:20]!r} ({url})', file=sys.stderr)
                snapshots_failed += 1
                continue
            if not prc_row[0].strip().startswith('中國大陸'):
                print(f'  ! row 2 not PRC: {prc_row[0][:20]!r} ({url})', file=sys.stderr)
                snapshots_failed += 1
                continue
            total_rows += upsert_row(conn, TW_RULES, tw_row, url)
            total_rows += upsert_row(conn, PRC_RULES, prc_row, url)
            snapshots_loaded += 1
            if (i + 1) % 10 == 0:
                conn.commit()

    conn.commit()
    conn.close()
    print(f'[MAC 7888] {snapshots_loaded} snapshots loaded ({total_rows} indicator rows), '
          f'{snapshots_failed} failures')
    return snapshots_loaded


if __name__ == '__main__':
    scrape_mac_macro()
