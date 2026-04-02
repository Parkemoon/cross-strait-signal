import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.scrapers.rss_scraper import scrape_all_rss_sources
from scraper.processors.ai_pipeline import process_unanalysed_articles


async def main():
    print("=" * 60)
    print("CROSS-STRAIT SIGNAL — Pipeline Run")
    print("=" * 60)

    # Step 1: Scrape new articles
    print("\n--- STEP 1: Scraping sources ---")
    new_articles = await scrape_all_rss_sources()

    # Step 2: Analyse unprocessed articles
    print("\n--- STEP 2: AI Analysis ---")
    process_unanalysed_articles(limit=5)

    print("\n" + "=" * 60)
    print("Pipeline complete.")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())