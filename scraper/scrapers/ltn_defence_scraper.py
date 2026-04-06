import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

LIST_URL = 'https://def.ltn.com.tw/breakingnewslist'


def parse_iso_date(dt_str):
    """Parse ISO 8601 date string with timezone offset."""
    if not dt_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        # e.g. '2026-04-06T21:59:00+08:00'
        dt = datetime.fromisoformat(dt_str)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return datetime.now(timezone.utc).isoformat()


async def scrape_ltn_defence():
    """Scrape LTN Defence 自由軍武頻道 (def.ltn.com.tw/breakingnewslist)."""
    conn = get_connection()

    source = conn.execute(
        "SELECT * FROM sources WHERE name = 'LTN Defence'"
    ).fetchone()

    if not source:
        print("  LTN Defence source not found — run seed_sources.py first")
        conn.close()
        return 0

    print(f"\nScraping: LTN Defence 自由軍武頻道")

    new_count = 0

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    }

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        try:
            resp = await client.get(LIST_URL)
            resp.encoding = 'utf-8'
        except Exception as e:
            print(f"  Error fetching LTN Defence list: {e}")
            conn.close()
            return 0

        if resp.status_code != 200:
            print(f"  Got status {resp.status_code}")
            conn.close()
            return 0

        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.select('a.article-box[href*="/article/"]')
        print(f"  Found {len(links)} articles")

        for link in links:
            full_url = link.get('href', '').split('?')[0]
            title = link.get('title', '').strip()

            if not full_url or not title or len(title) < 4:
                continue

            if article_exists(conn, full_url):
                continue

            print(f"  New: {title[:70]}...")

            published_at = datetime.now(timezone.utc).isoformat()
            content = ''

            try:
                article_resp = await client.get(full_url)
                article_resp.encoding = 'utf-8'
                article_soup = BeautifulSoup(article_resp.text, 'html.parser')

                # Authoritative title from og:title (strip site suffix)
                og_title = article_soup.find('meta', {'property': 'og:title'})
                if og_title and og_title.get('content'):
                    title = og_title['content'].replace(' - 自由軍武頻道', '').strip()

                # Date from article:published_time meta
                pub_meta = article_soup.find('meta', {'property': 'article:published_time'})
                if pub_meta and pub_meta.get('content'):
                    published_at = parse_iso_date(pub_meta['content'])

                content_div = article_soup.select_one('div.text')
                if content_div:
                    content = content_div.get_text(strip=True)
                    for cutoff in ['延伸閱讀', '相關新聞', '不用抽', '不用搶']:
                        if cutoff in content:
                            content = content[:content.index(cutoff)]
                            break

            except Exception as e:
                print(f"    Could not fetch article: {e}")

            conn.execute("""
                INSERT INTO articles (source_id, url, title_original, content_original, language, published_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (source['id'], full_url, title, content[:10000], 'zh-tw', published_at))
            new_count += 1

    conn.commit()
    conn.close()
    print(f"  Saved {new_count} new articles from LTN Defence")
    return new_count


if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_ltn_defence())
