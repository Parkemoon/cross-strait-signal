import asyncio
import sys
import os
import subprocess
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.scrapers.tao_scraper import scrape_tao
from scraper.scrapers.rss_scraper import scrape_all_rss_sources
from scraper.scrapers.mfa_scraper import scrape_mfa_spokesperson
from scraper.scrapers.udn_scraper import scrape_all_udn_sources
from scraper.scrapers.guancha_scraper import scrape_guancha
from scraper.scrapers.taiwan_cn_scraper import scrape_taiwan_cn
from scraper.scrapers.fjsen_scraper import scrape_fjsen
from scraper.scrapers.pla_daily_scraper import scrape_pla_daily
from scraper.scrapers.ydn_scraper import scrape_ydn
from scraper.scrapers.ltn_defence_scraper import scrape_ltn_defence
from scraper.scrapers.ettoday_poll_scraper import scrape_ettoday_polls
from scraper.scrapers.tvbs_poll_scraper import scrape_tvbs_polls
from scraper.scrapers.myformosa_poll_scraper import scrape_myformosa_polls
from scraper.scrapers.mac_poll_scraper import scrape_mac_polls
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
    run_tier1,
    process_exercise_only_articles,
    process_poll_only_articles,
)
from scraper.processors.social_translator import translate_social_pulse

# Add scripts dir to path for cluster_events import
sys.path.insert(0, os.path.dirname(__file__))
from cluster_events import cluster_recent_articles


_FAILURES = []


def _run(label, fn, default=0):
    """Run a sync pipeline step, isolating its failure so the rest of the run —
    crucially the downstream AI-analysis and clustering steps — still executes.
    One flaky source must never abort the whole 6-hourly pipeline."""
    try:
        return fn()
    except Exception as e:
        traceback.print_exc()
        print(f"  [pipeline] step '{label}' FAILED: {type(e).__name__}: {e}")
        _FAILURES.append(label)
        return default


async def _arun(label, coro, default=0):
    """Async counterpart of _run. Pass the coroutine itself, e.g.
    ``await _arun('rss', scrape_all_rss_sources())``."""
    try:
        return await coro
    except Exception as e:
        traceback.print_exc()
        print(f"  [pipeline] step '{label}' FAILED: {type(e).__name__}: {e}")
        _FAILURES.append(label)
        return default


