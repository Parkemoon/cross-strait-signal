import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection
from scraper.processors.keyword_filter import TW_MUST_MENTION_PRC

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL = 'https://www.ptt.cc'
MIN_PUSH = 2  # minimum push count to be considered high-engagement

# Pages to scrape per board — calibrated so each covers roughly the last 24h of posts
BOARD_PAGES = {
    'Military': 5,
    'Gossiping': 15,
    'HatePolitics': 12,
}

INIT_SQL = """
CREATE TABLE IF NOT EXISTS social_pulse (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    platform          TEXT NOT NULL,
    item_key          TEXT NOT NULL,
    title             TEXT NOT NULL,
    title_en          TEXT,
    title_en_override TEXT,
    rank_position     INTEGER,
    heat_index        INTEGER,
    push_count        INTEGER,
    boo_count         INTEGER,
    board             TEXT,
    url               TEXT,
    scraped_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_social_pulse_platform_time ON social_pulse(platform, scraped_at DESC);
"""


def is_cross_strait_relevant(title):
    text = title.lower()
    return any(kw.lower() in text for kw in TW_MUST_MENTION_PRC)


def parse_push_count(nrec_text):
    """Convert PTT push display to integer. '爆' = 100, 'XX' = -1, number = that number."""
    t = nrec_text.strip()
    if t == '爆':
        return 100
    if t.startswith('X') or t == '':
        return 0
    try:
        return int(t)
    except ValueError:
        return 0


def already_stored_today(conn, post_url):
    """Check if this PTT post was already stored in the last 24 hours."""
    row = conn.execute("""
        SELECT id FROM social_pulse
        WHERE platform = 'ptt' AND item_key = ?
        AND scraped_at >= datetime('now', '-1 day')
    """, (post_url,)).fetchone()
    return row is not None


async def scrape_ptt():
    """Scrape PTT boards for high-push cross-strait relevant posts."""
    conn = get_connection()
    conn.executescript(INIT_SQL)

    print(f"\nScraping: PTT (Military, Gossiping, HatePolitics)")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Cookie': 'over18=1',
    }

    new_count = 0
    scraped_at = datetime.now(timezone.utc).isoformat()

    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        for board, max_pages in BOARD_PAGES.items():
            # Collect entries across pages until max_pages or no previous page
            all_entries = []
            prev_url = None

            for page_num in range(max_pages):
                if page_num == 0:
                    url = f'{BASE_URL}/bbs/{board}/index.html'
                elif prev_url:
                    url = prev_url
                else:
                    break

                try:
                    resp = await client.get(url)
                    resp.encoding = 'utf-8'
                except Exception as e:
                    print(f"  Error fetching PTT {board} (page {page_num}): {type(e).__name__}: {e}")
                    break

                if resp.status_code != 200:
                    print(f"  {board}: got status {resp.status_code}")
                    break

                soup = BeautifulSoup(resp.text, 'html.parser')
                page_entries = soup.select('div.r-ent')
                all_entries.extend(page_entries)

                # Find "上頁" (previous page) link for next iteration
                if page_num == 0:
                    prev_link = soup.select_one('a.btn.wide:-soup-contains("上頁"), .action-bar a:-soup-contains("上頁")')
                    if prev_link and prev_link.get('href'):
                        prev_url = BASE_URL + prev_link['href']
                    else:
                        break  # no previous page link found

            print(f"  {board}: {len(all_entries)} posts across {page_num + 1} page(s)")

            for entry in all_entries:
                title_el = entry.select_one('div.title a')
                nrec_el = entry.select_one('div.nrec span')

                if not title_el:
                    continue  # deleted post

                title = title_el.get_text(strip=True)
                href = title_el.get('href', '')
                post_url = BASE_URL + href if href.startswith('/') else href
                push_count = parse_push_count(nrec_el.get_text(strip=True) if nrec_el else '')

                if push_count < MIN_PUSH:
                    continue

                if not is_cross_strait_relevant(title):
                    continue

                if already_stored_today(conn, post_url):
                    continue

                print(f"  New [{board}] ▲{push_count}: {title[:60]}...")

                conn.execute("""
                    INSERT INTO social_pulse
                        (platform, item_key, title, push_count, board, url, scraped_at)
                    VALUES ('ptt', ?, ?, ?, ?, ?, ?)
                """, (post_url, title, push_count, board, post_url, scraped_at))
                new_count += 1

    conn.commit()
    conn.close()
    print(f"  Stored {new_count} new PTT posts")
    return new_count


if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_ptt())
