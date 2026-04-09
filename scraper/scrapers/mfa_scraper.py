import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from scraper.utils.db import get_connection, article_exists


async def scrape_mfa_spokesperson():
    """Scrape PRC Ministry of Foreign Affairs spokesperson remarks.
    
    This is an HTML scraper, not RSS — the MFA doesn't provide feeds.
    """
    conn = get_connection()
    
    # First, make sure this source exists in the database
    source = conn.execute(
        "SELECT * FROM sources WHERE name = 'PRC MFA Spokesperson'"
    ).fetchone()
    
    if not source:
        # Add the source if it doesn't exist yet
        conn.execute("""
    INSERT INTO sources (name, name_zh, url, source_type, place, bias, language, tier, scrape_interval, scrape_method)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    'PRC MFA Spokesperson',
    '外交部发言人',
    'https://www.mfa.gov.cn/fyrbt_673021/jzhsl_673025/',
    'government',
    'PRC',
    'state_official',
    'zh-cn',
    1,
    120,
    'html_scrape'
))
        conn.commit()
        source = conn.execute(
            "SELECT * FROM sources WHERE name = 'PRC MFA Spokesperson'"
        ).fetchone()
        print("Added PRC MFA Spokesperson source to database")
    
    print(f"\nScraping: PRC MFA Spokesperson")
    
    new_count = 0
    base_url = "https://www.mfa.gov.cn"
    list_url = f"{base_url}/fyrbt_673021/jzhsl_673025/"
    
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        try:
            resp = await client.get(list_url)
            resp.encoding = 'utf-8'
        except Exception as e:
            print(f"  Error fetching MFA page: {e}")
            conn.close()
            return 0
        
        if resp.status_code != 200:
            print(f"  Got status {resp.status_code}")
            conn.close()
            return 0
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # MFA press conference links contain date patterns like /202604/ and end in .shtml
        all_links = soup.select('a[href$=".shtml"]')
        links = [l for l in all_links if l.get('href', '').startswith('./')]
        
        print(f"  Found {len(links)} links on page")
        
        for link in links[:20]:  # Limit to 20 most recent
            href = link.get('href', '')
            title = link.get_text(strip=True)
            
            if not href or not title or len(title) < 5:
                continue
            
            # Build full URL — MFA uses relative paths like ./202604/t20260401_xxx.shtml
            if href.startswith('./'):
                full_url = list_url + href[2:]
            elif href.startswith('/'):
                full_url = base_url + href
            elif href.startswith('http'):
                full_url = href
            else:
                full_url = list_url + href
            
            # Skip if already scraped
            if article_exists(conn, full_url):
                continue
            
            print(f"  New: {title[:60]}...")
            
            # Fetch the full article
            content = ""
            try:
                article_resp = await client.get(full_url)
                article_resp.encoding = 'utf-8'
                article_soup = BeautifulSoup(article_resp.text, 'html.parser')
                
                # Try common content selectors for MFA pages
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
            
            # Save to database
            conn.execute("""
                INSERT INTO articles (source_id, url, title_original, content_original, language, published_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                source['id'],
                full_url,
                title,
                content[:10000],
                'zh-cn',
                datetime.now(timezone.utc).isoformat()
            ))
            new_count += 1
    
    conn.commit()
    conn.close()
    print(f"  Saved {new_count} new articles from PRC MFA")
    return new_count


# Run directly
if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_mfa_spokesperson())