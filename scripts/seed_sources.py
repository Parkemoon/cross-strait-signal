import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'cross_strait_signal.db')

# Broad feeds replaced by targeted sections — deactivate these
DEACTIVATE_SOURCES = [
    'CNA Chinese',    # replaced by CNA Politics/Mainland/International/Finance
    'Liberty Times',  # replaced by LTN Politics/World/Business/Defence
    'Guangming Daily', # anyfeeder proxy dead, rarely cross-strait relevant
]

SOURCES = [
    # Taiwan — targeted sections
    {
        'name': 'LTN Politics',
        'name_zh': '自由時報政治',
        'url': 'https://news.ltn.com.tw/rss/politics.xml',
        'source_type': 'independent_media',
        'country': 'TW',
        'bias': 'green',
        'language': 'zh-tw',
        'tier': 1,
        'scrape_interval': 240,
        'scrape_method': 'rss',
    },
    {
        'name': 'LTN World',
        'name_zh': '自由時報國際',
        'url': 'https://news.ltn.com.tw/rss/world.xml',
        'source_type': 'independent_media',
        'country': 'TW',
        'bias': 'green',
        'language': 'zh-tw',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
    {
        'name': 'LTN Business',
        'name_zh': '自由時報財經',
        'url': 'https://news.ltn.com.tw/rss/business.xml',
        'source_type': 'independent_media',
        'country': 'TW',
        'bias': 'green',
        'language': 'zh-tw',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
    {
        'name': 'LTN Defence',
        'name_zh': '自由軍武頻道',
        'url': 'https://def.ltn.com.tw/breakingnewslist',
        'source_type': 'independent_media',
        'country': 'TW',
        'bias': 'green',
        'language': 'zh-tw',
        'tier': 1,
        'scrape_interval': 240,
        'scrape_method': 'html_scrape',
    },
    {
        'name': 'CNA Politics',
        'name_zh': '中央社政治',
        'url': 'https://feeds.feedburner.com/rsscna/politics',
        'source_type': 'state_media',
        'country': 'TW',
        'bias': 'green_leaning',
        'language': 'zh-tw',
        'tier': 1,
        'scrape_interval': 240,
        'scrape_method': 'rss',
    },
    {
        'name': 'CNA Mainland',
        'name_zh': '中央社兩岸',
        'url': 'https://feeds.feedburner.com/rsscna/mainland',
        'source_type': 'state_media',
        'country': 'TW',
        'bias': 'green_leaning',
        'language': 'zh-tw',
        'tier': 1,
        'scrape_interval': 240,
        'scrape_method': 'rss',
    },
    {
        'name': 'CNA International',
        'name_zh': '中央社國際',
        'url': 'https://feeds.feedburner.com/rsscna/intworld',
        'source_type': 'state_media',
        'country': 'TW',
        'bias': 'green_leaning',
        'language': 'zh-tw',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
    {
        'name': 'CNA Finance',
        'name_zh': '中央社財經',
        'url': 'https://feeds.feedburner.com/rsscna/finance',
        'source_type': 'state_media',
        'country': 'TW',
        'bias': 'green_leaning',
        'language': 'zh-tw',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
    {
        'name': 'UDN',
        'name_zh': '聯合報兩岸',
        'url': 'https://udn.com/news/cate/2/6640',
        'source_type': 'independent_media',
        'country': 'TW',
        'bias': 'blue',
        'language': 'zh-tw',
        'tier': 1,
        'scrape_interval': 240,
        'scrape_method': 'html_scrape',
    },
    {
        'name': 'UDN Breaking',
        'name_zh': '聯合報要聞',
        'url': 'https://udn.com/news/cate/2/6638',
        'source_type': 'independent_media',
        'country': 'TW',
        'bias': 'blue',
        'language': 'zh-tw',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'html_scrape',
    },
    {
        'name': 'UDN International',
        'name_zh': '聯合報全球',
        'url': 'https://udn.com/news/cate/2/7225',
        'source_type': 'independent_media',
        'country': 'TW',
        'bias': 'blue',
        'language': 'zh-tw',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'html_scrape',
    },
    {
        'name': 'UDN Business',
        'name_zh': '聯合報産経',
        'url': 'https://udn.com/news/cate/2/6644',
        'source_type': 'independent_media',
        'country': 'TW',
        'bias': 'blue',
        'language': 'zh-tw',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'html_scrape',
    },
    {
        'name': 'YDN',
        'name_zh': '青年日報',
        'url': 'https://www.ydn.com.tw/tw/home/',
        'source_type': 'state_media',
        'country': 'TW',
        'bias': 'green_leaning',
        'language': 'zh-tw',
        'tier': 1,
        'scrape_interval': 240,
        'scrape_method': 'html_scrape',
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
        'name_zh': '人民日报台湾',
        'url': 'http://localhost:1200/people/tw',
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
        'name_zh': '环球时报台海',
        'url': 'http://localhost:1200/huanqiu/news/taiwan',
        'source_type': 'state_media',
        'country': 'PRC',
        'bias': 'state_nationalist',
        'language': 'zh-cn',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
    {
        'name': 'The Paper',
        'name_zh': '澎湃新聞',
        'url': 'http://localhost:1200/thepaper/featured',
        'source_type': 'state_media',
        'country': 'PRC',
        'bias': 'state_official',
        'language': 'zh-cn',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
    {
        'name': 'Guancha',
        'name_zh': '观察者网',
        'url': 'https://www.guancha.cn/taihaifengyun',
        'source_type': 'independent_media',
        'country': 'PRC',
        'bias': 'state_nationalist',
        'language': 'zh-cn',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'html_scrape',
    },
    {
        'name': 'Haixia Daobao',
        'name_zh': '海峽導報',
        'url': 'http://taihai.fjsen.com/',
        'source_type': 'state_media',
        'country': 'PRC',
        'bias': 'state_official',
        'language': 'zh-cn',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'html_scrape',
    },
    {
        'name': 'PLA Daily',
        'name_zh': '解放軍報',
        'url': 'http://www.81.cn/fyr/',
        'source_type': 'state_media',
        'country': 'PRC',
        'bias': 'state_official',
        'language': 'zh-cn',
        'tier': 1,
        'scrape_interval': 240,
        'scrape_method': 'html_scrape',
    },
    # International Chinese-language Sources
    {
        'name': 'Zaobao Cross-Strait',
        'name_zh': '聯合早報中港台',
        'url': 'http://localhost:1200/zaobao/realtime/china',
        'source_type': 'independent_media',
        'country': 'SG',
        'bias': 'centrist',
        'language': 'zh-cn',
        'tier': 2,
        'scrape_interval': 360,
        'scrape_method': 'rss',
    },
]


def seed_sources():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Deactivate broad feeds replaced by targeted sections
    for name in DEACTIVATE_SOURCES:
        cursor.execute("SELECT id FROM sources WHERE name = ?", (name,))
        if cursor.fetchone():
            cursor.execute("UPDATE sources SET is_active = 0 WHERE name = ?", (name,))
            print(f"  Deactivated: {name}")

    for source in SOURCES:
        cursor.execute("SELECT id FROM sources WHERE name = ?", (source['name'],))
        if cursor.fetchone():
            cursor.execute(
                "UPDATE sources SET bias = ?, url = ?, scrape_method = ?, is_active = 1 WHERE name = ?",
                (source['bias'], source['url'], source['scrape_method'], source['name']))
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
