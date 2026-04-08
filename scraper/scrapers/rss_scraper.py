import feedparser
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

MAX_ARTICLE_AGE = timedelta(days=180)
import sys
import os

# Add the project root to the path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists


FEED_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*',
}


async def scrape_rss_source(source):
    """Scrape articles from an RSS source and store new ones in the database.

    Args:
        source: a database row from the sources table

    Returns:
        Number of new articles saved
    """
    conn = get_connection()
    new_count = 0

    print(f"\nScraping: {source['name']} ({source['url']})")

    # Fetch feed content via httpx so we control headers (feedparser's built-in
    # fetcher uses a bare UA that rsshub.app and some proxies reject)
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=FEED_HEADERS) as client:
            feed_resp = await client.get(source['url'])
        if feed_resp.status_code != 200:
            print(f"  Feed returned HTTP {feed_resp.status_code}")
            conn.close()
            return 0
        feed = feedparser.parse(feed_resp.content)
    except Exception as e:
        print(f"  Could not fetch feed: {e}")
        conn.close()
        return 0

    if not feed.entries:
        print(f"  No entries found in feed")
        conn.close()
        return 0

    print(f"  Found {len(feed.entries)} entries in feed")

    async with httpx.AsyncClient(timeout=30, headers=FEED_HEADERS) as client:
        for entry in feed.entries:
            url = entry.get('link', '')
            
            if not url:
                continue
            
            # DEDUPLICATION: Skip if we already have this article
            if article_exists(conn, url):
                continue
            
            title = entry.get('title', 'No title')
            print(f"  New article: {title[:60]}...")

            # Try to get full article text
            content = entry.get('summary', '')
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    # Source-specific selectors first, then generic fallbacks
                    content_div = (
                        soup.select_one('div.text') or          # Liberty Times
                        soup.select_one('div.article-content__paragraph') or  # UDN
                        soup.select_one('div.archives') or
                        soup.select_one('article') or
                        soup.select_one('div.article-content') or
                        soup.select_one('div.content')
                    )
                    if content_div:
                        content = content_div.get_text(strip=True)
                        # Trim at page furniture markers
                        for cutoff in ['大家都關注', '相關新聞', '熱門新聞', '請加入', '延伸閱讀']:
                            if cutoff in content:
                                content = content[:content.index(cutoff)]
                                break
                    # Try common article selectors
                    content_div = (
                        soup.select_one('div.archives') or
                        soup.select_one('article') or
                        soup.select_one('div.article-content') or
                        soup.select_one('div.content')
                    )
                    if content_div:
                        content = content_div.get_text(strip=True)
            except Exception as e:
                print(f"    Could not fetch full text: {e}")
            
            # Parse published date
            published_at = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                try:
                    published_at = datetime(*entry.published_parsed[:6]).isoformat()
                except Exception:
                    pass

            # Skip articles older than 180 days
            if published_at:
                try:
                    art_dt = datetime.fromisoformat(published_at)
                    if art_dt.tzinfo is None:
                        art_dt = art_dt.replace(tzinfo=timezone.utc)
                    if art_dt < datetime.now(timezone.utc) - MAX_ARTICLE_AGE:
                        continue
                except ValueError:
                    pass

            # Save to database
            conn.execute("""
                INSERT INTO articles (source_id, url, title_original, content_original, language, published_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                source['id'],
                url,
                title,
                content[:10000],  # Cap content length
                source['language'],
                published_at
            ))
            new_count += 1

    conn.commit()
    conn.close()
    return new_count


async def scrape_all_rss_sources():
    """Scrape all active RSS sources."""
    conn = get_connection()
    sources = conn.execute(
        "SELECT * FROM sources WHERE scrape_method = 'rss' AND is_active = 1"
    ).fetchall()
    conn.close()

    total_new = 0
    for source in sources:
        new = await scrape_rss_source(source)
        total_new += new
        print(f"  Saved {new} new articles from {source['name']}")

    print(f"\nTotal new articles saved: {total_new}")
    return total_new


# Run directly
if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_all_rss_sources())