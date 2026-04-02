import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'cross_strait_signal.db')

SOURCES = [
    {
        'name': 'Taipei Times',
        'name_zh': '台北時報',
        'url': 'https://www.taipeitimes.com/xml/index.rss',
        'source_type': 'independent_media',
        'country': 'TW',
        'language': 'en',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
    {
        'name': 'Liberty Times',
        'name_zh': '自由時報',
        'url': 'https://news.ltn.com.tw/rss/all.xml',
        'source_type': 'independent_media',
        'country': 'TW',
        'language': 'zh-tw',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
    {
        'name': 'CGTN World',
        'name_zh': '中国国际电视台',
        'url': 'https://www.cgtn.com/subscribe/rss/section/world.xml',
        'source_type': 'state_media',
        'country': 'PRC',
        'language': 'en',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
    {
        'name': 'CNA Chinese',
        'name_zh': '中央通訊社',
        'url': 'https://feedx.net/rss/cna.xml',
        'source_type': 'state_media',
        'country': 'TW',
        'language': 'zh-tw',
        'tier': 1,
        'scrape_interval': 120,
        'scrape_method': 'rss',
    },
    {
        'name': "People's Daily Politics",
        'name_zh': '人民日报时政',
        'url': 'https://plink.anyfeeder.com/people/politics',
        'source_type': 'state_media',
        'country': 'PRC',
        'language': 'zh-cn',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
    {
        'name': 'Xinhua Chinese',
        'name_zh': '新华社',
        'url': 'https://plink.anyfeeder.com/newscn/whxw',
        'source_type': 'state_media',
        'country': 'PRC',
        'language': 'zh-cn',
        'tier': 1,
        'scrape_interval': 240,
        'scrape_method': 'rss',
    },
    {
        'name': 'China News Service',
        'name_zh': '中国新闻网',
        'url': 'https://www.chinanews.com.cn/rss/scroll-news.xml',
        'source_type': 'state_media',
        'country': 'PRC',
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
        # Check if source already exists (so you can run this script again safely)
        cursor.execute("SELECT id FROM sources WHERE name = ?", (source['name'],))
        if cursor.fetchone():
            print(f"  Already exists: {source['name']}")
            continue

        cursor.execute("""
            INSERT INTO sources (name, name_zh, url, source_type, country, language, tier, scrape_interval, scrape_method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            source['name'], source['name_zh'], source['url'], source['source_type'],
            source['country'], source['language'], source['tier'],
            source['scrape_interval'], source['scrape_method']
        ))
        print(f"  Added: {source['name']}")

    conn.commit()
    conn.close()
    print("\nDone. Sources seeded.")


if __name__ == '__main__':
    seed_sources()