"""Cross-strait trade access scraper — populates the ``trade_access`` table.

Brings together four independent sources that together describe what each
side allows the other to import, and at what tariff:

  * **BOFT dataset 22674** (大陸物品不准許輸入項目) — items TW *bans* from PRC.
    Status: ``banned``, direction: ``tw_imports_from_prc``.
  * **BOFT dataset 22675** (大陸物品有條件准許輸入項目) — items TW allows
    *conditionally* from PRC. Status: ``conditional``, direction: same.
  * **MoF Customs ECFA correspondence** (2024-2024 對照表, .ods) — the early
    harvest list with paired TW↔PRC 8-digit HS codes. We write *two* rows
    per entry: one ``ecfa_active`` row for TW→PRC (PRC's preferential import)
    and one for PRC→TW. Suspensions below downgrade matching rows to
    ``ecfa_suspended``.
  * **MoF (PRC) State Council Tariff Commission suspension PDFs** — Wave 1
    (Dec 2023, 12 items) and Wave 2 (May 2024, 134 items). Each row marks
    a ``prc_imports_from_tw`` HS code as ``ecfa_suspended``.

Plus the curated ``prc_trade_bans.json`` for PRC's targeted bans on TW
agricultural/food goods (pineapples, grouper, etc.) — these write
``banned`` rows for direction ``prc_imports_from_tw``.

Insertion order matters: ECFA active rows go in first, then suspension PDFs
overwrite their status to ``ecfa_suspended``, then curated PRC bans
overwrite to ``banned`` where applicable.

Re-runs are idempotent — we ``INSERT … ON CONFLICT(direction, hs_code) DO
UPDATE`` so revised tariff schedules or new ban announcements propagate.
"""
import csv
import io
import json
import os
import re
import sys
from typing import Iterable

import httpx
import pandas as pd
import pdfplumber

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Source URLs ────────────────────────────────────────────────────────────
BOFT_BANNED_URL      = 'https://www.trade.gov.tw/OpenData/getOpenData.aspx?oid=BBA6A9A8900F2C46'
BOFT_CONDITIONAL_URL = 'https://www.trade.gov.tw/OpenData/getOpenData.aspx?oid=CF7F90DCBCD5718D'
ECFA_ODS_URL         = 'https://web.customs.gov.tw/download/4489d39d00b24c8f90f5b4ee2bdd6acf'
# Wave 2 (134 items, effective 2024-06-15) — the canonical PDF on gss.mof.gov.cn
MOF_PRC_SUSP_W2_URL  = 'https://gss.mof.gov.cn/gzdt/zhengcefabu/202405/P020240531308646828162.pdf'

# Wave 1 (12 petrochemical items, effective 2024-01-01, MoF Announcement 2023 No. 9).
# The PDF URL has not been findable via public search, so we carry the list inline
# from contemporary reporting. Update when the canonical PDF surfaces.
MOF_PRC_SUSP_W1_ITEMS = [
    ('29012100', '丙烯',                      'Propylene'),
    ('29012400', '丁二烯',                    '1,3-Butadiene'),
    ('29012990', '異戊二烯',                  'Isoprene'),
    ('29024100', '鄰二甲苯',                  'o-Xylene'),
    ('29024200', '間二甲苯',                  'm-Xylene'),
    ('29024300', '對二甲苯',                  'p-Xylene'),
    ('29024400', '混合二甲苯異構體',          'Mixed xylene isomers'),
    ('38170010', '十二烷基苯',                'Dodecylbenzene'),
    ('29031300', '氯仿（三氯甲烷）',          'Chloroform (trichloromethane)'),
    ('29032100', '氯乙烯',                    'Vinyl chloride'),
    ('40027000', '初級形狀的乙烯丙烯共聚物',  'Ethylene-propylene rubber, primary form'),
    ('39019090', '其他初級形狀的烯烴聚合物',  'Other olefin polymers, primary form'),
]

# BOFT (trade.gov.tw) returns a Cloudflare-style block page without a Referer.
# data.gov.tw's dataset page is a stable referer that passes the check.
BOFT_HEADERS = {
    'Referer': 'https://data.gov.tw/dataset/22674',
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
}

CURATED_BANS_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'processors', 'prc_trade_bans.json'
)

# ── Helpers ────────────────────────────────────────────────────────────────

