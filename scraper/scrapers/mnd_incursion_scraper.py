"""MND incursion scraper.

Pulls Taiwan MND's daily "中共解放軍臺海周邊海、空域動態" reports from
`mnd.gov.tw/news/plaactlist/<page>` listing and the per-entry detail pages
under `/news/plaact/<id>`. Writes one row per reporting day to
`pla_incursions` with source='mnd'.

The reporting day in MND's convention is the END of the 0600-0600 window
(e.g. a report titled 115.05.22 covers activity from 05/21 0600 to 05/22
0600). We use the listing-page date as the canonical `date` value.

Text-parse contract (post-2022 wording, observed live):

    迄0600時止，偵獲共機N架次（逾越中線進入<zones>空域M架次）、
    共艦K艘及公務船L艘，持續在臺海周邊活動。

Two parenthetical forms exist:
  * `（逾越中線進入X空域M架次）` — M aircraft crossed the median line.
  * `（進入X空域M架次）`         — M aircraft entered TW-claimed airspace
                                   from elsewhere (no median crossing).

Both are recorded as `aircraft_intruded = M` since both are operationally
incursions; the distinction is preserved verbatim in `raw_text`.

Idempotent — re-running upserts on (date, source).
"""
import asyncio
import os
import re
import sys
from datetime import datetime, timezone, timedelta

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection
from scraper.utils.http import make_async_client
from scraper.utils.dates import roc_date_to_iso

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

MAX_AGE = timedelta(days=180)
BASE = 'https://www.mnd.gov.tw'
LIST_URL = BASE + '/news/plaactlist/{page}'
MAX_PAGES = 25  # safety cap; 180 days ≈ 20 pages at ~9 entries each

ZONE_MAP = [
    ('北部', 'N'),
    ('中部', 'C'),
    ('南部', 'S'),
    ('西南', 'SW'),
    ('東南', 'SE'),
    ('東部', 'E'),
]

LIST_ITEM_RE = re.compile(
    r'<a\s+href="(news/plaact/(\d+))"\s+class="news_list">.*?'
    r'<div class="date[^"]*">(\d{3})\.(\d{2})\.(\d{2})</div>',
    re.DOTALL,
)

_UPSERT_SQL = """
INSERT INTO pla_incursions
    (date, aircraft_total, aircraft_intruded, aircraft_zones,
     vessels_total, coast_guard_total, source, source_url, raw_text)
VALUES (?, ?, ?, ?, ?, ?, 'mnd', ?, ?)
ON CONFLICT(date, source) DO UPDATE SET
    aircraft_total    = excluded.aircraft_total,
    aircraft_intruded = excluded.aircraft_intruded,
    aircraft_zones    = excluded.aircraft_zones,
    vessels_total     = excluded.vessels_total,
    coast_guard_total = excluded.coast_guard_total,
    source_url        = excluded.source_url,
    raw_text          = excluded.raw_text,
    scraped_at        = CURRENT_TIMESTAMP
"""


def _roc_to_iso(roc_y: str, m: str, d: str) -> str:
    return roc_date_to_iso(roc_y, m, d)


def _extract_zones(s: str) -> str | None:
    codes = [code for zh, code in ZONE_MAP if zh in s]
    return ','.join(codes) if codes else None


def parse_summary(text: str) -> dict:
    """Extract structured counts from the maincontent paragraph text.

    Public so the test fixture (or a future backfill script that uses the
    same wording) can reuse it.
    """
    out = {
        'aircraft_total': None,
        'aircraft_intruded': None,
        'aircraft_zones': None,
        'vessels_total': None,
        'coast_guard_total': None,
    }

    # Quiet days are reported either with 未偵獲共機 ("no PLA aircraft detected")
    # or by omitting the 共機 sentence entirely (only 共艦 reported). Both mean
    # zero — record as 0 so the daily series stays continuous.
    if '未偵獲共機' in text or '共機' not in text:
        out['aircraft_total'] = 0
        out['aircraft_intruded'] = 0
    else:
        # Singular sortie days drop the 次 suffix (共機1架 instead of 1架次).
        m = re.search(r'共機(\d+)架次?', text)
        if m:
            out['aircraft_total'] = int(m.group(1))

    # Prefer median-crossing wording; fall back to ADIZ entry. The zone list
    # sits between 進入 and 空域 in either case. Same 架次/架 variation applies.
    m = re.search(r'逾越中線進入([^空（）]+)空域(\d+)架次?', text)
    if m:
        out['aircraft_intruded'] = int(m.group(2))
        out['aircraft_zones'] = _extract_zones(m.group(1))
    else:
        m = re.search(r'進入([^空（）]+)空域(\d+)架次?', text)
        if m:
            out['aircraft_intruded'] = int(m.group(2))
            out['aircraft_zones'] = _extract_zones(m.group(1))
        elif out['aircraft_total'] == 0:
            out['aircraft_intruded'] = 0

    m = re.search(r'共艦(\d+)艘', text)
    if m:
        out['vessels_total'] = int(m.group(1))

    m = re.search(r'公務船(\d+)艘', text)
    if m:
        out['coast_guard_total'] = int(m.group(1))

    return out


