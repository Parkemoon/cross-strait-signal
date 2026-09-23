"""China Times (中時新聞網) scraper for the four CT section sources.

Replaces the RSSHub /chinatimes route. chinatimes.com put a Cloudflare
managed challenge on section pages on 2026-08-26 and widened it to the
whole site (every path but the home page, including sitemaps, RSS and
article pages) on 2026-09-08 (Politics on 09-18). The rule challenges
headless and scripted clients: plain HTTP, RSSHub and headless Chromium
all get a 403 「正在執行安全驗證」 page. A normal Chromium with a window is
served every page with no challenge, so this scraper drives headful
Chromium on a private Xvfb display (scraper/utils/display.py). It sends
the browser's own user-agent and uses no stealth patches or challenge
solving; if CT starts challenging real browsers as well, the run stops
at the first challenge page and check_scraper_health.py flags the
sources stale.

Per source: the section's paginated 總覽 list
(/<section>/total?page=N&chdtv, 20 items a page, newest first), then
every article not already stored, then the direct-child <p> of
.article-body. Paging stops at the first page with nothing new, so the
same code serves the 6-hourly tick (normally page 1 only) and a gap
backfill (`--max-pages 60`).

Stored URLs keep the historical form `<article>?chdtv`. Older rows also
carry `?ctrack=…` variants, so the stored-check matches any query
string on the same article path.
"""
import argparse
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.dates import TAIPEI
from scraper.utils.db import get_connection, save_article
from scraper.utils.display import virtual_display

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL = 'https://www.chinatimes.com'
MAX_ARTICLE_AGE = timedelta(days=180)
DEFAULT_MAX_PAGES = 5
LIST_PAUSE_S = 4
ARTICLE_PAUSE_S = 2

_ARTICLE_PATH = re.compile(r'^/(realtimenews|newspapers|opinion)/(\d{14}-\d{6})$')
# Page furniture that follows the body inside .article-body (the 兩岸徵文
# column's call for submissions).
_BODY_CUTOFFS = ('【徵文啟事】',)


class ChallengedError(RuntimeError):
    """chinatimes.com served its Cloudflare challenge instead of a page."""


def canonical_url(href):
    """Absolute article URL in the stored `?chdtv` form, or None for a
    link that is not a realtimenews / newspapers / opinion article."""
    parts = urlsplit(href.strip())
    if parts.netloc and parts.netloc != 'www.chinatimes.com':
        return None
    if not _ARTICLE_PATH.match(parts.path):
        return None
    return f'{BASE_URL}{parts.path}?chdtv'


def taipei_to_utc(stamp):
    """'2026-09-24 00:12' (Taipei) -> '2026-09-23T16:12:00', naive UTC as
    the RSSHub-era CT rows were stored. None when unparseable."""
    try:
        local = datetime.strptime(stamp.strip(), '%Y-%m-%d %H:%M').replace(tzinfo=TAIPEI)
    except (AttributeError, ValueError):
        return None
    return local.astimezone(timezone.utc).replace(tzinfo=None).isoformat()


def parse_list(html):
    """Items on a 總覽 list page, newest first: dicts with url, title and
    published_at (naive UTC ISO, or None)."""
    soup = BeautifulSoup(html, 'html.parser')
    items, seen = [], set()
    for box in soup.select('.articlebox-compact'):
        link = box.select_one('h3.title a')
        if not link:
            continue
        url = canonical_url(link.get('href', ''))
        title = ' '.join(link.get_text(' ', strip=True).split())
        # The 旺報 print lists can repeat an entry; keep the first.
        if not url or not title or url in seen:
            continue
        seen.add(url)
        stamp = box.select_one('.meta-info time[datetime]')
        items.append({
            'url': url,
            'title': title,
            'published_at': taipei_to_utc(stamp['datetime']) if stamp else None,
        })
    return items


def extract_body(html):
    """Article text: the direct-child <p> of .article-body, one per line.
    Nested <p> belong to ads, the promote-word boxes and the payment
    appeal, so they are left out."""
    soup = BeautifulSoup(html, 'html.parser')
    body = soup.select_one('.article-body')
    if not body:
        return ''
    paras = [p.get_text(' ', strip=True) for p in body.find_all('p', recursive=False)]
    text = '\n'.join(p for p in paras if p)
    for cutoff in _BODY_CUTOFFS:
        if cutoff in text:
            text = text[:text.index(cutoff)].rstrip()
    return text


def is_challenge(status, title):
    return status == 403 or '請稍候' in (title or '')


def list_url(source_url, page_no):
    """/<section>/total?page=N&chdtv for a source whose url is the
    section front page (https://www.chinatimes.com/politic/)."""
    section = urlsplit(source_url).path.strip('/').split('/')[0]
    return f'{BASE_URL}/{section}/total?page={page_no}&chdtv'


