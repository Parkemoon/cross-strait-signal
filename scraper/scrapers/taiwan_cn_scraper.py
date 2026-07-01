import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL = 'https://www.taiwan.cn'

# China Taiwan Net (中国台湾网) is the TAO's official cross-strait portal. Its
# general news centre (/xwzx/) mixes in national PRC politics that the PRC
# keyword pre-filter rejects, so we scrape only the dedicated cross-strait
# channels — every item there mentions Taiwan, giving a near-100% filter pass.
# /xwzx/PoliticsNews/ is deliberately excluded (general CCP politics, off-topic).
SECTIONS = [
    ('两岸',   'https://www.taiwan.cn/xwzx/la/'),      # cross-strait news
    ('台湾',   'https://www.taiwan.cn/taiwan/'),        # Taiwan channel
    ('快讯',   'https://www.taiwan.cn/taiwan/jsxw/'),   # Taiwan quick news
    ('地方快讯', 'https://www.taiwan.cn/local/dfkx/'),  # local cross-strait exchange
    ('评论',   'https://www.taiwan.cn/plzhx/'),         # cross-strait commentary
]

# Article URLs look like /<section>/YYYYMM/tYYYYMMDD_<id>.htm
ARTICLE_RE = re.compile(r'/t(\d{4})(\d{2})(\d{2})_\d+\.htm')

PER_SECTION_LIMIT = 40

# Skip evergreen/older content (the 评论 commentary channel carries pieces
# years old); matches the 180-day insert guard used across the other scrapers.
MAX_ARTICLE_AGE = timedelta(days=180)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': BASE_URL + '/',
}


def normalise_url(href):
    """Resolve a list-page href to an absolute taiwan.cn URL (query stripped)."""
    if href.startswith('http'):
        full = href
    elif href.startswith('/'):
        full = BASE_URL + href
    else:
        full = BASE_URL + '/' + href.lstrip('./')
    return full.split('?')[0]


def parse_date_from_url(href):
    """Extract published date from the /tYYYYMMDD_id.htm filename."""
    m = ARTICLE_RE.search(href)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).isoformat()


async def scrape_taiwan_cn():
    """Scrape China Taiwan Net (中国台湾网) cross-strait channels."""
    conn = get_connection()

    source = conn.execute(
        "SELECT * FROM sources WHERE name = 'China Taiwan Net'"
    ).fetchone()

    if not source:
        print("  China Taiwan Net source not found — run seed_sources.py first")
        conn.close()
        return 0

    print(f"\nScraping: China Taiwan Net (中国台湾网)")

    new_count = 0
    seen = set()

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=HEADERS) as client:
        for label, list_url in SECTIONS:
            try:
                resp = await client.get(list_url)
                resp.encoding = 'gb18030'  # site serves GBK despite a utf-8 header
            except Exception as e:
                print(f"  [{label}] error fetching list page: {e}")
                continue

            if resp.status_code != 200:
                print(f"  [{label}] got status {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')

            links = []
            for a in soup.select('a[href]'):
                href = a.get('href', '')
                if not ARTICLE_RE.search(href):
                    continue
                title = a.get_text(strip=True)
                if not title or len(title) < 5:
                    continue
                links.append((normalise_url(href), title, href))

            print(f"  [{label}] {len(links)} article links")

            for full_url, title, href in links[:PER_SECTION_LIMIT]:
                if full_url in seen:
                    continue
                seen.add(full_url)

                if article_exists(conn, full_url):
                    continue

                published_at = parse_date_from_url(href)
                # Skip articles older than 180 days (esp. evergreen 评论 commentary)
                try:
                    art_dt = datetime.fromisoformat(published_at)
                    if art_dt < datetime.now(timezone.utc) - MAX_ARTICLE_AGE:
                        continue
                except ValueError:
                    pass

                print(f"  New: {title[:70]}...")

                content = ''
                try:
                    article_resp = await client.get(full_url)
                    article_resp.encoding = 'gb18030'
                    article_soup = BeautifulSoup(article_resp.text, 'html.parser')

                    content_div = (
                        article_soup.select_one('div.TRS_Editor') or
                        article_soup.select_one('div.article_content') or
                        article_soup.select_one('#Zoom') or
                        article_soup.select_one('div.content')
                    )
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
    print(f"  Saved {new_count} new articles from China Taiwan Net")
    return new_count


if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_taiwan_cn())
