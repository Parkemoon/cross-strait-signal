from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import sys
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists, save_article
from scraper.utils.http import browser_headers, make_async_client

# UDN list-page timestamps are Asia/Taipei local time (UTC+8, no DST).
_TAIPEI = timezone(timedelta(hours=8))


BASE_URL = 'https://udn.com'


async def scrape_udn(source):
    """Scrape a single UDN section given a source row from the database."""
    conn = get_connection()
    new_count = 0

    print(f"\nScraping: {source['name']} ({source['url']})")

    headers = browser_headers(**{'Accept-Language': 'zh-TW,zh;q=0.9'})

    async with make_async_client(headers=headers) as client:
        try:
            resp = await client.get(source['url'])
            resp.encoding = 'utf-8'
        except Exception as e:
            print(f"  Error fetching list page: {e}")
            conn.close()
            return 0

        if resp.status_code != 200:
            print(f"  Got status {resp.status_code}")
            conn.close()
            return 0

        soup = BeautifulSoup(resp.text, 'html.parser')
        items = soup.select('div.story-list__news')
        print(f"  Found {len(items)} articles on list page")

        for item in items:
            text_div = item.select_one('div.story-list__text')
            if not text_div:
                continue

            link = text_div.select_one('h3 a, h2 a')
            if not link:
                continue

            title = link.get('title') or link.get_text(strip=True)
            href = link.get('href', '')

            if not title or not href:
                continue

            # Build canonical URL — strip tracking params
            if href.startswith('/'):
                full_url = BASE_URL + href.split('?')[0]
            elif href.startswith('http'):
                full_url = href.split('?')[0]
            else:
                continue

            if article_exists(conn, full_url):
                continue

            print(f"  New: {title[:70]}...")

            # Parse timestamp from list page
            time_tag = item.select_one('time.story-list__time')
            published_at = datetime.now(timezone.utc).isoformat()
            if time_tag:
                time_text = time_tag.get_text(strip=True)
                try:
                    published_at = (datetime.strptime(time_text, '%Y-%m-%d %H:%M')
                                    .replace(tzinfo=_TAIPEI)
                                    .astimezone(timezone.utc).isoformat())
                except ValueError:
                    pass

            # Fetch article content
            content = ''
            try:
                article_resp = await client.get(full_url)
                article_resp.encoding = 'utf-8'
                article_soup = BeautifulSoup(article_resp.text, 'html.parser')

                content_div = article_soup.select_one('div.article-content__paragraph')
                if content_div:
                    content = content_div.get_text(strip=True)
            except Exception as e:
                print(f"    Could not fetch article content: {e}")

            save_article(conn, source['id'], full_url, title, content,
                         'zh-tw', published_at)
            new_count += 1

    conn.commit()
    conn.close()
    print(f"  Saved {new_count} new articles from {source['name']}")
    return new_count


async def scrape_all_udn_sources():
    """Scrape all active UDN section sources."""
    conn = get_connection()
    sources = conn.execute(
        "SELECT * FROM sources WHERE name LIKE 'UDN%' AND is_active = 1"
    ).fetchall()
    conn.close()

    total = 0
    for source in sources:
        total += await scrape_udn(source)
    return total


if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_all_udn_sources())
