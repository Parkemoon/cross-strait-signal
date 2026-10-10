from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists, save_article
from scraper.utils.http import make_async_client
from scraper.utils.dates import parse_url_date

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

LIST_URL = 'http://taihai.fjsen.com/'
CHANNEL_HOST = 'taihai.fjsen.com'
# The front page shows ~15 picks; the section lists carry 2-3x as many
# channel stories a day (2026-10-05: 21 vs 7 for 09-30), and 闽台往来 /
# 台湾万象 items never reached the front page at all.
SECTION_URLS = [
    'http://taihai.fjsen.com/tw_politics.htm',   # 台湾时政
    'http://taihai.fjsen.com/Cross-strait.htm',  # 海峡两岸
    'http://taihai.fjsen.com/fj_tw.htm',         # 闽台往来
    'http://taihai.fjsen.com/tw_Society.htm',    # 台湾万象
]
MAX_LINKS_PER_PAGE = 30
MAX_ARTICLE_AGE = timedelta(days=180)


def parse_list(html, page_url, channel_only):
    """(url, title) pairs from a list page, in page order.

    Front page: list items plus the h1 headline slots, which hold the lead
    stories and are often off-channel (www / fjnews.fjsen.com) — all
    cross-strait picks, so all kept. Section pages: their off-channel links
    are the site-wide sidebar (Fujian news, sport), so channel_only keeps
    taihai.fjsen.com links only."""
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    for a in soup.select('li > a[href*="/content_"], h1 > a[href*="/content_"]'):
        url = urljoin(page_url, a.get('href', '')).split('?')[0]
        title = a.get_text(strip=True)
        if len(title) < 4:
            continue
        if channel_only and urlparse(url).netloc != CHANNEL_HOST:
            continue
        out.append((url, title))
    return out[:MAX_LINKS_PER_PAGE]


def merge_lists(lists):
    """One (url, title) per URL across list pages, first-seen order. The
    front page cuts long titles with '…'; a full title for the same URL on
    a section page replaces it."""
    merged = {}
    for pairs in lists:
        for url, title in pairs:
            old = merged.get(url)
            if old is None or (old.endswith('…') and not title.endswith('…')):
                merged[url] = title
    return list(merged.items())


def parse_date_from_url(url):
    """Extract published date from URL pattern /YYYY-MM/DD/content_...
    Unmatched URLs deliberately stamp now() so the article still gets a
    feed position (the shared helper returns None and leaves that call)."""
    return (parse_url_date(url, r'/(\d{4})-(\d{2})/(\d{2})/')
            or datetime.now(timezone.utc).isoformat())


async def scrape_fjsen():
    """Scrape Haixia Daobao 海峽導報 cross-strait channel (taihai.fjsen.com):
    the front page plus the four section lists in SECTION_URLS."""
    conn = get_connection()

    source = conn.execute(
        "SELECT * FROM sources WHERE name = 'Haixia Daobao'"
    ).fetchone()

    if not source:
        print("  Haixia Daobao source not found — run seed_sources.py first")
        conn.close()
        return 0

    print(f"\nScraping: Haixia Daobao (taihai.fjsen.com)")

    new_count = 0

    async with make_async_client() as client:
        lists = []
        for page_url in [LIST_URL] + SECTION_URLS:
            try:
                resp = await client.get(page_url)
                resp.encoding = 'utf-8'
            except Exception as e:
                print(f"  Error fetching {page_url}: {e}")
                continue
            if resp.status_code != 200:
                print(f"  {page_url}: status {resp.status_code}")
                continue
            lists.append(parse_list(resp.text, page_url,
                                    channel_only=page_url != LIST_URL))

        if not lists:
            conn.close()
            return 0

        links = merge_lists(lists)
        print(f"  Found {len(links)} articles across {len(lists)} list pages")

        for full_url, title in links:
            if article_exists(conn, full_url):
                continue

            published_at = parse_date_from_url(full_url)
            # Skip articles older than 180 days — section pages can surface
            # evergreen/archive pieces (rss_scraper pattern)
            try:
                art_dt = datetime.fromisoformat(published_at)
                if art_dt < datetime.now(timezone.utc) - MAX_ARTICLE_AGE:
                    continue
            except ValueError:
                pass

            print(f"  New: {title[:70]}...")

            # Fetch article content — table-based layout, grab all <p> tags
            content = ''
            try:
                article_resp = await client.get(full_url)
                article_resp.encoding = 'utf-8'
                article_soup = BeautifulSoup(article_resp.text, 'html.parser')

                # Try common content selectors first, fall back to joining p tags
                content_div = (
                    article_soup.select_one('div#content') or
                    article_soup.select_one('div.content') or
                    article_soup.select_one('div#artbody') or
                    article_soup.select_one('div.article')
                )
                if content_div:
                    content = content_div.get_text(strip=True)
                else:
                    # Fall back: join all substantive paragraphs
                    paragraphs = [p.get_text(strip=True) for p in article_soup.select('p')
                                  if len(p.get_text(strip=True)) > 20]
                    content = ' '.join(paragraphs)
            except Exception as e:
                print(f"    Could not fetch article: {e}")

            save_article(conn, source['id'], full_url, title, content, 'zh-cn', published_at)
            new_count += 1

    conn.commit()
    conn.close()
    print(f"  Saved {new_count} new articles from Haixia Daobao")
    return new_count


if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_fjsen())
