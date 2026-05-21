"""One-off backfill of pre-2019 MAC investment-by-industry snapshots.

MAC's open-data feed for datasets 7473 and 7478 only exposes CSVs from
period 316 (≈ 2019-06) onwards. Earlier history (periods 285-315,
≈ 2016-11 to 2019-05) is bundled in a single archive:

    https://www.mac.gov.tw/big5/data/CSESM/285-315.zip

That URL is under MAC's Cloudflare-protected /CSESM/*.zip family and
can't be downloaded server-side; for this run, the archive was
downloaded manually and unzipped to /tmp/csesm_old/285-315/. Each
period subdirectory contains numbered table CSVs:
    9.csv  — TW → PRC outbound by industry (matches MAC 7473)
    12.csv — PRC → TW inbound by industry (matches MAC 7478)

The OLD CSV format is incompatible with the modern scraper:
  * Multi-line header rows with English row interleaved
  * Industry names combine Chinese and English with an embedded newline
  * Encoding is Big5 (not UTF-8 with BOM as the modern CSVs are)
  * Table 9 packs four period groups into one row (prior month,
    reporting month, YTD, cumulative-since-1991) — same shape as
    modern outbound but at different column offsets.
  * Table 12 is a single cumulative snapshot whose period is encoded
    in row 2 ("(2009年6月至YYYY年M月/Jun. YYYY-...)").

We extract the cumulative-since-N column from each and write into
`investment_by_industry` with the same upserts as the live scrapers.
Idempotent — safe to re-run.
"""
import csv
import io
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scraper.utils.db import get_connection
from scraper.scrapers.mac_invest_industry_inbound import INDUSTRY_EN
from scraper.scrapers.mac_invest_industry_outbound import INDUSTRY_EN_ALL

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ARCHIVE_ROOT = '/tmp/csesm_old/285-315'
ARCHIVE_URL  = 'https://www.mac.gov.tw/big5/data/CSESM/285-315.zip'

# Table 9 (outbound) header pattern — same as modern:
_T9_CUM_RE  = re.compile(r'1991-(\d{4})年(\d{1,2})月累計')
# Table 12 (inbound) cumulative range pattern — in row 2:
_T12_CUM_RE = re.compile(r'至(\d{4})年(\d{1,2})月')


