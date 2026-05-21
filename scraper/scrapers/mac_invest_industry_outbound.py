"""Outbound investment (Taiwan → PRC) by industry — MAC dataset 7473.

Companion to `mac_invest_industry_inbound.py` (MAC 7478, PRC → TW). Both
write to `investment_by_industry` keyed on (direction, period, industry_zh).
This one writes direction='tw_to_prc'.

Source: data.gov.tw dataset 7473 (臺商對中國大陸投資金額統計). One CSV per
monthly cycle at:

    https://www.mac.gov.tw/big5/data/CSESM/9/<N>_9.csv

`N` follows the same numbering as 7478 (starts at 316 ≈ 2019-06, increments
monthly through ~396 ≈ 2026-02). We probe until 3 consecutive 404s.

Per-file shape differs from 7478 — each CSV has **four column groups** of
(件數, 金額(百萬美元), 金額比重), each tagged with a period in parentheses
in the header. The four groups (in column order) are:
    1. Prior month       — header (YYYY年M月)
    2. Reporting month   — header (YYYY年M月)        ← "current"
    3. YTD               — header (YYYY年1-M月)
    4. Cumulative-since-1991 — header (1991-YYYY年M月累計) ← what we want

We extract group 4 (the cumulative snapshot) and store it as the period
identified by the YYYY-M end of the cumulative range. Two scale gotchas:

  * MAC publishes amount in **百萬美元 (millions USD)** here, not
    千美元 (thousands USD) as 7478 does. We multiply by 1000 on ingest so
    the column unit (`amount_usd_k`) is consistent across both directions.
  * Cumulative range is **since 1991**, not since 2009-07 as 7478 is.
    `amount_share_pct` is therefore share of a longer-run total; the
    comparison across directions is still meaningful since both are
    "share of approved cross-strait flow at this snapshot," just over
    different historical windows.
"""
import csv
import io
import os
import re
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection
from scraper.scrapers.mac_invest_industry_inbound import (
    INDUSTRY_EN, _parse_number,
)

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL  = 'https://www.mac.gov.tw/big5/data/CSESM/9/{n}_9.csv'
FIRST_N   = 316
PROBE_MAX = 450
DIRECTION = 'tw_to_prc'

# Header pattern for the cumulative-since-1991 column group:
#   (1991-YYYY年M月累計) or (1991-YYYY年累計) for annual summaries
_CUM_PERIOD_RE = re.compile(r'\(1991-(\d{4})年(?:(\d{1,2})月)?累計\)')

# 7473's cumulative column group also has a few alias industry names that
# don't appear in 7478 — extend the inbound map without duplicating it.
_EXTRA_INDUSTRY_EN = {
    '金融及保險業':                   'Finance and insurance',
    '電腦、電子產品及光學製品製造業': 'Computers, electronics, and optics',
    '運輸工具製造業':                 'Transport equipment',
    '皮革、毛皮及其製品製造業':       'Leather and fur products',
    '木竹製品製造業':                 'Wood and bamboo products',
    '紙漿、紙及紙製品製造業':         'Pulp and paper products',
    '非金屬礦物製品製造業':           'Non-metallic mineral products',
    '石油及煤製品製造業':             'Petroleum and coal products',
    '汽車及其零件製造業':             'Automobiles and parts',
    '其他運輸工具及其零件製造業':     'Other transport equipment',
    '機械設備修配業':                 'Machinery repair and assembly',
    '電子產品及光學製品製造業':       'Electronic and optical products',
    '其他金融及保險業':               'Other finance and insurance',
}
INDUSTRY_EN_ALL = {**INDUSTRY_EN, **_EXTRA_INDUSTRY_EN}


