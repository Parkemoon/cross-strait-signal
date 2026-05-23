"""MAC cross-strait economic indicators scraper.

Fetches dataset 7887 (兩岸經濟交流統計速報) from data.gov.tw.
Each monthly CSV contains trade, investment, and people-flow indicators
in three rows: current month, year-to-date, and all-time cumulative.

MVP scope: monthly point-in-time values only (period_type='month').
"""
import base64
import csv
import io
import os
import sys
import urllib.parse
from datetime import datetime
from typing import Iterable

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

CATALOG_URL = 'https://data.gov.tw/datasets/export/csv'
DATASET_ID = '7887'
SOURCE_TAG = 'MAC_7887'

# Each entry maps a series_id to (header substring tokens, unit, scale).
# Tokens must all appear in the header cell. The value column is followed by
# a "成長率" (growth rate) column; we pair them by position.
# Scale is applied to the raw cell value: MAC publishes USD figures in 億美元
# (10^8 USD), so to store in USD billions we multiply by 0.1.
SERIES_SPECS = [
    ('trade_total_usd_b',          ('貿易總額', '億美元'),       'usd_billion', 0.1),
    ('exports_to_prc_usd_b',       ('對中國大陸出口', '億美元'), 'usd_billion', 0.1),
    ('imports_from_prc_usd_b',     ('自中國大陸進口', '億美元'), 'usd_billion', 0.1),
    ('trade_balance_usd_b',        ('出', '入', '超', '億美元'), 'usd_billion', 0.1),
    ('tw_investment_prc_count',    ('投資件數',),                'count',        1.0),
    ('tw_investment_prc_amount_usd_b', ('投資金額', '億美元'),   'usd_billion', 0.1),
    ('prc_visitors_tw_10k',        ('中國大陸人民來臺人數', '萬人'), '10k_persons', 1.0),
    ('tw_visitors_prc_10k',        ('赴中國大陸', '萬人'),       '10k_persons', 1.0),
]


def fetch_dataset_urls() -> list[str]:
    """Download the data.gov.tw master catalog and return URLs for dataset 7887."""
    with httpx.Client(timeout=60) as client:
        r = client.get(CATALOG_URL)
        r.raise_for_status()
    # data.gov.tw serves the catalog with a UTF-8 BOM
    text = r.content.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        if row.get('資料集識別碼') == DATASET_ID:
            urls = [u.strip() for u in row.get('資料下載網址', '').split(';') if u.strip()]
            return urls
    raise RuntimeError(f'Dataset {DATASET_ID} not found in data.gov.tw catalog')


def direct_url(url: str) -> str:
    """Convert ws.mac.gov.tw Download.ashx proxy URLs to direct static URLs.

    The proxy is Cloudflare-protected; direct paths are not. The ``u=``
    query param is a base64-encoded relative path.
    """
    if 'Download.ashx' not in url:
        return url
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    u = qs.get('u', [None])[0]
    if not u:
        return url
    # Add padding before decode (data.gov.tw strips it)
    pad = '=' * (-len(u) % 4)
    rel_path = base64.b64decode(u + pad).decode('utf-8')
    return f'{parsed.scheme}://{parsed.netloc}{rel_path}'


def roc_to_iso(period_label: str) -> str | None:
    """Convert '115年3月' → '2026-03'. Returns None if not a single-month label."""
    label = period_label.strip()
    if '~' in label or '-' in label.replace('年', '').replace('月', ''):
        return None  # YTD or cumulative range
    # Match patterns like '115年3月' or '106年12月'
    if '年' not in label or '月' not in label:
        return None
    try:
        roc_year_str, rest = label.split('年', 1)
        month_str = rest.replace('月', '').strip()
        if not roc_year_str.strip().isdigit() or not month_str.isdigit():
            return None
        year = 1911 + int(roc_year_str.strip())
        return f'{year:04d}-{int(month_str):02d}'
    except (ValueError, IndexError):
        return None


def parse_number(cell: str) -> float | None:
    """Parse a numeric cell. Returns None for missing values ('－', '-', '')."""
    s = cell.strip().strip('"')
    if not s or s in ('－', '-', '－ ', 'N/A'):
        return None
    # Strip commas, parentheses (used for negatives: '(6.3)' = -6.3)
    negative = False
    if s.startswith('(') and s.endswith(')'):
        negative = True
        s = s[1:-1]
    s = s.replace(',', '').strip()
    if not s:
        return None
    try:
        v = float(s)
        return -v if negative else v
    except ValueError:
        return None


def parse_pct(cell: str) -> float | None:
    """Parse a YoY growth cell.

    MAC publishes most YoY columns with a '%' suffix (e.g. '23.4%'), but the
    'TW visitors to PRC' growth column writes a decimal fraction without '%'
    (e.g. '0.103' meaning 10.3%). We only apply the ×100 conversion in the
    narrow band where it's unambiguous: |val| strictly less than 1 AND no '%'.
    A value of exactly 1.0 (or larger) with no '%' is preserved as-is so a
    real 100% reading doesn't get silently collapsed to 1%.
    """
    raw = cell.strip().strip('"').strip()
    if not raw or raw in ('－', '-'):
        return None
    has_pct_sign = raw.endswith('%')
    val = parse_number(raw.rstrip('%').strip())
    if val is None:
        return None
    if not has_pct_sign and 0 < abs(val) < 1:
        return val * 100
    return val


