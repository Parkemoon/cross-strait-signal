import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

LIST_URL = 'https://www.guancha.cn/taihaifengyun'
BASE_URL = 'https://www.guancha.cn'


def parse_date_from_url(href):
    """Extract published date from URL pattern /section/YYYY_MM_DD_id.shtml"""
    match = re.search(r'/(\d{4})_(\d{2})_(\d{2})_', href)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)),
                            tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).isoformat()


async def scrape_guancha():
    """Scrape Guancha 观察者网 Taiwan Strait section (台海风云)."""
    conn = get_connection()

    source = conn.execute(
        "SELECT * FROM sources WHERE name = 'Guancha'"
    ).fetchone()

    if not source:
        print("  Guancha source not found — run seed_sources.py first")
        conn.close()
        return 0

    print(f"\nScraping: Guancha (Taiwan Strait section)")

    new_count = 0

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Referer': 'https://www.guancha.cn/',
    }

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        try:
            resp = await client.get(LIST_URL)
            resp.encoding = 'utf-8'
        except Exception as e:
            print(f"  Error fetching Guancha list page: {e}")
            conn.close()
            return 0

        if resp.status_code != 200:
            print(f"  Got status {resp.status_code}")
            conn.close()
            return 0

        soup = BeautifulSoup(resp.text, 'html.parser')

        # Article items: li elements containing h4 > a with .shtml hrefs
        links = soup.select('li h4 > a[href*=".shtml"]')
        print(f"  Found {len(links)} articles")

        for link in links[:30]:
            href = link.get('href', '')
            title = link.get_text(strip=True)

            if not href or not title or len(title) < 4:
                continue

            # Build full URL
            if href.startswith('/'):
                full_url = BASE_URL + href
            elif href.startswith('http'):
                full_url = href
            else:
                continue

            # Strip query strings
            full_url = full_url.split('?')[0]

            if article_exists(conn, full_url):
                continue

            print(f"  New: {title[:70]}...")

            published_at = parse_date_from_url(href)

            # Fetch article content
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

            conn.execute("""
                INSERT INTO articles (source_id, url, title_original, content_original, language, published_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (source['id'], full_url, title, content[:10000], 'zh-cn', published_at))
            new_count += 1

    conn.commit()
    conn.close()
    print(f"  Saved {new_count} new articles from Guancha")
    return new_count


if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_guancha())