def _find_cumulative_columns(header_row: list[str]) -> tuple[str | None, int | None, int | None, int | None]:
    """Locate the cumulative-since-1991 column group in the header.

    Returns (period, cases_col, amount_col, share_col). The three columns
    are always contiguous in MAC's CSVs: cases, amount, share — so we find
    the period match and assume the next two columns are amount and share.
    """
    for i, cell in enumerate(header_row):
        m = _CUM_PERIOD_RE.search(cell)
        if m:
            end_year = int(m.group(1))
            end_month = int(m.group(2)) if m.group(2) else 12
            period = f'{end_year:04d}-{end_month:02d}'
            # 件數 (cases) column is `i`, 金額 is `i+1`, 比重 is `i+2`
            # — only if this `i` is the *cases* column (not amount/share).
            # MAC labels "件數(...累計)" for cases, "金額(...累計)" for amount,
            # "金額比重(...累計)" for share. We want the cases column.
            if '件數' in cell:
                return period, i, i + 1, i + 2
    return None, None, None, None


def _fetch_csv(n: int) -> tuple[int, bytes]:
    url = BASE_URL.format(n=n)
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        resp = client.get(url)
        return resp.status_code, resp.content


def _parse_snapshot(blob: bytes) -> tuple[str | None, list[dict]]:
    """Extract the cumulative-since-1991 column group from one CSV."""
    text = blob.decode('utf-8-sig', errors='replace')
    reader = csv.reader(io.StringIO(text, newline=''))
    rows = list(reader)
    if len(rows) < 2:
        return None, []
    period, ci, ai, si = _find_cumulative_columns(rows[0])
    if not period:
        return None, []
    parsed = []
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        # Need at least up to the share column
        if len(row) <= si:
            continue
        industry_zh = row[0].strip()
        cases  = _parse_number(row[ci])
        amount = _parse_number(row[ai])
        share  = _parse_number(row[si])
        if cases is None and amount is None and share is None:
            continue
        parsed.append({
            'industry_zh':      industry_zh,
            'cases':            int(cases) if cases is not None else None,
            # Normalise to thousands USD (MAC publishes in millions here)
            'amount_usd_k':     amount * 1000 if amount is not None else None,
            'amount_share_pct': share,
        })
    return period, parsed


_UPSERT_SQL = """
INSERT INTO investment_by_industry
    (direction, period, industry_zh, industry_en, cases, amount_usd_k,
     amount_share_pct, source_url)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(direction, period, industry_zh) DO UPDATE SET
    industry_en      = COALESCE(excluded.industry_en, investment_by_industry.industry_en),
    cases            = excluded.cases,
    amount_usd_k     = excluded.amount_usd_k,
    amount_share_pct = excluded.amount_share_pct,
    source_url       = excluded.source_url,
    scraped_at       = CURRENT_TIMESTAMP
"""


def scrape_mac_invest_industry_outbound() -> dict:
    conn = get_connection()
    snapshots = 0
    rows_written = 0
    misses = 0

    for n in range(FIRST_N, PROBE_MAX + 1):
        try:
            status, blob = _fetch_csv(n)
        except Exception as e:
            print(f'[MAC 7473] fetch error at n={n}: {e}')
            continue

        if status == 404:
            misses += 1
            if misses >= 3:
                break
            continue
        if status != 200:
            print(f'[MAC 7473] unexpected status {status} at n={n}')
            continue
        misses = 0

        period, rows = _parse_snapshot(blob)
        if not period or not rows:
            continue

        url = BASE_URL.format(n=n)
        params = [
            (DIRECTION, period, r['industry_zh'], INDUSTRY_EN_ALL.get(r['industry_zh']),
             r['cases'], r['amount_usd_k'], r['amount_share_pct'], url)
            for r in rows
        ]
        conn.executemany(_UPSERT_SQL, params)
        snapshots += 1
        rows_written += len(params)

    conn.commit()
    conn.close()

    counts = {'snapshots': snapshots, 'rows_written': rows_written}
    print(f'[MAC 7473] {counts}')
    return counts


if __name__ == '__main__':
    scrape_mac_invest_industry_outbound()