async def main():
    print("=" * 60)
    print("CROSS-STRAIT SIGNAL — Pipeline Run")
    print("=" * 60)

    # Every scraper call is wrapped so a single source failing (transient 5xx,
    # markup change, timeout) can't abort the run before Steps 3-4.

    # Step 1: Scrape RSS sources
    print("\n--- STEP 1: Scraping RSS sources ---")
    new_rss = await _arun('rss', scrape_all_rss_sources())

    # Step 2: Scrape HTML sources
    print("\n--- STEP 2: Scraping HTML sources ---")
    new_mfa = await _arun('mfa', scrape_mfa_spokesperson())
    new_tao = await _arun('tao', scrape_tao())
    new_udn = await _arun('udn', scrape_all_udn_sources())
    new_guancha = await _arun('guancha', scrape_guancha())
    new_taiwan_cn = await _arun('taiwan_cn', scrape_taiwan_cn())
    new_fjsen = await _arun('fjsen', scrape_fjsen())
    new_pla = await _arun('pla_daily', scrape_pla_daily())
    new_ydn = await _arun('ydn', scrape_ydn())
    new_ltn_defence = await _arun('ltn_defence', scrape_ltn_defence())
    new_ettoday_polls = await _arun('ettoday_polls', scrape_ettoday_polls())
    await _arun('weibo_hot', scrape_weibo_hot())
    await _arun('ptt', scrape_ptt())

    # Step 2b: Translate social pulse items
    print("\n--- STEP 2b: Social Pulse Translation ---")
    _run('social_translate', translate_social_pulse, default=None)

    # Step 2c: MAC cross-strait economic indicators (monthly publication, idempotent)
    print("\n--- STEP 2c: MAC Economic Indicators ---")
    _run('mac_economic', scrape_mac_economic)

    # Step 2d: UN Comtrade — PRC-reported trade with Taiwan (independent verification source)
    print("\n--- STEP 2d: UN Comtrade ---")
    _run('comtrade', scrape_comtrade)

    # Step 2e: MAC dataset 7459 — TW-HK trade with HK Customs cross-check
    print("\n--- STEP 2e: TW-HK Trade (dual reporter) ---")
    _run('mac_hk_trade', scrape_mac_hk_trade)

    # Step 2f: MAC dataset 7888 — TW vs PRC macro indicators (GDP, CPI, FX)
    print("\n--- STEP 2f: TW vs PRC Macro Indicators ---")
    _run('mac_macro', scrape_mac_macro)

    # Step 2g: Cross-strait trade access (BOFT ban lists + ECFA + PRC suspensions)
    print("\n--- STEP 2g: Trade Access ---")
    _run('trade_access', scrape_trade_access)

    # Step 2h: MAC 7478 + 7473 — cross-strait investment by industry (both directions)
    print("\n--- STEP 2h: Investment by Industry (PRC → TW) ---")
    _run('invest_inbound', scrape_mac_invest_industry_inbound)
    print("\n--- STEP 2h: Investment by Industry (TW → PRC) ---")
    _run('invest_outbound', scrape_mac_invest_industry_outbound)

    # Step 2i: HK Census & Statistics Dept — TW-HK trade as a third reporter
    print("\n--- STEP 2i: HK CSD Trade Verification ---")
    _run('hk_census', scrape_hk_census)

    # Step 2j: TW NIA — PRC + HK/Macao citizens resident in Taiwan
    print("\n--- STEP 2j: TW NIA Population ---")
    _run('tw_nia_population', scrape_tw_nia_population)

    # Step 2k: MND daily PLA aircraft/vessel activity counts
    print("\n--- STEP 2k: MND PLA Incursions ---")
    await _arun('mnd_incursions', scrape_mnd_incursions())

    # Step 2L: Pollster-direct ingestion (Playwright — ~30s startup each).
    # TVBS publishes one PDF per release, My-Formosa one article per release.
    # Polls publish weekly at best; running every 6h is wasteful but
    # idempotent (article_exists check) — extract to a separate daily cron
    # if the pipeline runtime becomes a concern.
    # Run the sync Playwright scrapers in a worker thread — Playwright's
    # sync API refuses to start inside an active asyncio loop.
    print("\n--- STEP 2L: Pollster direct (Playwright) ---")
    new_tvbs_polls = await _arun('tvbs_polls', asyncio.to_thread(scrape_tvbs_polls))
    new_myformosa_polls = await _arun('myformosa_polls', asyncio.to_thread(scrape_myformosa_polls))

    # MAC publishes structured 配布表 PDFs that we parse deterministically
    # straight into polls/poll_results as approved (no Step 3c AI pass, no
    # article staged, so its count is NOT in total_new) — discovery filters
    # the 最新消息 listing on the presence of a 配布表 attachment, which only
    # poll releases carry.
    await _arun('mac_polls', asyncio.to_thread(scrape_mac_polls))

    # Step 3: Analyse unprocessed articles
    total_new = (new_rss + new_mfa + new_tao + new_udn + new_guancha + new_taiwan_cn
                 + new_fjsen + new_pla + new_ydn + new_ltn_defence + new_ettoday_polls
                 + new_tvbs_polls + new_myformosa_polls)
    print(f"\n--- STEP 3: AI Analysis ({total_new} new articles) ---")
    # run_tier1 = Batch API mode by default (collect previous job, submit
    # backlog, brief same-tick wait) — ~50% off Tier-1 token pricing.
    # GEMINI_TIER1_MODE=interactive in .env restores the sequential path.
    _run('ai_analysis', lambda: run_tier1(limit=500), default=None)

    # Step 3b: Exercise-only extraction on articles the keyword pre-filter
    # rejected (no ai_analysis row) from the YDN military-source whitelist.
    # Feeds the exercise tracker with ROC domestic drill content without
    # adding PR pieces to the main signal feed. Capped at 30/run.
    print("\n--- STEP 3b: Exercise-only extraction (military sources) ---")
    _run('exercise_only', lambda: process_exercise_only_articles(days=14, limit=30), default=None)

    # Step 3c: Poll-only extraction on TW-side articles the keyword filter
    # rejected, where the title carries a poll signal (民調/民意調查).
    # Feeds the polling tracker with Lai-approval / vote-intention / TPOF-
    # style coverage that lacks a cross-strait keyword angle. Capped at
    # 30/run.
    print("\n--- STEP 3c: Poll-only extraction (TW poll-bearing titles) ---")
    _run('poll_only', lambda: process_poll_only_articles(days=14, limit=30), default=None)

    # Step 3d: Canonicalise poll-result option labels (drift-catcher). The
    # AI extraction prompt is the first line of defence (CANONICAL NO-OPINION
    # + VOTE-INTENT blocks); this re-collapses any variant labels that slipped
    # through this tick. Idempotent — a no-op when nothing drifted. Run as a
    # subprocess (the script wraps argparse); surface its row-count to the log.
    print("\n--- STEP 3d: Canonicalise poll labels ---")
    canon_script = os.path.join(os.path.dirname(__file__), 'canonicalise_poll_labels.py')
    try:
        result = subprocess.run(
            [sys.executable, canon_script, '--apply'],
            capture_output=True, text=True, timeout=120)
        for line in result.stdout.splitlines():
            if 'pdated' in line:  # "Updated N row(s)" / per-rule "updated N"
                print(f"  {line.strip()}")
        if result.returncode != 0:
            print(f"  canonicaliser exited {result.returncode}: {result.stderr[-500:]}")
    except Exception as e:
        print(f"  canonicaliser failed — {e}")

    # Step 4: Cluster events
    print("\n" + "=" * 60)
    print("--- STEP 4: Event Clustering ---")
    _run('clustering', lambda: cluster_recent_articles(hours=48), default=None)

    print("\n" + "=" * 60)
    print("Pipeline complete.")
    if _FAILURES:
        print(f"⚠ {len(_FAILURES)} step(s) failed this run: {', '.join(_FAILURES)}")
    print("=" * 60)
    return _FAILURES


if __name__ == '__main__':
    failures = asyncio.run(main())
    # Non-zero exit so cron / log monitoring can see a degraded run even though
    # the pipeline pushed through the surviving steps.
    sys.exit(1 if failures else 0)