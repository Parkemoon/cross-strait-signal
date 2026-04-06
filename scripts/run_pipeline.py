import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.scrapers.tao_scraper import scrape_tao
from scraper.scrapers.rss_scraper import scrape_all_rss_sources
from scraper.scrapers.mfa_scraper import scrape_mfa_spokesperson
from scraper.scrapers.udn_scraper import scrape_all_udn_sources
from scraper.scrapers.guancha_scraper import scrape_guancha
from scraper.scrapers.fjsen_scraper import scrape_fjsen
from scraper.scrapers.pla_daily_scraper import scrape_pla_daily
from scraper.scrapers.ydn_scraper import scrape_ydn
from scraper.scrapers.ltn_defence_scraper import scrape_ltn_defence
from scraper.processors.ai_pipeline import process_unanalysed_articles

# Add scripts dir to path for cluster_events import
sys.path.insert(0, os.path.dirname(__file__))
from cluster_events import cluster_recent_articles


async def main():
    print("=" * 60)
    print("CROSS-STRAIT SIGNAL — Pipeline Run")
    print("=" * 60)

    # Step 1: Scrape RSS sources
    print("\n--- STEP 1: Scraping RSS sources ---")
    new_rss = await scrape_all_rss_sources()

    # Step 2: Scrape HTML sources
    print("\n--- STEP 2: Scraping HTML sources ---")
    new_mfa = await scrape_mfa_spokesperson()
    new_tao = await scrape_tao()
    new_udn = await scrape_all_udn_sources()
    new_guancha = await scrape_guancha()
    new_fjsen = await scrape_fjsen()
    new_pla = await scrape_pla_daily()
    new_ydn = await scrape_ydn()
    new_ltn_defence = await scrape_ltn_defence()

    # Step 3: Analyse unprocessed articles
    total_new = new_rss + new_mfa + new_tao + new_udn + new_guancha + new_fjsen + new_pla + new_ydn + new_ltn_defence
    print(f"\n--- STEP 3: AI Analysis ({total_new} new articles) ---")
    process_unanalysed_articles(limit=500)

    # Step 4: Cluster events
    print("\n" + "=" * 60)
    print("--- STEP 4: Event Clustering ---")
    cluster_recent_articles(hours=48)

    print("\n" + "=" * 60)
    print("Pipeline complete.")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())