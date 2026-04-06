import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# YDN uses /tw/ prefix for all pages — must use full /tw/ path
LIST_URL = 'https://www.ydn.com.tw/tw/home/'
BASE_URL = 'https://www.ydn.com.tw'


def parse_date(dt_str):
    """Parse ISO-like datetime string from time[datetime] attribute: '2026-04-06 18:21'"""
    try:
        return datetime.strptime(dt_str.strip(), '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return datetime.now(timezone.utc).isoformat()


async def scrape_ydn():
    """Scrape YDN 青年日報 (ROC MND newspaper) from homepage list."""
    conn = get_connection()

    source = conn.execute(
        "SELECT * FROM sources WHERE name = 'YDN'"
    ).fetchone()

    if not source:
        print("  YDN source not found — run seed_sources.py first")
        conn.close()
        return 0

    print(f"\nScraping: YDN 青年日報 (ROC MND newspaper)")

    new_count = 0

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    }

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        try:
            resp = await client.get(LIST_URL)
            resp.encoding = 'utf-8'
        except Exception as e:
            print(f"  Error fetching YDN homepage: {e}")
            conn.close()
            return 0

        if resp.status_code != 200:
            print(f"  Got status {resp.status_code}")
            conn.close()
            return 0

        soup = BeautifulSoup(resp.text, 'html.parser')

        # time.date elements are inside <a> tags with article links
        time_elements = soup.select('time.date[datetime]')
        print(f"  Found {len(time_elements)} articles with timestamps")

        seen_urls = set()

        for time_el in time_elements[:40]:
            dt_str = time_el.get('datetime', '')

            # The time element is inside the anchor tag
            link = time_el.find_parent('a')
            if not link:
                continue

            href = link.get('href', '')
            if 'ugC_News_Detail' not in href:
                continue

            # Resolve relative URL: ../News/... from /tw/home/ → /tw/News/...
            if href.startswith('../'):
                href = '/tw/' + href[3:]
            elif href.startswith('/'):
                pass
            else:
                continue

            full_url = BASE_URL + href.split('?')[0] + '?' + href.split('?')[1] if '?' in href else BASE_URL + href

            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            if article_exists(conn, full_url):
                continue

            # Extract title from span.title if present; otherwise link text minus time
            title_span = link.select_one('span.title')
            if title_span:
                title = title_span.get_text(strip=True)
            else:
                time_el.extract()
                title = link.get_text(strip=True)

            if not title or len(title) < 4:
                continue

            print(f"  New: {title[:70]}...")

            published_at = parse_date(dt_str) if dt_str else datetime.now(timezone.utc).isoformat()

            # Fetch article content (and authoritative title from og:title)
            content = ''
            try:
                article_resp = await client.get(full_url)
                article_resp.encoding = 'utf-8'
                article_soup = BeautifulSoup(article_resp.text, 'html.parser')

                og_title = article_soup.find('meta', {'property': 'og:title'})
                if og_title and og_title.get('content'):
                    title = og_title['content'].strip()

                content_div = article_soup.select_one('div.div_Desc')
                if content_div:
                    content = content_div.get_text(strip=True)
            except Exception as e:
                print(f"    Could not fetch article: {e}")

            conn.execute("""
                INSERT INTO articles (source_id, url, title_original, content_original, language, published_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (source['id'], full_url, title, content[:10000], 'zh-tw', published_at))
            new_count += 1

    conn.commit()
    conn.close()
    print(f"  Saved {new_count} new articles from YDN")
    return new_count


if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_ydn())
