"""TW-HK trade statistics scraper (MAC dataset 7459).

Fetches 臺灣對香港貿易統計表 from data.gov.tw / mac.gov.tw. The CSV is
unique in that it carries the **same trade flow as recorded by two customs
authorities**: TW Customs (via Taiwan's Ministry of Finance) and HK Customs
(Census & Statistics Dept). The reporting gap between them is the analytical
analog of the existing MAC-vs-Comtrade verification on the TW-PRC leg.

CSV columns (UTF-8 BOM, header row in Chinese):
    年份  TW海關出口  TW海關進口  TW海關總額  HK海關出口  HK海關進口  HK海關總額

The "出口"/"進口" labels are TW-flow-centric throughout — i.e. "HK海關出口"
means *TW exports to HK as recorded by HK Customs* (cross-checks against
"TW海關出口"), not "HK's outbound exports to TW".

Period format:
    1987–2021    annual rows ("1987", "2021", ...)
    2022+        monthly rows ("2022.1" through "2022.12") with annual
                 summary appended as "2022"

Trap: months 10/11/12 produce "2022.10" / "2022.11" / "2022.12" — but
"2022.10" looks identical to "2022.1" (January). We disambiguate by
position: rows are emitted in calendar order, so the *second* "YYYY.1" we
see is October.

Values are in millions of USD. We store in USD billions (scale 0.001) to
match the other trade series.
"""
import csv
import io
import os
import sys
from typing import Iterator

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

CSV_URL = 'https://www.mac.gov.tw/big5/data/8-臺灣對香港貿易統計表.csv'
SOURCE_TAG = 'MAC_7459'

# (series_id, csv_column_index, unit)
# Column 0 is the period label.
COLUMN_MAP = [
    ('exports_to_hk_usd_b',           1, 'usd_billion'),  # TW Customs view
    ('imports_from_hk_usd_b',         2, 'usd_billion'),  # TW Customs view
    ('hk_customs_tw_exports_usd_b',   4, 'usd_billion'),  # HK Customs view of TW→HK
    ('hk_customs_tw_imports_usd_b',   5, 'usd_billion'),  # HK Customs view of HK→TW
]
SCALE = 0.001  # millions → billions


def parse_number(cell: str) -> float | None:
    s = cell.strip().strip('"')
    if not s or s in ('-', '－', 'N/A'):
        return None
    s = s.replace(',', '')
    try:
        return float(s)
    except ValueError:
        return None


def iter_monthly_periods(rows: list[list[str]]) -> Iterator[tuple[str, list[str]]]:
    """Yield (iso_period, row) for monthly rows only.

    Disambiguates the "2022.1" Jan/Oct collision by tracking how many times
    we've seen a given (year, '1') tuple within the same calendar year. The
    second occurrence is October.
    """
    # Per-year occurrence counter for ".1" (collides with ".10")
    jan_seen_in_year: dict[int, int] = {}
    last_year_seen: int | None = None

    for row in rows:
        if not row or not row[0].strip():
            continue
        label = row[0].strip()
        if '.' not in label:
            continue  # annual or summary row
        try:
            year_str, month_str = label.split('.', 1)
            year = int(year_str)
        except ValueError:
            continue

        # Reset counter when we enter a new year
        if last_year_seen is not None and year != last_year_seen:
            jan_seen_in_year[year] = jan_seen_in_year.get(year, 0)
        last_year_seen = year

        if month_str == '1':
            jan_seen_in_year[year] = jan_seen_in_year.get(year, 0) + 1
            month = 10 if jan_seen_in_year[year] == 2 else 1
        else:
            try:
                month = int(month_str)
            except ValueError:
                continue

        if not (1 <= month <= 12):
            continue
        yield f'{year:04d}-{month:02d}', row


def fetch_csv(client: httpx.Client) -> list[list[str]]:
    r = client.get(CSV_URL, timeout=30)
    r.raise_for_status()
    text = r.content.decode('utf-8-sig')
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    return rows


def upsert_indicators(conn, iso_period: str, row: list[str]) -> int:
    count = 0
    for series_id, col_idx, unit in COLUMN_MAP:
        if col_idx >= len(row):
            continue
        raw = parse_number(row[col_idx])
        value = raw * SCALE if raw is not None else None
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
            (series_id, iso_period, value, unit, SOURCE_TAG, CSV_URL),
        )
        count += 1
    return count


def scrape_mac_hk_trade() -> int:
    """Main entry point. Returns count of months loaded."""
    print(f'[MAC 7459] Fetching TW-HK trade CSV…')
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        rows = fetch_csv(client)
    if len(rows) < 2:
        print(f'[MAC 7459] No data', file=sys.stderr)
        return 0

    data_rows = rows[1:]  # skip header
    conn = get_connection()
    months_loaded = 0
    total_indicator_rows = 0

    for iso_period, row in iter_monthly_periods(data_rows):
        n = upsert_indicators(conn, iso_period, row)
        total_indicator_rows += n
        months_loaded += 1

    conn.commit()
    conn.close()
    print(f'[MAC 7459] Loaded {months_loaded} months ({total_indicator_rows} indicator rows)')
    return months_loaded


if __name__ == '__main__':
    scrape_mac_hk_trade()
