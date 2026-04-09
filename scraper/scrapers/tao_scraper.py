import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists


async def scrape_tao():
    """Scrape Taiwan Affairs Office (国台办) press conferences."""
    conn = get_connection()

    source = conn.execute(
        "SELECT * FROM sources WHERE name = 'Taiwan Affairs Office'"
    ).fetchone()

    if not source:
        conn.execute("""
    INSERT INTO sources (name, name_zh, url, source_type, place, bias, language, tier, scrape_interval, scrape_method)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    'Taiwan Affairs Office', '国务院台湾事务办公室',
    'https://www.gwytb.gov.cn/',
    'government', 'PRC', 'state_official', 'zh-cn', 1, 120, 'html_scrape'
))
        conn.commit()
        source = conn.execute(
            "SELECT * FROM sources WHERE name = 'Taiwan Affairs Office'"
        ).fetchone()
        print("Added Taiwan Affairs Office source to database")

    print(f"\nScraping: Taiwan Affairs Office (国台办)")

    new_count = 0
    base_url = "https://www.gwytb.gov.cn"

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.get(base_url)
            resp.encoding = 'gb2312'
        except Exception as e:
            print(f"  Error fetching TAO page: {e}")
            conn.close()
            return 0

        soup = BeautifulSoup(resp.text, 'html.parser')

        # Find press conference links — they're under /xwdt/xwfb/xwfbh/
        all_links = soup.select('a')
        links = [l for l in all_links if '/xwfbh/' in l.get('href', '')]

        print(f"  Found {len(links)} press conference links")

        for link in links:
            href = link.get('href', '')
            title = link.get_text(strip=True)

            if not href or not title or len(title) < 5:
                continue

            # Build full URL
            if href.startswith('http'):
                full_url = href
            elif href.startswith('/'):
                full_url = base_url + href
            else:
                full_url = base_url + '/' + href

            if article_exists(conn, full_url):
                continue

            print(f"  New: {title[:60]}...")

            # Fetch full transcript
            content = ""
            try:
                article_resp = await client.get(full_url)
                article_resp.encoding = 'gb2312'
                article_soup = BeautifulSoup(article_resp.text, 'html.parser')

                content_div = (
                    article_soup.select_one('div.TRS_Editor') or
                    article_soup.select_one('div.article_content') or
                    article_soup.select_one('div.content') or
                    article_soup.select_one('article')
                )
                if content_div:
                    content = content_div.get_text(strip=True)
            except Exception as e:
                print(f"    Could not fetch article: {e}")

            # Extract date from title if present, e.g. (2026-04-01)
            published_at = datetime.now(timezone.utc).isoformat()
            if '（' in title and '）' in title:
                try:
                    date_str = title.split('（')[-1].split('）')[0]
                    published_at = datetime.strptime(date_str, '%Y-%m-%d').isoformat()
                except Exception:
                    pass

            conn.execute("""
                INSERT INTO articles (source_id, url, title_original, content_original, language, published_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                source['id'], full_url, title, content[:10000],
                'zh-cn', published_at
            ))
            new_count += 1

    conn.commit()
    conn.close()
    print(f"  Saved {new_count} new articles from TAO")
    return new_count


if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_tao())