def _normalise_hs(raw: str) -> str:
    """Strip non-digits and pad/truncate to 8 digits.

    BOFT codes carry a check digit and EX marker (e.g. ``0102.29.00.00-4``
    or ``0208.40.10.10-8EX``). We keep the first 8 numeric digits, which
    matches the HS-8 used by both ECFA tables and PRC customs.
    """
    digits = re.sub(r'\D', '', raw or '')
    return digits[:8] if len(digits) >= 8 else digits


def _fetch(url: str, headers: dict | None = None) -> bytes:
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(url, headers=headers or {})
        resp.raise_for_status()
        return resp.content


# ── BOFT: banned + conditional ─────────────────────────────────────────────

def _fetch_boft_csv(url: str) -> list[dict]:
    """Return a list of {hs_code, product_zh, product_en, effective_date}.

    Both BOFT datasets share the same 5-column shape; the 4th column is
    either ``輸入規定`` (banned list) or ``特別規定`` (conditional list)
    and we capture it as a freeform note.
    """
    # BOFT serves UTF-8 with BOM; the visually-Big5-corrupted header in some
    # browsers is just BOM rendering, not actual Big5 encoding.
    text = _fetch(url, headers=BOFT_HEADERS).decode('utf-8-sig', errors='replace')
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []
    items = []
    for row in rows[1:]:
        if len(row) < 5:
            continue
        hs = _normalise_hs(row[0])
        if not hs:
            continue
        items.append({
            'hs_code': hs,
            'product_zh': row[1].strip() or None,
            'product_en': row[2].strip() or None,
            'rule_code': row[3].strip() or None,
            'effective_date_roc': row[4].strip() or None,
        })
    return items


def _roc_date_to_iso(roc: str | None) -> str | None:
    """Convert ROC date like '1021129' or '0970319' to '2013-11-29' / '2008-03-19'."""
    if not roc:
        return None
    s = roc.strip()
    if not s.isdigit() or len(s) < 5:
        return None
    # First 2-3 digits are ROC year; the rest is mmdd. ROC years are
    # 3-digit since 100 (=2011). Anything <100 is 2-digit.
    if len(s) == 7:
        year = int(s[:3]) + 1911
        month, day = int(s[3:5]), int(s[5:7])
    elif len(s) == 6:
        year = int(s[:2]) + 1911
        month, day = int(s[2:4]), int(s[4:6])
    else:
        return None
    try:
        return f'{year:04d}-{month:02d}-{day:02d}'
    except (ValueError, TypeError):
        return None


# ── ECFA correspondence (.ods) ─────────────────────────────────────────────

def _fetch_ecfa_correspondence() -> list[dict]:
    """Return paired TW↔PRC entries from the customs correspondence file.

    Sheet shape (header rows skipped): one row per HS pairing. Some rows
    only have one side (continuation rows where the same PRC code maps to
    multiple TW codes — pandas leaves the merged-cell side blank, so we
    forward-fill with the most recently seen non-null value on each side.
    """
    blob = _fetch(ECFA_ODS_URL)
    tmp_path = '/tmp/_ecfa_correspondence.ods'
    with open(tmp_path, 'wb') as f:
        f.write(blob)
    df = pd.read_excel(tmp_path, engine='odf', header=None, skiprows=2)
    df.columns = ['seq', 'prc_hs', 'prc_zh', 'prc_en', 'prc_rate',
                  'tw_ex', 'tw_hs', 'tw_zh', 'tw_en', 'tw_rate', 'remarks']
    # Forward-fill within each side — merged cells in source render as NaN
    for col in ('prc_hs', 'prc_zh', 'prc_en'):
        df[col] = df[col].ffill()
    items = []
    for _, row in df.iterrows():
        prc_hs = _normalise_hs(str(row['prc_hs']) if pd.notna(row['prc_hs']) else '')
        tw_hs  = _normalise_hs(str(row['tw_hs'])  if pd.notna(row['tw_hs'])  else '')
        if not (prc_hs and tw_hs):
            continue
        items.append({
            'prc_hs': prc_hs,
            'prc_zh': str(row['prc_zh']).strip() if pd.notna(row['prc_zh']) else None,
            'prc_en': str(row['prc_en']).strip() if pd.notna(row['prc_en']) else None,
            'tw_hs': tw_hs,
            'tw_zh': str(row['tw_zh']).strip() if pd.notna(row['tw_zh']) else None,
            'tw_en': str(row['tw_en']).strip() if pd.notna(row['tw_en']) else None,
            'remarks': str(row['remarks']).strip() if pd.notna(row['remarks']) else None,
        })
    return items


