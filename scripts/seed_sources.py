import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'cross_strait_signal.db')

SOURCES = [
    # Taiwan
    {
        'name': 'CNA Chinese',
        'name_zh': '中央通訊社',
        'url': 'https://feedx.net/rss/cna.xml',
        'source_type': 'state_media',
        'country': 'TW',
        'bias': 'green_leaning',
        'language': 'zh-tw',
        'tier': 1,
        'scrape_interval': 120,
        'scrape_method': 'rss',
    },
    {
        'name': 'Liberty Times',
        'name_zh': '自由時報',
        'url': 'https://news.ltn.com.tw/rss/all.xml',
        'source_type': 'independent_media',
        'country': 'TW',
        'bias': 'green',
        'language': 'zh-tw',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
    {
        'name': 'UDN',
        'name_zh': '聯合報',
        'url': 'https://udn.com/rssfeed/news/2/6638/7314?ch=news',
        'source_type': 'independent_media',
        'country': 'TW',
        'bias': 'blue',
        'language': 'zh-tw',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
    # PRC
    {
        'name': 'Xinhua Chinese',
        'name_zh': '新华社',
        'url': 'https://plink.anyfeeder.com/newscn/whxw',
        'source_type': 'state_media',
        'country': 'PRC',
        'bias': 'state_official',
        'language': 'zh-cn',
        'tier': 1,
        'scrape_interval': 240,
        'scrape_method': 'rss',
    },
    {
        'name': "People's Daily Politics",
        'name_zh': '人民日报时政',
        'url': 'https://plink.anyfeeder.com/people/politics',
        'source_type': 'state_media',
        'country': 'PRC',
        'bias': 'state_official',
        'language': 'zh-cn',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
    {
        'name': 'China News Service',
        'name_zh': '中国新闻网',
        'url': 'https://www.chinanews.com.cn/rss/scroll-news.xml',
        'source_type': 'state_media',
        'country': 'PRC',
        'bias': 'state_official',
        'language': 'zh-cn',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
    {
        'name': 'Global Times',
        'name_zh': '环球时报',
        'url': 'https://plink.anyfeeder.com/weixin/hqsbwx',
        'source_type': 'state_media',
        'country': 'PRC',
        'bias': 'state_nationalist',
        'language': 'zh-cn',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
]


def seed_sources():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for source in SOURCES:
        cursor.execute("SELECT id FROM sources WHERE name = ?", (source['name'],))
        if cursor.fetchone():
            # Update bias on existing records in case it wasn't set before
            cursor.execute(
    "UPDATE sources SET bias = ?, url = ? WHERE name = ?",
    (source['bias'], source['url'], source['name']))
            print(f"  Updated: {source['name']}")
            continue

        cursor.execute("""
            INSERT INTO sources
                (name, name_zh, url, source_type, country, bias, language, tier, scrape_interval, scrape_method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            source['name'], source['name_zh'], source['url'], source['source_type'],
            source['country'], source['bias'], source['language'], source['tier'],
            source['scrape_interval'], source['scrape_method']
        ))
        print(f"  Added: {source['name']}")

    conn.commit()
    conn.close()
    print("\nDone. Sources seeded.")


if __name__ == '__main__':
    seed_sources()