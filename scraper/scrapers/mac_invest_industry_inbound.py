"""Inbound investment (PRC → Taiwan) by industry — MAC dataset 7478.

Companion to `mac_invest_industry_outbound.py` (MAC 7473, TW → PRC). Both
write to `investment_by_industry` keyed on (direction, period, industry_zh).
This one writes direction='prc_to_tw'.

Source: data.gov.tw dataset 7478 (陸資來臺投資業別統計). One CSV per monthly
snapshot, each a CUMULATIVE breakdown of approved PRC investment cases by
industry from 2009-07 onwards. Filename pattern:

    https://www.mac.gov.tw/big5/data/CSESM/12/<N>_12.csv

where N starts at 316 (snapshot covering through June 2019) and increments
by 1 per month. We probe until a 404 to discover the latest available.

Per-file shape (4 columns, UTF-8 with BOM):
    行業別 ,
    核准陸資來臺投資-件數(YYYY年M月至YYYY年M月) ,
    核准陸資來臺投資-金額(千美元)(YYYY年M月至YYYY年M月) ,
    核准陸資來臺投資-金額比重(YYYY年M月至YYYY年M月)

We extract the *end* period (the second 年X月 in the header) as the snapshot
period and store as YYYY-MM. Some files use comma-thousands separators
inside quoted values (e.g. ` 753,556 `); we strip those.

NB: the parent /CSESM/ family is mostly Cloudflare-protected (per
CLAUDE.md), but /CSESM/12/*.csv (this dataset) is plain CSV and passes
through fine — no Referer or UA dance needed. Verified during the 7478
survey on 2026-05-21.
"""
import csv
import io
import os
import re
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL = 'https://www.mac.gov.tw/big5/data/CSESM/12/{n}_12.csv'
FIRST_N  = 316         # snapshot through 2019-06 (the oldest available)
PROBE_MAX = 450        # safe upper bound for "how far to probe"

# Static zh → en translation map for the industry labels MAC uses.
# Untranslated entries write NULL to industry_en; they'll show as their
# Chinese name in the UI until added here.
INDUSTRY_EN = {
    '批發及零售業':                       'Wholesale and retail',
    '電子零組件製造業':                   'Electronic components',
    '銀行業':                             'Banking',
    '資訊軟體服務業':                     'Information software services',
    '港埠業':                             'Port operations',
    '機械設備製造業':                     'Machinery and equipment',
    '電腦、電子產品及光學製品製造業':     'Computers, electronics, and optics',
    '研究發展服務業':                     'Research and development services',
    '電力設備製造業':                     'Electrical equipment',
    '金屬製品製造業':                     'Metal products',
    '住宿服務業':                         'Accommodation services',
    '化學製品製造業':                     'Chemical products',
    '餐飲業':                             'Food and beverage services',
    '醫療器材及用品製造業':               'Medical devices and supplies',
    '廢棄物清除、處理及資源回收業':       'Waste disposal and recycling',
    '紡織業':                             'Textiles',
    '食品製造業':                         'Food manufacturing',
    '化學材料製造業':                     'Chemical materials',
    '汽車及其零件製造業':                 'Automobiles and parts',
    '塑膠製品製造業':                     'Plastic products',
    '會議服務業':                         'Conference services',
    '產業用機械設備維修及安裝業':         'Industrial machinery repair and installation',
    '其他製造業':                         'Other manufacturing',
    '技術檢測及分析服務業':               'Technical testing and analysis services',
    '其他':                               'Other',
    '橡膠製品製造業':                     'Rubber products',
    '皮革、毛皮及其製品製造業':           'Leather and fur products',
    '產業用機械設備維修及安裝業':         'Industrial machinery repair and installation',
    '其他電子零組件製造業':               'Other electronic components',
    '基本金屬製造業':                     'Basic metals',
    '運輸及倉儲業':                       'Transport and warehousing',
    '創業投資業':                         'Venture capital',
    '專業、科學及技術服務業':             'Professional, scientific, and technical services',
    '不動產業':                           'Real estate',
    '出版業':                             'Publishing',
    '證券業':                             'Securities',
    '保險業':                             'Insurance',
    '其他金融服務業':                     'Other financial services',
    '建築工程業':                         'Construction',
    '土木工程業':                         'Civil engineering',
    '農、林、漁、牧業':                   'Agriculture, forestry, fishing, livestock',
    '礦業及土石採取業':                   'Mining and quarrying',
    '其他服務業':                         'Other services',
    '藝術、娛樂及休閒服務業':             'Arts, entertainment, recreation',
    '教育服務業':                         'Education',
    '支援服務業':                         'Support services',
    '電信業':                             'Telecommunications',
    '飲料製造業':                         'Beverages manufacturing',
    '印刷及資料儲存媒體複製業':           'Printing and reproduction',
    '家具製造業':                         'Furniture manufacturing',
    '其他運輸工具及其零件製造業':         'Other transport equipment',
    '木竹製品製造業':                     'Wood and bamboo products',
    '紙漿、紙及紙製品製造業':             'Pulp and paper products',
}

