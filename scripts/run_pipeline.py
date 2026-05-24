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
from scraper.scrapers.weibo_hot_scraper import scrape_weibo_hot
from scraper.scrapers.ptt_scraper import scrape_ptt
from scraper.scrapers.mac_economic_scraper import scrape_mac_economic
from scraper.scrapers.mac_hk_trade_scraper import scrape_mac_hk_trade
from scraper.scrapers.mac_macro_scraper import scrape_mac_macro
from scraper.scrapers.trade_access_scraper import scrape_trade_access
from scraper.scrapers.mac_invest_industry_inbound import scrape_mac_invest_industry_inbound
from scraper.scrapers.mac_invest_industry_outbound import scrape_mac_invest_industry_outbound
from scraper.scrapers.hk_census_scraper import scrape_hk_census
from scraper.scrapers.comtrade_scraper import scrape_comtrade
from scraper.scrapers.tw_nia_population_scraper import scrape_tw_nia_population
from scraper.scrapers.mnd_incursion_scraper import scrape_mnd_incursions
from scraper.processors.ai_pipeline import (
    process_unanalysed_articles,
    process_exercise_only_articles,
)
from scraper.processors.social_translator import translate_social_pulse

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
    await scrape_weibo_hot()
    await scrape_ptt()

    # Step 2b: Translate social pulse items
    print("\n--- STEP 2b: Social Pulse Translation ---")
    translate_social_pulse()

    # Step 2c: MAC cross-strait economic indicators (monthly publication, idempotent)
    print("\n--- STEP 2c: MAC Economic Indicators ---")
    scrape_mac_economic()

    # Step 2d: UN Comtrade — PRC-reported trade with Taiwan (independent verification source)
    print("\n--- STEP 2d: UN Comtrade ---")
    scrape_comtrade()

    # Step 2e: MAC dataset 7459 — TW-HK trade with HK Customs cross-check
    print("\n--- STEP 2e: TW-HK Trade (dual reporter) ---")
    scrape_mac_hk_trade()

    # Step 2f: MAC dataset 7888 — TW vs PRC macro indicators (GDP, CPI, FX)
    print("\n--- STEP 2f: TW vs PRC Macro Indicators ---")
    scrape_mac_macro()

    # Step 2g: Cross-strait trade access (BOFT ban lists + ECFA + PRC suspensions)
    print("\n--- STEP 2g: Trade Access ---")
    scrape_trade_access()

    # Step 2h: MAC 7478 + 7473 — cross-strait investment by industry (both directions)
    print("\n--- STEP 2h: Investment by Industry (PRC → TW) ---")
    scrape_mac_invest_industry_inbound()
    print("\n--- STEP 2h: Investment by Industry (TW → PRC) ---")
    scrape_mac_invest_industry_outbound()

    # Step 2i: HK Census & Statistics Dept — TW-HK trade as a third reporter
    print("\n--- STEP 2i: HK CSD Trade Verification ---")
    scrape_hk_census()

    # Step 2j: TW NIA — PRC + HK/Macao citizens resident in Taiwan
    print("\n--- STEP 2j: TW NIA Population ---")
    scrape_tw_nia_population()

    # Step 2k: MND daily PLA aircraft/vessel activity counts
    print("\n--- STEP 2k: MND PLA Incursions ---")
    await scrape_mnd_incursions()

    # Step 3: Analyse unprocessed articles
    total_new = new_rss + new_mfa + new_tao + new_udn + new_guancha + new_fjsen + new_pla + new_ydn + new_ltn_defence
    print(f"\n--- STEP 3: AI Analysis ({total_new} new articles) ---")
    process_unanalysed_articles(limit=500)

    # Step 3b: Exercise-only extraction on articles the keyword pre-filter
    # rejected (no ai_analysis row) from the YDN military-source whitelist.
    # Feeds the exercise tracker with ROC domestic drill content without
    # adding PR pieces to the main signal feed. Capped at 30/run.
    print("\n--- STEP 3b: Exercise-only extraction (military sources) ---")
    process_exercise_only_articles(days=14, limit=30)

    # Step 4: Cluster events
    print("\n" + "=" * 60)
    print("--- STEP 4: Event Clustering ---")
    cluster_recent_articles(hours=48)

    print("\n" + "=" * 60)
    print("Pipeline complete.")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())