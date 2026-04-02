import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.scrapers.tao_scraper import scrape_tao
from scraper.scrapers.rss_scraper import scrape_all_rss_sources
from scraper.scrapers.mfa_scraper import scrape_mfa_spokesperson
from scraper.processors.ai_pipeline import process_unanalysed_articles


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

    # Step 3: Analyse unprocessed articles
    total_new = new_rss + new_mfa + new_tao
    print(f"\n--- STEP 3: AI Analysis ({total_new} new articles) ---")
    process_unanalysed_articles(limit=10)

    print("\n" + "=" * 60)
    print("Pipeline complete.")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())