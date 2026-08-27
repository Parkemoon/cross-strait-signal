from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists, save_article
from scraper.utils.http import make_async_client
from scraper.utils.dates import parse_url_date

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL = 'https://www.guancha.cn'
MAX_ARTICLE_AGE = timedelta(days=180)

# The dedicated Taiwan section (台海风云, alias /taiwan) stopped being fed on
# 2026-08-10 while Taiwan stories kept running in the general channels, so
# we scan those too. General channels are gated on a TITLE keyword — the
# downstream keyword pre-filter would otherwise pass any PRC article that
# mentions 台湾 in passing and Tier 1 would pay for it. The Taiwan section
# is not gated (everything there is on-topic by construction).
SECTIONS = [
    ('taihaifengyun', None),
    ('internation', 'title'),
    ('military-affairs', 'title'),
    ('politics', 'title'),
]
TITLE_KEYWORDS = ('台湾', '台海', '两岸', '台独', '赖清德', '民进党', '国民党',
                  '台军', '台当局', '台北', '金门', '台积电', '统一')
MAX_PER_SECTION = 30


def parse_date_from_url(href):
    """Extract published date from URL pattern /section/YYYY_MM_DD_id.shtml.
    Unmatched URLs deliberately stamp now() so the article still gets a
    feed position (the shared helper returns None and leaves that call)."""
    return (parse_url_date(href, r'/(\d{4})_(\d{2})_(\d{2})_')
            or datetime.now(timezone.utc).isoformat())


def title_is_taiwan(title):
    return any(k in title for k in TITLE_KEYWORDS)


async def _scrape_section(client, conn, source_id, section, gate):
    """Return the number of new articles saved from one listing page."""
    try:
        resp = await client.get(f'{BASE_URL}/{section}')
        resp.encoding = 'utf-8'
    except Exception as e:
        print(f"  Error fetching Guancha /{section}: {e}")
        return 0
    if resp.status_code != 200:
        print(f"  /{section}: status {resp.status_code}")
        return 0

    soup = BeautifulSoup(resp.text, 'html.parser')
    # Article items: li elements containing h4 > a with .shtml hrefs
    links = soup.select('li h4 > a[href*=".shtml"]')
    new_count = 0
    kept = 0
    # Gated channels are scanned in full (the gate keeps it cheap); the
    # Taiwan section keeps the historical cap.
    for link in (links if gate else links[:MAX_PER_SECTION]):
        href = link.get('href', '')
        title = link.get_text(strip=True)
        if not href or not title or len(title) < 4:
            continue
        if gate == 'title' and not title_is_taiwan(title):
            continue
        kept += 1

        if href.startswith('/'):
            full_url = BASE_URL + href
        elif href.startswith('http'):
            full_url = href
        else:
            continue
        full_url = full_url.split('?')[0]

        if article_exists(conn, full_url):
            continue

        published_at = parse_date_from_url(href)
        # Skip articles older than 180 days — section pages can surface
        # evergreen/archive pieces (rss_scraper pattern)
        try:
            art_dt = datetime.fromisoformat(published_at)
            if art_dt < datetime.now(timezone.utc) - MAX_ARTICLE_AGE:
                continue
        except ValueError:
            pass

        print(f"  New (/{section}): {title[:70]}...")
        content = ''
        try:
            article_resp = await client.get(full_url)
            article_resp.encoding = 'utf-8'
            article_soup = BeautifulSoup(article_resp.text, 'html.parser')
            content_div = article_soup.select_one('div.content')
            if content_div:
                content = content_div.get_text(strip=True)
        except Exception as e:
            print(f"    Could not fetch article: {e}")

        save_article(conn, source_id, full_url, title, content, 'zh-cn', published_at)
        new_count += 1

    print(f"  /{section}: {len(links)} listed, {kept} on-topic, {new_count} new")
    return new_count


async def scrape_guancha():
    """Scrape Guancha 观察者网 — the Taiwan section plus title-gated general channels."""
    conn = get_connection()
    source = conn.execute("SELECT * FROM sources WHERE name = 'Guancha'").fetchone()
    if not source:
        print("  Guancha source not found — run seed_sources.py first")
        conn.close()
        return 0

    print("\nScraping: Guancha (Taiwan section + gated general channels)")
    new_count = 0
    async with make_async_client(referer='https://www.guancha.cn/') as client:
        for section, gate in SECTIONS:
            new_count += await _scrape_section(client, conn, source['id'], section, gate)

    conn.commit()
    conn.close()
    print(f"  Saved {new_count} new articles from Guancha")
    return new_count


if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_guancha())