def already_stored(conn, url):
    """True when any query-string variant of this article path is stored
    (?chdtv, ?ctrack=…, or bare). Range scan on the unique url index."""
    path = url.split('?', 1)[0]
    row = conn.execute(
        'SELECT 1 FROM articles WHERE url = ? OR (url >= ? AND url < ?) LIMIT 1',
        (path, path + '?', path + '@')).fetchone()
    return row is not None


def allow_request(resource_type, url):
    """Only CT's own document, scripts and XHR load. Third-party ad and
    tracker scripts and iframes grew one renderer to 1.3 GB over ~500
    articles on the first prod backfill (4 GB server, no swap); images,
    fonts, media and CSS are never needed. Cloudflare's /cdn-cgi/ scripts
    are first-party, so they still run."""
    return (resource_type in ('document', 'script', 'xhr', 'fetch')
            and urlsplit(url).hostname == 'www.chinatimes.com')


def _open(page, url):
    resp = page.goto(url, wait_until='domcontentloaded', timeout=45000)
    status = resp.status if resp else None
    if is_challenge(status, page.title()):
        raise ChallengedError(f'Cloudflare challenge on {url} (HTTP {status})')
    return status, page.content()


def scrape_source(context, conn, source, max_pages=DEFAULT_MAX_PAGES, all_pages=False):
    """Walk the section's 總覽 list. Normally stops at the first page with
    nothing new; `all_pages` walks every page (the listing ends after 10
    pages / 200 items), for resuming an interrupted backfill."""
    print(f"\nScraping: {source['name']} ({source['url']})")
    cutoff = (datetime.now(timezone.utc) - MAX_ARTICLE_AGE).replace(tzinfo=None).isoformat()
    new_count = 0
    for page_no in range(1, max_pages + 1):
        # A fresh tab per list page (~20 articles) keeps the renderer from
        # growing across a long run.
        page = context.new_page()
        try:
            _, html = _open(page, list_url(source['url'], page_no))
            items = parse_list(html)
            fresh = [it for it in items if not already_stored(conn, it['url'])]
            print(f"  page {page_no}: {len(items)} items, {len(fresh)} new")
            if not items or (not fresh and not all_pages):
                break
            for item in fresh:
                if item['published_at'] and item['published_at'] < cutoff:
                    continue
                time.sleep(ARTICLE_PAUSE_S)
                try:
                    _, article_html = _open(page, item['url'])
                except ChallengedError:
                    raise
                except Exception as e:
                    print(f"    Could not fetch {item['url']}: {e}")
                    continue
                content = extract_body(article_html)
                # An empty body is a markup change or a failed load, not an
                # empty article. Saving it would make the miss permanent (URL dedup).
                if not content:
                    print(f"    No body text: {item['url']} — skipping")
                    continue
                try:
                    save_article(conn, source['id'], item['url'], item['title'], content,
                                 source['language'], item['published_at'])
                except sqlite3.IntegrityError:
                    # A backfill and a pipeline tick overlapping: the other run
                    # stored it between our check and this insert.
                    print(f"    Stored meanwhile by another run: {item['url']}")
                    continue
                print(f"  New: {item['title'][:70]}")
                new_count += 1
        finally:
            page.close()
        conn.commit()
        time.sleep(LIST_PAUSE_S)
    print(f"  Saved {new_count} new articles from {source['name']}")
    return new_count


def scrape_all_chinatimes_sources(max_pages=DEFAULT_MAX_PAGES, only=None, all_pages=False):
    """Scrape every active chinatimes.com source (or just `only`, a source
    name) in one browser session. Sync Playwright: run it in a worker
    thread from async code, as the pipeline does."""
    from playwright.sync_api import sync_playwright

    conn = get_connection()
    sources = conn.execute(
        "SELECT * FROM sources WHERE url LIKE 'https://www.chinatimes.com/%' "
        "AND scrape_method = 'html_scrape' AND is_active = 1 ORDER BY id").fetchall()
    if only:
        sources = [s for s in sources if s['name'] == only]
    if not sources:
        print("  No active chinatimes.com sources — run seed_sources.py first")
        conn.close()
        return 0

    total = 0
    try:
        with virtual_display() as display, sync_playwright() as p:
            browser = p.chromium.launch(channel='chromium', headless=False,
                                        env={**os.environ, 'DISPLAY': display})
            try:
                context = browser.new_context(locale='zh-TW')
                context.route('**/*', lambda route: route.continue_()
                              if allow_request(route.request.resource_type, route.request.url)
                              else route.abort())
                for source in sources:
                    total += scrape_source(context, conn, source, max_pages, all_pages)
            finally:
                browser.close()
    finally:
        conn.commit()
        conn.close()
    return total


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--max-pages', type=int, default=DEFAULT_MAX_PAGES,
                    help='list pages per section; paging stops early at the first page with nothing new')
    ap.add_argument('--source', help="one source by name, e.g. 'CT Politics'")
    ap.add_argument('--all-pages', action='store_true',
                    help='walk every list page even when one has nothing new (resume an interrupted backfill)')
    args = ap.parse_args()
    print(f"Total new: {scrape_all_chinatimes_sources(args.max_pages, args.source, args.all_pages)}")
