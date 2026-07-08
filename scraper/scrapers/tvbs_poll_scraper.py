"""TVBS Poll Center scraper — Phase 2d pollster-direct ingestion.

TVBS publishes each release as a single multi-page PDF (cover + prose
summary + cross-tabulations + methodology) linked from a date/title table
on the poll-center page. The page itself is client-side rendered so we
use Playwright to enumerate (title, pdf_url) pairs, then httpx +
pdfplumber to lift the prose summary out of the first few pages.

We only ingest the first 4 pages of each PDF — that covers cover,
headline prose, and the start of the question-by-question breakdown.
Later pages are cross-tabulation matrices (party-ID × age × gender)
that add noise without informational gain for the poll-extraction prompt.
Total bytes stay under the 10KB content cap.

Step 3c picks these up via the existing `%民調%` title trigger — every
TVBS poll title ends in 民調 by convention.
"""
import io
import re
import sys
import os
from datetime import datetime, timezone

import httpx
import pdfplumber

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists, save_article
from scraper.utils.http import browser_headers

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

LIST_URL = 'https://www.tvbs.com.tw/poll-center'
PDF_DATE_RE = re.compile(r'/(\d{4})/(\d{8})/')
PDF_PAGES_TO_KEEP = 4


def _published_from_url(url):
    """PDF URLs encode the release date as /YYYY/YYYYMMDD/<uuid>.pdf.
    Parse from the URL so we don't have to scrape a table cell."""
    m = PDF_DATE_RE.search(url)
    if not m:
        return datetime.now(timezone.utc).isoformat()
    try:
        return datetime.strptime(m.group(2), '%Y%m%d').replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return datetime.now(timezone.utc).isoformat()


def _extract_pdf_prose(pdf_bytes):
    """Pull the cover + prose summary out of a TVBS poll PDF. We stop
    at PDF_PAGES_TO_KEEP because everything after that is cross-tab
    matrices that the AI prompt has no use for."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            chunks = []
            for i, p in enumerate(pdf.pages[:PDF_PAGES_TO_KEEP]):
                t = p.extract_text() or ''
                if t.strip():
                    chunks.append(t.strip())
            return '\n\n'.join(chunks)
    except Exception as e:
        print(f"    pdfplumber failed: {e}")
        return ''


def scrape_tvbs_polls():
    """Enumerate TVBS Poll Center PDFs and stage them as articles."""
    from playwright.sync_api import sync_playwright

    conn = get_connection()
    source = conn.execute("SELECT * FROM sources WHERE name = 'TVBS Poll Center'").fetchone()
    if not source:
        print("  TVBS Poll Center source not found — run seed_sources.py first")
        conn.close()
        return 0

    print("\nScraping: TVBS 民調中心")
    new_count = 0

    # Get the (title, pdf_url) catalogue first, then close Playwright before
    # the PDF downloads — keeping a Chromium open while we sync-download
    # several PDFs is wasted memory.
    entries = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(25000)
            page.goto(LIST_URL, wait_until='networkidle')
            raw = page.evaluate("""
                () => Array.from(document.querySelectorAll('a'))
                    .map(a => ({
                        url: a.href,
                        title: (a.textContent || '').trim(),
                    }))
                    .filter(x => x.url.endsWith('.pdf')
                                 && x.url.includes('poll_center')
                                 && x.title.length >= 4)
            """)
            seen = set()
            for e in raw:
                u = e['url'].split('?')[0]
                if u in seen:
                    continue
                seen.add(u)
                entries.append({'url': u, 'title': e['title']})
        finally:
            browser.close()

    print(f"  Found {len(entries)} TVBS poll PDFs")

    headers = browser_headers(referer=LIST_URL)

    with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
        for entry in entries:
            if article_exists(conn, entry['url']):
                continue
            try:
                resp = client.get(entry['url'])
                if resp.status_code != 200:
                    print(f"    {entry['url']}: status {resp.status_code}")
                    continue
                content = _extract_pdf_prose(resp.content)
            except Exception as e:
                print(f"    {entry['url']}: fetch failed — {e}")
                continue

            published_at = _published_from_url(entry['url'])
            print(f"  New: {entry['title'][:70]}")
            save_article(conn, source['id'], entry['url'], entry['title'], content,
                         'zh-tw', published_at)
            new_count += 1

    conn.commit()
    conn.close()
    print(f"  Saved {new_count} new articles from TVBS Poll Center")
    return new_count


if __name__ == '__main__':
    scrape_tvbs_polls()
