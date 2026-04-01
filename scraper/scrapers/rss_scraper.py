import feedparser
import httpx
from bs4 import BeautifulSoup
from datetime import datetime

async def scrape_taipei_times():
    """Scrape latest articles from Taipei Times RSS feed."""
    
    feed_url = "https://www.taipeitimes.com/xml/index.rss"
    feed = feedparser.parse(feed_url)
    
    articles = []
    
    async with httpx.AsyncClient() as client:
        for entry in feed.entries[:5]:  # Start with just 5 articles
            print(f"Fetching: {entry.title}")
            
            try:
                # Get the full article page
                resp = await client.get(entry.link, timeout=30)
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # Extract the article body
                # (You may need to inspect the actual HTML to find the right selector)
                content_div = soup.select_one('div.archives') or soup.select_one('article')
                content = content_div.get_text(strip=True) if content_div else entry.get('summary', '')
                
                articles.append({
                    'url': entry.link,
                    'title': entry.title,
                    'content': content[:5000],  # Cap at 5000 chars for now
                    'language': 'en',
                    'published_at': entry.get('published', ''),
                })
                
            except Exception as e:
                print(f"  Error fetching {entry.link}: {e}")
                continue
    
    return articles


# Quick test — run this file directly
if __name__ == '__main__':
    import asyncio
    
    async def main():
        articles = await scrape_taipei_times()
        print(f"\nScraped {len(articles)} articles:\n")
        for a in articles:
            print(f"  {a['title']}")
            print(f"  {a['url']}")
            print(f"  Content length: {len(a['content'])} chars")
            print()
    
    asyncio.run(main())