import httpx
import json
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection
from scraper.processors.keyword_filter import PRC_MUST_MENTION_TAIWAN

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

LIST_URL = 'https://weibo.com/ajax/side/hotSearch'

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


def is_cross_strait_relevant(keyword):
    text = keyword.lower()
    return any(kw.lower() in text for kw in PRC_MUST_MENTION_TAIWAN)


async def scrape_weibo_hot():
    """Scrape Weibo Hot Search 微博热搜榜 for cross-strait relevant trending terms."""
    conn = get_connection()
    conn.executescript(INIT_SQL)

    print(f"\nScraping: Weibo Hot Search 微博热搜榜")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://weibo.com/',
        'X-Requested-With': 'XMLHttpRequest',
    }

    scraped_at = datetime.now(timezone.utc).isoformat()
    matched = []

    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        try:
            resp = await client.get(LIST_URL)
        except Exception as e:
            print(f"  Error fetching Weibo hot search: {e}")
            conn.close()
            return 0

        if resp.status_code != 200:
            print(f"  Got status {resp.status_code}")
            conn.close()
            return 0

        try:
            data = resp.json()
        except Exception:
            print(f"  Could not parse JSON response")
            conn.close()
            return 0

        items = data.get('data', {}).get('realtime', [])
        print(f"  Found {len(items)} trending items")

        cross_strait_count = 0
        for item in items:
            keyword = item.get('word', '').strip()
            rank = item.get('rank', 0) + 1  # API rank is 0-indexed
            heat = item.get('num', 0)

            if not keyword:
                continue

            relevant = is_cross_strait_relevant(keyword)
            if relevant:
                print(f"  Cross-strait #{rank}: {keyword} (heat: {heat})")
                cross_strait_count += 1

            matched.append((keyword, rank, heat, relevant))

    for keyword, rank, heat, relevant in matched:
        conn.execute("""
            INSERT INTO social_pulse (platform, item_key, title, rank_position, heat_index, scraped_at)
            VALUES ('weibo', ?, ?, ?, ?, ?)
        """, (keyword, keyword, rank, heat, scraped_at))

    if matched:
        print(f"  Stored {len(matched)} trending items ({cross_strait_count} cross-strait relevant)")
    else:
        print("  No items returned from API")

    conn.commit()
    conn.close()
    return cross_strait_count


if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_weibo_hot())
