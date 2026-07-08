"""TW NIA cross-strait population scraper.

Pulls two annual datasets from data.gov.tw / 內政部移民署:

  * **167829** — 大陸地區人民、港澳居民、無戶籍國民來臺居留及定居人數
    Annual flow: NEW residence permits and NEW settlement permits granted
    each year. Eight columns covering mainland / HK / Macao / stateless.

  * **13503** — 外籍配偶人數與大陸（含港澳配偶人數）─按區域別、性別分
    Cumulative stock: total spouses by region+gender at each snapshot.
    We only ingest the country/region totals (sum-of-all-cities rows
    matching "區域別總計/性別總計"), since the per-city breakdown is
    overkill for the dashboard.

Both write to `cross_strait_population` with direction='prc_in_taiwan'.
Idempotent — re-running upserts on (direction, metric, period, period_type).
"""
import csv
import io
import os
import re
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection
from scraper.utils.dates import roc_label_year, roc_year_to_gregorian

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DATASET_167829_URL = (
    'https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/'
    '6FE5F180-470E-45E8-B5AC-8CF453F54FAF/resource/'
    '0B0CCB09-2E52-485A-8A69-49D814DF8D4A/download'
)
DATASET_13503_URL = (
    'https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/'
    'AE631767-27F1-437D-B1F1-4429CB60E58E/resource/'
    '8923C9F0-ABA1-4E18-B2CF-C3D99E85AE96/download'
)


def _fetch(url: str) -> bytes:
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content


def _parse_number(cell: str) -> int | None:
    s = (cell or '').strip().strip('"').replace(',', '')
    if not s or s in ('-', '－', 'N/A'):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _roc_year_to_gregorian(label: str) -> int | None:
    """Convert ROC year label like '112年' to 2023."""
    return roc_label_year(label)


_UPSERT_SQL = """
INSERT INTO cross_strait_population
    (direction, metric, period, period_type, value, unit, source, source_url, notes)
VALUES (?, ?, ?, ?, ?, 'persons', ?, ?, ?)
ON CONFLICT(direction, metric, period, period_type) DO UPDATE SET
    value      = excluded.value,
    source     = excluded.source,
    source_url = excluded.source_url,
    notes      = excluded.notes,
    scraped_at = CURRENT_TIMESTAMP
"""


def _ingest_167829(conn) -> int:
    """Annual flow: 居留 (residence) and 定居 (settlement) new permits
    granted each year for mainland / HK / Macao / stateless cohorts."""
    text = _fetch(DATASET_167829_URL).decode('utf-8-sig', errors='replace')
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return 0

    # Header layout (column indexes):
    #   0: 年度
    #   1: 大陸地區人民_居留人數      | 2: 大陸地居人民_定居人數
    #   3: 香港居民_居留人數          | 4: 香港居民_定居人數
    #   5: 澳門居民_居留人數          | 6: 澳門居民_定居人數
    #   7: 無戶籍國民_居留人數        | 8: 無戶籍國民_定居人數
    # We only ingest mainland (cols 1, 2). HK/Macao/stateless aren't
    # cross-strait per se. NB: dataset misspells 大陸地"區" as 大陸地"居"
    # in the 定居 column header — header isn't actually used; we go by index.
    COLS = [
        (1, 'prc_in_taiwan', 'permits_annual_residence',
         'Mainland-Chinese-citizen NEW residence permits granted in Taiwan that year (per TW NIA dataset 167829).'),
        (2, 'prc_in_taiwan', 'permits_annual_settlement',
         'Mainland-Chinese-citizen NEW settlement permits granted in Taiwan that year (per TW NIA dataset 167829). Settlement is a step beyond residence — closer to permanent residency.'),
    ]

    written = 0
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        year = _roc_year_to_gregorian(row[0])
        if not year:
            continue
        for col_idx, direction, metric, notes in COLS:
            if len(row) <= col_idx:
                continue
            value = _parse_number(row[col_idx])
            if value is None:
                continue
            conn.execute(_UPSERT_SQL, (
                direction, metric, str(year), 'annual',
                value, 'TW_NIA_167829', DATASET_167829_URL, notes,
            ))
            written += 1
    return written


def _ingest_13503(conn) -> int:
    """Cumulative spouse stock by region. We only keep the country-level
    totals rows (matching '/區域別總計/性別總計') — the per-county
    breakdown isn't useful at the dashboard level.

    Each snapshot row is labelled like '109年 (1~10月)/...'. The period
    represents cumulative since 1987 through that month. We store the
    snapshot at the YYYY-MM that the label implies (using the end month
    of the range when one is given, otherwise December).
    """
    text = _fetch(DATASET_13503_URL).decode('utf-8-sig', errors='replace')
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if len(rows) < 2:
        return 0
    header = rows[0]
    # Find indexes for the columns we want
    try:
        idx_mainland = header.index('大陸配偶_統計')
        idx_hkmo     = header.index('港澳配偶_統計')
    except ValueError:
        return 0

    written = 0
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        label = row[0].strip().strip('"')
        # Only the country/gender-total summary rows; skip per-city detail
        if '區域別總計' not in label or '性別總計' not in label:
            continue
        # Extract period: ROC year + optional month range
        m = re.match(r'\s*(\d{1,3})年(?:\s*\((\d{1,2})~(\d{1,2})月\))?', label)
        if not m:
            continue
        year = roc_year_to_gregorian(m.group(1))
        end_month = int(m.group(3)) if m.group(3) else 12
        period = f'{year:04d}-{end_month:02d}'

        mainland = _parse_number(row[idx_mainland])
        hkmo     = _parse_number(row[idx_hkmo])

        notes = (
            'Cumulative spouse stock from 1987 through this snapshot '
            '(per TW NIA dataset 13503, country totals row).'
        )
        if mainland is not None:
            conn.execute(_UPSERT_SQL, (
                'prc_in_taiwan', 'spouses_cumulative', period, 'monthly',
                mainland, 'TW_NIA_13503', DATASET_13503_URL,
                'Mainland Chinese spouses, ' + notes,
            ))
            written += 1
        if hkmo is not None:
            conn.execute(_UPSERT_SQL, (
                'hk_macao_in_taiwan', 'spouses_cumulative', period, 'monthly',
                hkmo, 'TW_NIA_13503', DATASET_13503_URL,
                'Hong Kong / Macao spouses, ' + notes,
            ))
            written += 1
    return written


def scrape_tw_nia_population() -> dict:
    conn = get_connection()
    counts = {
        'nia_167829_rows': _ingest_167829(conn),
        'nia_13503_rows':  _ingest_13503(conn),
    }
    conn.commit()
    conn.close()
    print(f'[TW NIA pop] {counts}')
    return counts


if __name__ == '__main__':
    scrape_tw_nia_population()