def _parse_number(cell):
    s = cell.strip().strip('"').replace(',', '').strip()
    if not s or s in ('-', '－'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _clean_industry(raw):
    """Industry names in old format are 'Chinese<sep>English' where sep is
    either a newline OR multiple spaces. Strip everything from the first
    ASCII letter or excess whitespace onward, returning the Chinese only."""
    if not raw:
        return None
    # Split on newline first (multi-line variant)
    zh = raw.split('\n')[0].strip()
    # Then split on multiple spaces (single-line variant where English is
    # concatenated with spaces)
    zh = re.split(r'\s{2,}', zh)[0].strip()
    # Finally drop any trailing single-space+English-letter pattern
    zh = re.sub(r'\s+[A-Za-z].*$', '', zh).strip()
    return zh


# Industry-name strings we should never persist (totals / headers that
# can leak through if the row layout drifts).
# Note: '其他' and '其他產業' are LEGITIMATE industry categories in MAC's
# data (a catch-all bucket); only true totals are blacklisted.
_INDUSTRY_BLACKLIST = {'合計', '總計', '小計', '行業', 'Industry'}


def _is_total_or_header(zh):
    if not zh:
        return True
    if zh in _INDUSTRY_BLACKLIST:
        return True
    if zh.startswith('總') or zh.startswith('合'):
        return True
    return False


def _read_csv_big5(path):
    with open(path, 'rb') as f:
        text = f.read().decode('big5', errors='replace')
    return list(csv.reader(io.StringIO(text, newline='')))


# ── Table 9: outbound (TW → PRC) ────────────────────────────────────────

def parse_table9(rows):
    """Return (period, [{industry_zh, cases, amount_usd_k, share}]).

    Layout (1-indexed for clarity):
       row 3 has period labels in groups of 3 columns each: prior month,
       reporting month, YTD, cumulative. The cumulative cell is the
       *first* cell of its group; we scan row 3 for the 1991-... pattern.
       Data begins at row 7 (English column-header row is row 6).
    """
    if len(rows) < 8:
        return None, []
    header_row = rows[3]
    cum_idx = None
    period = None
    for i, cell in enumerate(header_row):
        m = _T9_CUM_RE.search(cell)
        if m:
            cum_idx = i
            period = f'{int(m.group(1)):04d}-{int(m.group(2)):02d}'
            break
    if cum_idx is None:
        return None, []
    cases_col  = cum_idx
    amount_col = cum_idx + 1
    share_col  = cum_idx + 2

    parsed = []
    for row in rows[7:]:
        if not row or not row[0].strip():
            continue
        industry = _clean_industry(row[0])
        if _is_total_or_header(industry):
            continue
        if len(row) <= share_col:
            continue
        cases  = _parse_number(row[cases_col])
        amount = _parse_number(row[amount_col])
        share  = _parse_number(row[share_col])
        if cases is None and amount is None and share is None:
            continue
        parsed.append({
            'industry_zh':      industry,
            'cases':            int(cases) if cases is not None else None,
            # Outbound unit is 百萬美元; normalise to thousands USD.
            'amount_usd_k':     amount * 1000 if amount is not None else None,
            'amount_share_pct': share,
        })
    return period, parsed


# ── Table 12: inbound (PRC → TW) ─────────────────────────────────────────

def parse_table12(rows):
    """Return (period, [rows]). Single cumulative snapshot whose end
    period is encoded in row 2 (`(2009年6月至YYYY年M月/...)`)."""
    if len(rows) < 6:
        return None, []
    period_cell = rows[2][0] if rows[2] else ''
    m = _T12_CUM_RE.search(period_cell)
    if not m:
        return None, []
    period = f'{int(m.group(1)):04d}-{int(m.group(2)):02d}'

    parsed = []
    # Data starts after header rows — find the first row whose col 0
    # looks like an industry name (non-empty, not a header keyword).
    for row in rows:
        if not row or not row[0].strip():
            continue
        first = row[0].strip()
        if first.startswith('表') or first.startswith('Table') or first.startswith('('):
            continue
        if '行業' in first or first.lower().startswith('industry'):
            continue
        if len(row) < 4:
            continue
        industry = _clean_industry(row[0])
        if _is_total_or_header(industry):
            continue
        cases  = _parse_number(row[1])
        amount = _parse_number(row[2])
        share  = _parse_number(row[3])
        if cases is None and amount is None and share is None:
            continue
        parsed.append({
            'industry_zh':      industry,
            'cases':            int(cases) if cases is not None else None,
            # Inbound unit is 千美元 — already what we store.
            'amount_usd_k':     amount,
            'amount_share_pct': share,
        })
    return period, parsed


# ── Upsert ───────────────────────────────────────────────────────────────

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


def main():
    if not os.path.isdir(ARCHIVE_ROOT):
        print(f'Archive not unpacked at {ARCHIVE_ROOT}. Expected layout: <root>/<period>/<table>.csv')
        sys.exit(1)

    conn = get_connection()
    counts = {'outbound_snapshots': 0, 'outbound_rows': 0,
              'inbound_snapshots': 0, 'inbound_rows': 0}

    for period_dir in sorted(os.listdir(ARCHIVE_ROOT)):
        full_period_dir = os.path.join(ARCHIVE_ROOT, period_dir)
        if not os.path.isdir(full_period_dir) or not period_dir.isdigit():
            continue

        # Outbound (table 9)
        path9 = os.path.join(full_period_dir, '9.csv')
        if os.path.exists(path9):
            rows9 = _read_csv_big5(path9)
            period, items = parse_table9(rows9)
            if period and items:
                params = [
                    ('tw_to_prc', period, r['industry_zh'],
                     INDUSTRY_EN_ALL.get(r['industry_zh']),
                     r['cases'], r['amount_usd_k'], r['amount_share_pct'],
                     ARCHIVE_URL)
                    for r in items
                ]
                conn.executemany(_UPSERT_SQL, params)
                counts['outbound_snapshots'] += 1
                counts['outbound_rows']      += len(params)

        # Inbound (table 12)
        path12 = os.path.join(full_period_dir, '12.csv')
        if os.path.exists(path12):
            rows12 = _read_csv_big5(path12)
            period, items = parse_table12(rows12)
            if period and items:
                params = [
                    ('prc_to_tw', period, r['industry_zh'],
                     INDUSTRY_EN.get(r['industry_zh']),
                     r['cases'], r['amount_usd_k'], r['amount_share_pct'],
                     ARCHIVE_URL)
                    for r in items
                ]
                conn.executemany(_UPSERT_SQL, params)
                counts['inbound_snapshots'] += 1
                counts['inbound_rows']      += len(params)

    conn.commit()
    conn.close()
    print(f'[backfill] {counts}')


if __name__ == '__main__':
    main()