def _existing_dates(conn) -> set:
    rows = conn.execute(
        "SELECT date FROM pla_incursions WHERE source = 'mnd'"
    ).fetchall()
    return {r['date'] for r in rows}


async def _fetch_detail(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        resp = await client.get(url)
        resp.encoding = 'utf-8'
        if resp.status_code != 200:
            return None
    except Exception as e:
        print(f"    fetch error for {url}: {e}")
        return None
    soup = BeautifulSoup(resp.text, 'html.parser')
    div = soup.select_one('div.maincontent')
    if not div:
        return None
    # Collapse to single-line text with normalised whitespace.
    return re.sub(r'\s+', ' ', div.get_text(' ', strip=True))


async def scrape_mnd_incursions() -> int:
    """Walk MND PLA activity listing pages, upsert each report. Returns row count written."""
    print("\nScraping: MND PLA incursions")
    conn = get_connection()
    existing = _existing_dates(conn)
    cutoff = (datetime.now(timezone.utc) - MAX_AGE).date().isoformat()

    written = 0
    stop_walk = False

    async with make_async_client() as client:
        for page in range(1, MAX_PAGES + 1):
            if stop_walk:
                break
            list_url = LIST_URL.format(page=page)
            try:
                resp = await client.get(list_url)
                resp.encoding = 'utf-8'
            except Exception as e:
                print(f"  list page {page} error: {e}")
                break
            if resp.status_code != 200:
                print(f"  list page {page}: status {resp.status_code}")
                break

            items = LIST_ITEM_RE.findall(resp.text)
            if not items:
                break

            new_on_page = 0
            for rel_url, _id, roc_y, mm, dd in items:
                iso_date = _roc_to_iso(roc_y, mm, dd)
                if iso_date < cutoff:
                    # past 180-day window — stop walking entirely
                    stop_walk = True
                    break
                if iso_date in existing:
                    continue
                full_url = f"{BASE}/{rel_url}"
                text = await _fetch_detail(client, full_url)
                if not text:
                    print(f"  {iso_date}: no maincontent at {full_url}")
                    continue
                parsed = parse_summary(text)
                if parsed['aircraft_total'] is None and parsed['vessels_total'] is None:
                    # Unparseable wording — log raw and skip. Better to surface
                    # than silently insert nulls everywhere.
                    print(f"  {iso_date}: could not parse counts; text snippet: {text[:200]}")
                    continue
                conn.execute(_UPSERT_SQL, (
                    iso_date,
                    parsed['aircraft_total'],
                    parsed['aircraft_intruded'],
                    parsed['aircraft_zones'],
                    parsed['vessels_total'],
                    parsed['coast_guard_total'],
                    full_url,
                    text,
                ))
                existing.add(iso_date)
                written += 1
                new_on_page += 1
                print(f"  + {iso_date}: aircraft={parsed['aircraft_total']} "
                      f"intruded={parsed['aircraft_intruded']} "
                      f"zones={parsed['aircraft_zones']} "
                      f"vessels={parsed['vessels_total']} "
                      f"coast_guard={parsed['coast_guard_total']}")

            conn.commit()
            if new_on_page == 0 and page > 1:
                # We've reached pages whose entries we already have — stop.
                break

    conn.close()
    print(f"  MND incursions: wrote {written} new rows")
    return written


if __name__ == '__main__':
    asyncio.run(scrape_mnd_incursions())
