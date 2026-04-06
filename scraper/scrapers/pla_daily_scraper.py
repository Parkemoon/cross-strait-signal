import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 81.cn is HTTP-only — must use http:// explicitly
LIST_URL = 'http://www.81.cn/fyr/'
BASE_URL = 'http://www.81.cn'


async def scrape_pla_daily():
    """Scrape PLA Daily 解放軍報 — MoD press conference transcripts (www.81.cn/fyr/)."""
    conn = get_connection()

    source = conn.execute(
        "SELECT * FROM sources WHERE name = 'PLA Daily'"
    ).fetchone()

    if not source:
        print("  PLA Daily source not found — run seed_sources.py first")
        conn.close()
        return 0

    print(f"\nScraping: PLA Daily (MoD press conferences)")

    new_count = 0

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    }

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        try:
            resp = await client.get(LIST_URL)
            resp.encoding = 'utf-8'
        except Exception as e:
            print(f"  Error fetching PLA Daily list page: {e}")
            conn.close()
            return 0

        if resp.status_code != 200:
            print(f"  Got status {resp.status_code}")
            conn.close()
            return 0

        soup = BeautifulSoup(resp.text, 'html.parser')

        # MoD press conference links are under jdt_208546 subsection
        links = soup.select('a[href*="jdt_208546"]')
        print(f"  Found {len(links)} press conference links")

        for link in links:
            href = link.get('href', '')
            title = link.get_text(strip=True)

            if not href or not title or len(title) < 5:
                continue

            full_url = href if href.startswith('http') else BASE_URL + href
            full_url = full_url.split('?')[0]

            if article_exists(conn, full_url):
                continue

            print(f"  New: {title[:70]}...")

            # Parse date from URL or content
            published_at = datetime.now(timezone.utc).isoformat()
            date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', full_url)
            if date_match:
                try:
                    published_at = datetime(
                        int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)),
                        tzinfo=timezone.utc
                    ).isoformat()
                except ValueError:
                    pass

            # Fetch transcript content
            content = ''
            try:
                article_resp = await client.get(full_url)
                article_resp.encoding = 'utf-8'
                article_soup = BeautifulSoup(article_resp.text, 'html.parser')

                # Try to get date from content
                date_text = article_soup.find(string=re.compile(r'\d{4}-\d{2}-\d{2}'))
                if date_text:
                    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_text)
                    if m:
                        try:
                            published_at = datetime(
                                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                tzinfo=timezone.utc
                            ).isoformat()
                        except ValueError:
                            pass

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
    print(f"  Saved {new_count} new articles from PLA Daily")
    return new_count


if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_pla_daily())