def map_headers_to_columns(headers: list[str]) -> dict[str, tuple[int, float, int | None]]:
    """For each series spec, find the column index of its value field.

    Returns {series_id: (col_index, scale_factor, period_col_or_None)}.
    `period_col` is the immediately-preceding column when its header contains
    '年(月)別' — used because MAC adopted per-column period sub-headers around
    2024-04, and the visitor columns can now lag the headline period by 1–2
    months (or even report an annual rollup like '112年') even though the
    document's headline period is the current month. Without honouring the
    per-column period we'd file lagged or annual values under the wrong
    monthly period. Series not found are omitted.
    """
    result = {}
    for series_id, tokens, _unit, scale in SERIES_SPECS:
        for i, h in enumerate(headers):
            h_clean = h.strip()
            if all(tok in h_clean for tok in tokens) and '成長率' not in h_clean:
                period_col = None
                if i > 0 and '年(月)別' in headers[i - 1]:
                    period_col = i - 1
                result[series_id] = (i, scale, period_col)
                break
    return result


def parse_monthly_row(headers: list[str], row: list[str]) -> list[tuple[str, str, float | None, float | None]] | None:
    """Parse the '當月統計數' row.

    Returns a list of (series_id, iso_period, value, yoy_pct) — one entry per
    series. Different series can land on different periods because of MAC's
    per-column period sub-headers (the visitor columns typically lag 1–2
    months behind the trade columns). Returns None if the row isn't a monthly
    snapshot row or has no parseable headline period.
    """
    if not row or row[0].strip() != '當月統計數':
        return None
    col_map = map_headers_to_columns(headers)
    # Headline period: first '年X月' looking cell in the row. Used as a
    # fallback for columns that don't carry their own period sub-header.
    headline_period = None
    for cell in row[1:]:
        candidate = roc_to_iso(cell)
        if candidate:
            headline_period = candidate
            break
    if not headline_period:
        return None
    out: list[tuple[str, str, float | None, float | None]] = []
    for series_id, (col_idx, scale, period_col) in col_map.items():
        if col_idx >= len(row):
            continue
        # Resolve the period for this specific column. If MAC has tagged the
        # column with its own '年(月)別' header and the cell is a monthly
        # label, use it; if the cell is an annual rollup ('112年') skip the
        # value entirely so it doesn't pollute the monthly series.
        period = headline_period
        if period_col is not None and period_col < len(row):
            cell = row[period_col].strip()
            if not cell:
                continue  # no period reported → skip
            parsed = roc_to_iso(cell)
            if parsed is None:
                # Non-monthly cell (annual, range, etc.) — drop.
                continue
            period = parsed
        raw_value = parse_number(row[col_idx])
        value = raw_value * scale if raw_value is not None else None
        # YoY % is typically the next column (and is unit-agnostic).
        yoy = parse_pct(row[col_idx + 1]) if col_idx + 1 < len(row) else None
        out.append((series_id, period, value, yoy))
    return out


def fetch_csv(url: str, client: httpx.Client) -> tuple[list[str], list[list[str]]] | None:
    """Fetch a Big5 CSV and return (headers, data_rows). None on failure."""
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
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if len(rows) < 2:
        return None
    return rows[0], rows[1:]


def upsert_indicators(
    conn,
    rows: list[tuple[str, str, float | None, float | None]],
    source_url: str,
) -> int:
    """UPSERT rows into economic_indicators. Returns row count touched."""
    unit_map = {sid: unit for sid, _tokens, unit, _scale in SERIES_SPECS}
    count = 0
    for series_id, iso_period, value, yoy in rows:
        conn.execute('''
            INSERT INTO economic_indicators
                (series_id, period, period_type, value, unit, yoy_pct, source, source_url, scraped_at)
            VALUES (?, ?, 'month', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(series_id, period, period_type) DO UPDATE SET
                value = excluded.value,
                yoy_pct = excluded.yoy_pct,
                source_url = excluded.source_url,
                scraped_at = CURRENT_TIMESTAMP
        ''', (series_id, iso_period, value, unit_map[series_id], yoy, SOURCE_TAG, source_url))
        count += 1
    return count


def scrape_mac_economic():
    """Main entry point. Fetches catalog, downloads all monthly CSVs, upserts."""
    print(f'[MAC econ] Fetching data.gov.tw catalog…')
    urls = fetch_dataset_urls()
    print(f'[MAC econ] Dataset {DATASET_ID}: {len(urls)} monthly files')

    conn = get_connection()
    months_loaded = 0
    months_failed = 0
    total_rows = 0

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for i, raw_url in enumerate(urls):
            url = direct_url(raw_url)
            result = fetch_csv(url, client)
            if not result:
                months_failed += 1
                continue
            headers, data_rows = result
            parsed = parse_monthly_row(headers, data_rows[0])
            if not parsed:
                print(f'  ! parse failed: {url}', file=sys.stderr)
                months_failed += 1
                continue
            n = upsert_indicators(conn, parsed, url)
            total_rows += n
            months_loaded += 1
            # Commit every 10 files so a crash mid-run doesn't lose all progress
            if (i + 1) % 10 == 0:
                conn.commit()

    conn.commit()
    conn.close()
    print(f'[MAC econ] Loaded {months_loaded} months ({total_rows} indicator rows), '
          f'{months_failed} failures')
    return months_loaded


if __name__ == '__main__':
    scrape_mac_economic()
