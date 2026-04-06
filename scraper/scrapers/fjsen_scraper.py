import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

LIST_URL = 'http://taihai.fjsen.com/'


def parse_date_from_url(url):
    """Extract published date from URL pattern /YYYY-MM/DD/content_..."""
    match = re.search(r'/(\d{4})-(\d{2})/(\d{2})/', url)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)),
                            tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).isoformat()


async def scrape_fjsen():
    """Scrape Haixia Daobao 海峽導報 cross-strait section (taihai.fjsen.com)."""
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

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    }

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        try:
            resp = await client.get(LIST_URL)
            resp.encoding = 'utf-8'
        except Exception as e:
            print(f"  Error fetching fjsen list page: {e}")
            conn.close()
            return 0

        if resp.status_code != 200:
            print(f"  Got status {resp.status_code}")
            conn.close()
            return 0

        soup = BeautifulSoup(resp.text, 'html.parser')

        # Article links: <li><a href="http://taihai.fjsen.com/.../content_XXXXX.htm">
        links = soup.select('li > a[href*="/content_"]')
        print(f"  Found {len(links)} articles")

        for link in links[:30]:
            href = link.get('href', '')
            title = link.get_text(strip=True)

            if not href or not title or len(title) < 4:
                continue

            full_url = href.split('?')[0]

            if article_exists(conn, full_url):
                continue

            print(f"  New: {title[:70]}...")

            published_at = parse_date_from_url(full_url)

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

            conn.execute("""
                INSERT INTO articles (source_id, url, title_original, content_original, language, published_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (source['id'], full_url, title, content[:10000], 'zh-cn', published_at))
            new_count += 1

    conn.commit()
    conn.close()
    print(f"  Saved {new_count} new articles from Haixia Daobao")
    return new_count


if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_fjsen())
