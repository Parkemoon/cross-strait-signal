"""CIFER snapshot tracker — automates the manual count Ed captured on 2026-05-21.

PRC's CIFER (China Import Food Enterprises Registration) portal at
`ciferquery.singlewindow.cn` is browser-gated (the API behind the form
returns generic error pages to direct POSTs from our server — see
`cifer-methodology.md` in agent memory). This script drives a real
headless Chromium via Playwright to:

  1. Open the landing page.
  2. Switch to the 港澳台 tab (PRC's CIFER schema files Taiwan there,
     not under 境外/foreign — itself an analytical artefact).
  3. Set country = 中国台湾 in the autocomplete picker.
  4. Run two queries: status='P' (暫停進口 / suspended) and status='R'
     (有效 / valid), capturing the result count from the pagination
     header for each.
  5. Persist both counts as cifer_snapshots rows tagged with today's
     date. Idempotent — re-running on the same day upserts the same
     row.

Once a month is plenty. The trend matters more than the absolute
freshness; rate-limiting also keeps us off PRC bot-detection radars.
Run via cron or `python -m scraper.scrapers.cifer_snapshot_scraper`.
"""
import datetime as _dt
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

CIFER_URL = 'https://ciferquery.singlewindow.cn/'
TAIWAN_QUERY = '中国台湾'

# Map CIFER form `status` codes to our normalised labels.
STATUSES = [
    {'code': 'P', 'tag': 'suspended', 'zh': '暫停進口'},
    {'code': 'R', 'tag': 'valid',     'zh': '有效'},
]

# Pagination summary on results page reads like "共 1291 条记录" — capture
# the integer regardless of where in the page footer it lands.
_COUNT_RE = re.compile(r'共\s*([0-9,]+)\s*条记录')


def _parse_count(page_text: str) -> int | None:
    m = _COUNT_RE.search(page_text)
    if not m:
        return None
    try:
        return int(m.group(1).replace(',', ''))
    except ValueError:
        return None


def _click_hktw_tab(page) -> None:
    """Switch the form to the 港澳台 (HK/Macao/Taiwan) section.

    The site's JS handler is exposed globally as tabClick('1'); we
    invoke it directly to avoid CSS-selector flake on the tab strip.
    """
    page.evaluate("tabClick('1')")
    # Give the DOM a moment to swap visibility before we touch the form.
    page.wait_for_timeout(400)


def _pick_taiwan_country(page) -> None:
    """Drive the autocompleter at #countryName → select 中国台湾.

    The placeholder hints at 按空格键检索 — the autocompleter opens on a
    space keystroke, after which the user types a substring and clicks
    the matching suggestion. We trigger that flow manually.
    """
    # The 港澳台 section reuses #countryName (and the hidden #country).
    page.locator('#countryName').fill('')   # clear any stale value
    page.locator('#countryName').click()
    page.keyboard.press('Space')
    page.wait_for_timeout(200)
    page.locator('#countryName').type(TAIWAN_QUERY, delay=40)
    # The autocompleter renders results in a list adjacent to the
    # input; click the first match whose text contains 台湾.
    suggestion = page.locator('text=中国台湾').first
    suggestion.wait_for(timeout=5000)
    suggestion.click()
    # Sanity-check that the hidden code got populated
    page.wait_for_timeout(200)


def _set_status_and_query(page, status_code: str) -> int | None:
    page.locator('#status').select_option(value=status_code)
    # The submit button has id="Action" (per the HTML markup); fall
    # back to the 查询 text label if anything moves.
    submit = page.locator('#Action')
    if submit.count() == 0:
        submit = page.locator('button:has-text("查询")')
    submit.first.click()
    # Wait for the results pagination to appear. The site renders
    # "共 X 条记录" inside the bootstrap-table footer; poll for up to 15s.
    for _ in range(30):
        text = page.content()
        if '共' in text and '条记录' in text:
            count = _parse_count(text)
            if count is not None:
                return count
        page.wait_for_timeout(500)
    return _parse_count(page.content())


_UPSERT_SQL = """
INSERT INTO cifer_snapshots (snapshot_date, status, status_zh, count, notes)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(snapshot_date, status) DO UPDATE SET
    count      = excluded.count,
    notes      = excluded.notes,
    scraped_at = CURRENT_TIMESTAMP
"""


def scrape_cifer_snapshot() -> dict:
    """Drive the CIFER portal and persist today's counts for both statuses."""
    from playwright.sync_api import sync_playwright

    today = _dt.date.today().isoformat()
    results: dict[str, int | None] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'],
        )
        try:
            context = browser.new_context(
                user_agent=('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                            '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'),
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
            )
            page = context.new_page()
            page.goto(CIFER_URL, wait_until='networkidle', timeout=60_000)
            _click_hktw_tab(page)
            _pick_taiwan_country(page)
            for status in STATUSES:
                count = _set_status_and_query(page, status['code'])
                results[status['tag']] = count
                # Brief pause between queries to avoid hammering the
                # portal harder than a casual human would.
                time.sleep(2)
        finally:
            browser.close()

    conn = get_connection()
    notes_blob = (
        f"Captured via Playwright/Chromium against {CIFER_URL} 港澳台 tab, "
        f"country={TAIWAN_QUERY}."
    )
    for status in STATUSES:
        count = results.get(status['tag'])
        if count is None:
            print(f"[CIFER] {status['tag']}: failed to capture count, skipping")
            continue
        conn.execute(_UPSERT_SQL,
                     (today, status['tag'], status['zh'], count, notes_blob))
    conn.commit()
    conn.close()

    print(f"[CIFER] {today} → {results}")
    return {'snapshot_date': today, **{k: v for k, v in results.items()}}


if __name__ == '__main__':
    scrape_cifer_snapshot()
