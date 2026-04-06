import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists


LIST_URL = 'https://udn.com/news/cate/2/6640'
BASE_URL = 'https://udn.com'


async def scrape_udn():
    """Scrape UDN 聯合新聞網 cross-strait section (最新文章)."""
    conn = get_connection()

    source = conn.execute(
        "SELECT * FROM sources WHERE name = 'UDN'"
    ).fetchone()

    if not source:
        print("  UDN source not found in database — run seed_sources.py first")
        conn.close()
        return 0

    print(f"\nScraping: UDN")

    new_count = 0

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-TW,zh;q=0.9',
    }

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        try:
            resp = await client.get(LIST_URL)
            resp.encoding = 'utf-8'
        except Exception as e:
            print(f"  Error fetching UDN list page: {e}")
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
                    published_at = datetime.strptime(time_text, '%Y-%m-%d %H:%M').isoformat()
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

            conn.execute("""
                INSERT INTO articles (source_id, url, title_original, content_original, language, published_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                source['id'], full_url, title, content[:10000],
                'zh-tw', published_at
            ))
            new_count += 1

    conn.commit()
    conn.close()
    print(f"  Saved {new_count} new articles from UDN")
    return new_count


if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_udn())