# ── PRC MoF suspension PDFs ────────────────────────────────────────────────

# Match seq + HS [+ optional name on same line]. Long names wrap to next line,
# so we coalesce continuations until the next row header appears.
_PDF_ROW = re.compile(r'^(\d{1,3})\s+(\d{8})(?:\s+(.+?))?\s*$')
# Footer junk to strip from product names
_PDF_FOOTNOTE_MARKERS = ('注：', '货品简称仅供参考', '《中华人民共和国进出口税则')


def _parse_suspension_pdf(url: str) -> list[dict]:
    """Extract (seq, hs_code, name) rows from a MoF suspension PDF.

    Names can wrap onto multiple lines; we coalesce continuation lines
    (lines that don't start with a row number) into the previous entry.
    """
    blob = _fetch(url)
    tmp_path = f'/tmp/_mof_susp_{abs(hash(url))}.pdf'
    with open(tmp_path, 'wb') as f:
        f.write(blob)
    items = []
    current = None
    with pdfplumber.open(tmp_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ''
            for line in text.split('\n'):
                line = line.strip()
                if not line or '序号' in line or '税则号列' in line or '货品简称' in line:
                    continue
                m = _PDF_ROW.match(line)
                if m:
                    if current:
                        items.append(current)
                    current = {
                        'seq': int(m.group(1)),
                        'hs_code': m.group(2),
                        'product_zh': (m.group(3) or '').strip(),
                    }
                elif current and not line[0].isdigit():
                    # continuation of product name
                    extra = line
                    for marker in _PDF_FOOTNOTE_MARKERS:
                        if marker in extra:
                            extra = extra.split(marker)[0].rstrip()
                            break
                    current['product_zh'] = (current['product_zh'] + extra).strip()
    if current:
        items.append(current)
    # Strip lingering footnote text from last entry
    for it in items:
        for marker in _PDF_FOOTNOTE_MARKERS:
            if marker in it['product_zh']:
                it['product_zh'] = it['product_zh'].split(marker)[0].strip()
    return items


# ── DB write ───────────────────────────────────────────────────────────────

_UPSERT_SQL = """
INSERT INTO trade_access
    (direction, hs_code, product_zh, product_en, status, effective_date,
     source, notes, ban_announcement_url)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(direction, hs_code) DO UPDATE SET
    product_zh           = COALESCE(excluded.product_zh, trade_access.product_zh),
    product_en           = COALESCE(excluded.product_en, trade_access.product_en),
    status               = excluded.status,
    effective_date       = COALESCE(excluded.effective_date, trade_access.effective_date),
    source               = excluded.source,
    notes                = excluded.notes,
    ban_announcement_url = COALESCE(excluded.ban_announcement_url, trade_access.ban_announcement_url),
    scraped_at           = CURRENT_TIMESTAMP
"""


def _upsert(conn, rows: Iterable[tuple]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    conn.executemany(_UPSERT_SQL, rows)
    return len(rows)


# ── Orchestration ──────────────────────────────────────────────────────────

def scrape_trade_access() -> dict:
    """Run all four sources and merge into trade_access. Return counts dict."""
    conn = get_connection()
    counts: dict[str, int] = {}

    # 1. TW banned list (BOFT 22674)
    try:
        banned = _fetch_boft_csv(BOFT_BANNED_URL)
        rows = [
            ('tw_imports_from_prc', it['hs_code'], it['product_zh'], it['product_en'],
             'banned', _roc_date_to_iso(it['effective_date_roc']),
             'BOFT_22674', it['rule_code'], None)
            for it in banned
        ]
        counts['tw_banned'] = _upsert(conn, rows)
    except Exception as e:
        print(f'[trade_access] BOFT banned fetch failed: {e}')
        counts['tw_banned'] = 0

    # 2. TW conditional list (BOFT 22675)
    try:
        conditional = _fetch_boft_csv(BOFT_CONDITIONAL_URL)
        rows = [
            ('tw_imports_from_prc', it['hs_code'], it['product_zh'], it['product_en'],
             'conditional', _roc_date_to_iso(it['effective_date_roc']),
             'BOFT_22675', it['rule_code'], None)
            for it in conditional
            # Don't downgrade a banned row to conditional — banned is stricter
            if it['hs_code'] not in {b['hs_code'] for b in banned}
        ]
        counts['tw_conditional'] = _upsert(conn, rows)
    except Exception as e:
        print(f'[trade_access] BOFT conditional fetch failed: {e}')
        counts['tw_conditional'] = 0

    # 3. ECFA correspondence — write paired rows for both directions
    try:
        ecfa = _fetch_ecfa_correspondence()
        prc_rows, tw_rows = [], []
        for it in ecfa:
            # PRC's preferential import from TW (TW exports to PRC under ECFA)
            prc_rows.append((
                'prc_imports_from_tw', it['prc_hs'], it['prc_zh'], it['prc_en'],
                'ecfa_active', None, 'CUSTOMS_ECFA_2024', it['remarks'], None
            ))
            # TW's preferential import from PRC (PRC exports to TW under ECFA)
            tw_rows.append((
                'tw_imports_from_prc', it['tw_hs'], it['tw_zh'], it['tw_en'],
                'ecfa_active', None, 'CUSTOMS_ECFA_2024', it['remarks'], None
            ))
        counts['ecfa_prc_side'] = _upsert(conn, prc_rows)
        # Skip TW-side ECFA rows where the BOFT banned list already says
        # this HS code is banned — that BOFT signal is stronger.
        existing_banned = {
            row['hs_code'] for row in conn.execute(
                "SELECT hs_code FROM trade_access WHERE direction = 'tw_imports_from_prc' AND status = 'banned'"
            )
        }
        tw_rows = [r for r in tw_rows if r[1] not in existing_banned]
        counts['ecfa_tw_side'] = _upsert(conn, tw_rows)
    except Exception as e:
        print(f'[trade_access] ECFA correspondence fetch failed: {e}')
        counts['ecfa_prc_side'] = counts['ecfa_tw_side'] = 0

    # 4a. Wave 1 (12 items, effective 2024-01-01) — hardcoded list
    rows = [
        ('prc_imports_from_tw', hs, zh, en,
         'ecfa_suspended', '2024-01-01', 'MOF_PRC_SUSP_W1', None,
         'https://gss.mof.gov.cn/gzdt/zhengcefabu/202312/')
        for hs, zh, en in MOF_PRC_SUSP_W1_ITEMS
    ]
    counts['mof_prc_susp_w1'] = _upsert(conn, rows)

    # 4b. Wave 2 (134 items, effective 2024-06-15) — parse MoF PDF
    try:
        susp = _parse_suspension_pdf(MOF_PRC_SUSP_W2_URL)
        rows = [
            ('prc_imports_from_tw', it['hs_code'], it['product_zh'], None,
             'ecfa_suspended', '2024-06-15', 'MOF_PRC_SUSP_W2', None,
             MOF_PRC_SUSP_W2_URL)
            for it in susp
        ]
        counts['mof_prc_susp_w2'] = _upsert(conn, rows)
    except Exception as e:
        print(f'[trade_access] MOF_PRC_SUSP_W2 parse failed: {e}')
        counts['mof_prc_susp_w2'] = 0

    # 5. Curated PRC bans / partial lifts on TW agri/food. Each entry can
    #    declare its own `status` (banned | partial_lift); defaults to banned.
    #    `effective_date` is the date the *current* status took effect
    #    (ban_date for bans; lift_date for partial lifts).
    try:
        with open(CURATED_BANS_PATH, encoding='utf-8') as f:
            curated = json.load(f)
        rows = [
            ('prc_imports_from_tw', _normalise_hs(b['hs_code']),
             b.get('product_zh'), b.get('product_en'),
             b.get('status', 'banned'),
             b.get('effective_date') or b.get('ban_date'),
             'CURATED', b.get('notes'), b.get('announcement_url'))
            for b in curated.get('bans', [])
        ]
        counts['curated_prc_bans'] = _upsert(conn, rows)
    except Exception as e:
        print(f'[trade_access] Curated PRC bans load failed: {e}')
        counts['curated_prc_bans'] = 0

    conn.commit()
    conn.close()

    print(f'[trade_access] Inserted/updated: {counts}')
    return counts


if __name__ == '__main__':
    scrape_trade_access()
