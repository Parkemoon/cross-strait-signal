"""ETtoday ET民調 scraper — Phase 2d pollster-direct ingestion.

ETtoday's polling unit publishes under the "ET民調／…" title prefix and a
dedicated landing page exists but has gone stale, so we drive the site's
public search-results page for keyword=ET民調. Their search list is
server-rendered (anchor hrefs present in the static HTML), which lets us
stick to httpx + BeautifulSoup without Playwright.

Step 3c (`process_poll_only_articles`) picks these up automatically — the
ET民調／ titles all contain 民調, so the existing title trigger fires once
the keyword pre-filter rejects them (these are TW-domestic poll write-ups
and almost never mention PRC).
"""
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists, save_article
from scraper.utils.http import make_async_client

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SEARCH_URL = 'https://www.ettoday.net/news_search/doSearch.php?keywords=ET%E6%B0%91%E8%AA%BF'
TITLE_PREFIX = 'ET民調'


def _parse_iso(dt_str):
    if not dt_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        return datetime.fromisoformat(dt_str).astimezone(timezone.utc).isoformat()
    except ValueError:
        return datetime.now(timezone.utc).isoformat()


async def scrape_ettoday_polls():
    """Scrape ET民調 search-result entries → articles. Title-prefix filtered."""
    conn = get_connection()
    source = conn.execute("SELECT * FROM sources WHERE name = 'ETtoday Polls'").fetchone()
    if not source:
        print("  ETtoday Polls source not found — run seed_sources.py first")
        conn.close()
        return 0

    print("\nScraping: ETtoday ET民調")
    new_count = 0
    async with make_async_client() as client:
        try:
            resp = await client.get(SEARCH_URL)
            resp.encoding = 'utf-8'
        except Exception as e:
            print(f"  Error fetching search list: {e}")
            conn.close()
            return 0
        if resp.status_code != 200:
            print(f"  Got status {resp.status_code}")
            conn.close()
            return 0

        soup = BeautifulSoup(resp.text, 'html.parser')
        # Search-result anchors carry their title as text and an onclick GA
        # tracker pointing back at the keyword bucket. Filter on the host
        # path so navigation chrome doesn't sneak in.
        links = []
        for a in soup.select('a[href*="ettoday.net/news/"]'):
            href = (a.get('href') or '').split('?')[0]
            title = (a.get_text() or '').strip()
            if not title.startswith(TITLE_PREFIX):
                continue
            if '/news/' not in href:
                continue
            links.append((href, title))
        # Dedupe while preserving order — duplicate anchors are common
        # (image + headline variants of the same row).
        seen = set()
        ordered = []
        for href, title in links:
            if href in seen:
                continue
            seen.add(href)
            ordered.append((href, title))
        print(f"  Found {len(ordered)} ET民調 results")

        for href, title in ordered:
            if article_exists(conn, href):
                continue

            content = ''
            published_at = datetime.now(timezone.utc).isoformat()
            try:
                ar = await client.get(href)
                ar.encoding = 'utf-8'
                asoup = BeautifulSoup(ar.text, 'html.parser')

                og = asoup.find('meta', {'property': 'og:title'})
                if og and og.get('content'):
                    title = og['content'].split('|')[0].strip()

                pub = asoup.find('meta', {'property': 'article:published_time'})
                if pub and pub.get('content'):
                    published_at = _parse_iso(pub['content'])

                story = asoup.select_one('div.story')
                if story:
                    # Strip tracking pixel + image captions that bloat
                    # content_original with noise — the AI prompt is fine
                    # with the prose alone.
                    for tag in story.select('script, style, .ad, .ad_in_news, figure'):
                        tag.decompose()
                    content = story.get_text(separator='\n', strip=True)
            except Exception as e:
                print(f"    Could not fetch article {href}: {e}")

            print(f"  New: {title[:70]}")
            save_article(conn, source['id'], href, title, content, 'zh-tw', published_at)
            new_count += 1

    conn.commit()
    conn.close()
    print(f"  Saved {new_count} new articles from ETtoday Polls")
    return new_count


if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_ettoday_polls())