# Header period patterns. The "normal" case is
# `(YYYY年M月至YYYY年M月)`; closing `)` is missing in older snapshots
# (≤ ~2022). Annual-summary CSVs use `(YYYY年M月至YYYY年)` instead — the
# end is a year with no month; we interpret those as year-end (December).
_PERIOD_RE = re.compile(r'\(\d{4}年\d{1,2}月至(\d{4})年(?:(\d{1,2})月)?\)?')


def _parse_period_from_header(header_row: list[str]) -> str | None:
    """Extract YYYY-MM (the *end* of the cumulative range) from any header cell.

    Annual-summary headers omit the end-month; we treat those as year-end
    (December) so they slot into the same monthly timeline.
    """
    for cell in header_row:
        m = _PERIOD_RE.search(cell)
        if m:
            end_year = int(m.group(1))
            end_month = int(m.group(2)) if m.group(2) else 12
            return f'{end_year:04d}-{end_month:02d}'
    return None


def _parse_number(cell: str) -> float | None:
    """Strip whitespace, quotes, and thousands commas; return float or None."""
    s = cell.strip().strip('"').replace(',', '').strip()
    if not s or s in ('-', '－'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fetch_csv(n: int) -> tuple[int, bytes]:
    url = BASE_URL.format(n=n)
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        resp = client.get(url)
        return resp.status_code, resp.content


def _parse_snapshot(blob: bytes) -> tuple[str | None, list[dict]]:
    """Return (period, [rows]) parsed from one CSV blob.

    Returns (None, []) for unrecognised formats (e.g. when the page server
    returns an HTML error body with a 200 status, which happens at the
    edges of the numbering range).
    """
    text = blob.decode('utf-8-sig', errors='replace')
    # Some snapshots have stray embedded newlines inside fields that aren't
    # quoted (e.g. the quarterly-summary CSVs from a couple of months in
    # 2021). newline='' makes csv.reader handle them as part of the field.
    reader = csv.reader(io.StringIO(text, newline=''))
    rows = list(reader)
    if len(rows) < 2:
        return None, []
    period = _parse_period_from_header(rows[0])
    if not period:
        return None, []
    parsed = []
    for row in rows[1:]:
        if len(row) < 4 or not row[0].strip():
            continue
        industry_zh = row[0].strip()
        # MAC sometimes emits a trailing blank "total" row; skip lines with
        # all-blank metric columns.
        cases = _parse_number(row[1])
        amount = _parse_number(row[2])
        share  = _parse_number(row[3])
        if cases is None and amount is None and share is None:
            continue
        parsed.append({
            'industry_zh': industry_zh,
            'cases':       int(cases) if cases is not None else None,
            'amount_usd_k': amount,
            'amount_share_pct': share,
        })
    return period, parsed


DIRECTION = 'prc_to_tw'

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


def scrape_mac_invest_industry_inbound() -> dict:
    """Fetch all available MAC 7478 snapshots, idempotent. Returns counts."""
    conn = get_connection()
    snapshots = 0
    rows_written = 0
    misses = 0  # consecutive 404s before we conclude "end of range"

    for n in range(FIRST_N, PROBE_MAX + 1):
        try:
            status, blob = _fetch_csv(n)
        except Exception as e:
            print(f'[MAC 7478] fetch error at n={n}: {e}')
            continue

        if status == 404:
            misses += 1
            # Three consecutive 404s = we're past the last snapshot.
            if misses >= 3:
                break
            continue
        if status != 200:
            print(f'[MAC 7478] unexpected status {status} at n={n}')
            continue
        misses = 0

        period, rows = _parse_snapshot(blob)
        if not period or not rows:
            continue

        url = BASE_URL.format(n=n)
        params = [
            (DIRECTION, period, r['industry_zh'], INDUSTRY_EN.get(r['industry_zh']),
             r['cases'], r['amount_usd_k'], r['amount_share_pct'], url)
            for r in rows
        ]
        conn.executemany(_UPSERT_SQL, params)
        snapshots += 1
        rows_written += len(params)

    conn.commit()
    conn.close()

    counts = {'snapshots': snapshots, 'rows_written': rows_written}
    print(f'[MAC 7478] {counts}')
    return counts


if __name__ == '__main__':
    scrape_mac_invest_industry_inbound()
