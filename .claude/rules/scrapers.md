---
paths:
  - "scraper/scrapers/**"
---

# Scrapers

Two types:
- **RSS** (`rss_scraper.py`): handles all `scrape_method='rss'` sources generically via `scrape_all_rss_sources()`.
- **HTML scrapers**: one file per source for sites without usable RSS feeds.

**Adding a new HTML scraper**: follow the pattern in any existing one. Register the source in `seed_sources.py` and add the import + call to `run_pipeline.py`.

**Age guard**: both `rss_scraper.py` and HTML scrapers skip articles older than 180 days at insert time (`MAX_ARTICLE_AGE = timedelta(days=180)`).

**PLA Daily date extraction**: reads the Chinese date format from the article title (`(\d{4})年(\d{1,2})月(\d{1,2})日`) — do not re-introduce content-based date scraping on 81.cn (the page template contains a static date that overrides real dates).

## Article scraper inventory

| Scraper file | Source |
|---|---|
| `udn_scraper.py` | UDN 4 sections — uses `scrape_all_udn_sources()` wrapper that queries all `name LIKE 'UDN%'` sources |
| `ltn_defence_scraper.py` | LTN Defence 自由軍武頻道 (`def.ltn.com.tw`) |
| `ydn_scraper.py` | YDN 青年日報 (ROC MND newspaper) |
| `mfa_scraper.py` | MFA Spokesperson (PRC) |
| `tao_scraper.py` | Taiwan Affairs Office (PRC) |
| `guancha_scraper.py` | Guancha 观察者网 |
| `fjsen_scraper.py` | Haixia Daobao 海峽導報 |
| `pla_daily_scraper.py` | PLA Daily 解放軍報 (81.cn — HTTP only, not HTTPS) |
| `weibo_hot_scraper.py` | Weibo Hot Search — top 50 from `weibo.com/ajax/side/hotSearch` JSON API → `social_pulse` |
| `ptt_scraper.py` | PTT BBS — Military (5 pages), Gossiping (15 pages), HatePolitics (12 pages); requires `over18=1` cookie; depth in `BOARD_PAGES` |

## Non-article scrapers (feed dedicated tables, not `articles`)

| Scraper file | Table | Notes |
|---|---|---|
| `mac_economic_scraper.py` | `economic_indicators` | MAC dataset 7887 — see Economic Indicators below |
| `mac_hk_trade_scraper.py` | `economic_indicators` | MAC 7459 — TW-HK trade, dual reporter (TW + HK Customs) |
| `mac_macro_scraper.py` | `economic_indicators` | MAC 7888 — TW vs PRC macro indicators |
| `comtrade_scraper.py` | `economic_indicators` | UN Comtrade — PRC Customs as verification reporter |
| `hk_census_scraper.py` | `economic_indicators` | HK CSD Tables 410-50012/13 — HK Customs direct, third reporter |
| `trade_access_scraper.py` | `trade_access` | BOFT bans + ECFA + MoF PRC suspensions + curated bans |
| `mac_invest_industry_inbound.py` | `investment_by_industry` | MAC 7478 — PRC→TW |
| `mac_invest_industry_outbound.py` | `investment_by_industry` | MAC 7473 — TW→PRC |
| `cifer_snapshot_scraper.py` | `cifer_snapshots` | Playwright, monthly cron — NOT in `run_pipeline.py` |

## Economic Indicators

Three primary sources feed `economic_indicators`:

- **MAC (TW-side, 7887)** — 兩岸經濟交流統計速報, monthly. Eight indicators × ~100 months: trade total, exports/imports/balance with PRC, TW investment in PRC (count + amount), PRC↔TW visitors. Runs as Step 2c.
- **UN Comtrade (PRC-side)** — PRC General Administration of Customs via Comtrade preview API. Reporter 156 (China), partner **490 ("Other Asia, nes")** — PRC files Taiwan trade here, not under 158. Rate-limited 1.2s/req; refreshes last 6 months each run + missing periods. Runs as Step 2d.
- **MAC 7459 (TW-HK dual reporter)** — single CSV with both TW Customs AND HK Customs reporting the same TW-HK flow. Monthly from 2022-01 (annual rows pre-2022 skipped). Series: `exports_to_hk_usd_b`, `imports_from_hk_usd_b` (TW view); `hk_customs_tw_exports_usd_b`, `hk_customs_tw_imports_usd_b` (HK view). Runs as Step 2e.
- **MAC 7888 (TW vs PRC macro)** — 104 monthly snapshot CSVs, each ONE current snapshot of TW + PRC indicators across mixed cadences. Two data rows per CSV: `臺灣` and `中國大陸`. URL format varies — older half uses `Download.ashx?u=<b64>` proxy, newer half is direct; reuse `direct_url()`. 10 series: `tw_gdp_usd_b`/`prc_gdp_usd_b`, `tw_gdp_growth_pct`/`prc_gdp_growth_pct`, `tw_cpi_yoy_pct`/`prc_cpi_yoy_pct`, `tw_fx_reserves_usd_b`/`prc_fx_reserves_usd_b`, `twd_usd_rate`, `cny_usd_rate`. **Quarterly GDP convention**: stored at the *last month of the quarter* (Q2 2017 → `2017-06`) with `period_type='month'` so `/api/economy/series` returns it alongside monthly indicators. Runs as Step 2f.
- **HK CSD direct (`hk_census_scraper.py`)** — censtatd Tables 410-50012 (imports) and 410-50013 (exports). MAC 7459 *compiles* HK Customs; HK CSD publishes the same data directly via censtatd's JSON API. The two should agree by construction (~0.3% in practice). Series: `hk_csd_hk_to_tw_exports_usd_b`, `hk_csd_hk_from_tw_imports_usd_b`. **Gotcha**: `full_series=1` parameter is required — without it the API returns "Parameter is not defined". HKD→USD via 7.78 peg.

### The verification story
PRC's reported imports from Taiwan are ~80–125% higher than MAC's reported exports to PRC (widening from 80% in 2017 to 124% in 2024). Mostly Hong Kong transit trade booked differently. The same gap is visible from the HK side: HK Customs records ~20× more outbound trade to TW than TW records as imports from HK — because TW books PRC-origin goods (which dominate HK→TW shipments) as imports from the mainland, not from HK. The `/api/economy/verification` endpoint pairs reporters by period and emits three kinds (`prc_customs`, `hk_customs`, `hk_csd_direct`).

### MAC gotchas
- **Cloudflare**: the `www.mac.gov.tw/big5/data/CSESM/*.zip` family (datasets 7472, 7469, 21823 etc.) is Cloudflare-protected and blocks server-side automation — cloudscraper, UA-faking, cookie warming all fail. Exceptions: `ws.mac.gov.tw/001/Upload/.../ckfile/<uuid>.csv` (used by 7887 via Download.ashx decoding), plain `/big5/data/<filename>.csv` (used by 7459), and the `/CSESM/12/*.csv` + `/CSESM/9/*.csv` subdirectories (used by 7478 inbound / 7473 outbound). If you need data from a `/CSESM/*.zip` dataset, look for an equivalent plain-CSV dataset first.
- **Critical unit**: MAC publishes USD values in 億 (10^8 USD), not billions. The scraper applies a 0.1x scale factor (see `SERIES_SPECS` in `mac_economic_scraper.py`). All values in `economic_indicators` are stored in USD billions for consistency with Comtrade. If MAC's column headers change to `(百萬美元)` or `(億新臺幣)` in the future, the scale factor needs updating.
- **Encoding**: MAC CSVs are Big5-encoded. Older download URLs go through `ws.mac.gov.tw/Download.ashx?u=<base64>` (Cloudflare-protected); the scraper decodes the `u=` param to reconstruct direct static URLs that bypass the challenge.
- **YoY parsing**: MAC's TW-visitors growth column uses decimal-fraction notation without `%` suffix (e.g. `0.103` = 10.3%) while every other column uses `30.6%` style. `parse_pct()` applies the ×100 conversion only when `|val| < 1` and no `%` sign — narrow enough that a real 100% reading isn't collapsed to 1%.

## Trade Access (`trade_access_scraper.py`)

Separate pipeline for the cross-strait *import permission regime* — what each side allows the other to ship in, and at what tariff. Distinct from the economic indicators table (which tracks trade *volumes*). Feeds `trade_access` keyed on `(direction, hs_code)` where direction is `tw_imports_from_prc` or `prc_imports_from_tw`. Statuses: `banned`, `conditional`, `ecfa_active`, `ecfa_suspended`. Runs as Step 2g.

Five inputs:
- **BOFT 22674** (大陸物品不准許輸入項目, ~2,500 lines) and **BOFT 22675** (有條件准許, ~870 lines): both via `https://www.trade.gov.tw/OpenData/getOpenData.aspx?oid=…`. Status `banned`/`conditional`, direction `tw_imports_from_prc`.
- **MoF Customs ECFA correspondence** (.ods file at `web.customs.gov.tw/download/4489d39d…`): 1,169 paired rows with TW-side and PRC-side 8-digit HS codes. Writes one `ecfa_active` row per direction (so ~2,300 rows total across both sides).
- **MoF PRC Wave 1 suspensions** (12 items, eff. 2024-01-01): inlined as `MOF_PRC_SUSP_W1_ITEMS` in the scraper because the canonical PDF URL has not been publicly findable. Update when located.
- **MoF PRC Wave 2 suspensions** (134 items, eff. 2024-06-15): parsed from `gss.mof.gov.cn/gzdt/zhengcefabu/202405/P020240531308646828162.pdf` using pdfplumber. Names can wrap onto continuation lines; `_PDF_ROW` regex allows the seq+HS prefix on its own line, with continuation logic coalescing the wrapped name.
- **Curated PRC bans** (`scraper/processors/prc_trade_bans.json`): hand-maintained list of GACC's targeted bans on TW agricultural/food exports (pineapples 2021, custard apples 2021, grouper 2022, etc.). Direction is implicit (`prc_imports_from_tw`), status always `banned`. Update when news scrape surfaces a new ban.

**Status conflict resolution**: priority is `banned` > `ecfa_suspended` > `conditional` > `ecfa_active`. Enforced by: skipping ECFA rows on the TW side when BOFT already says banned; letting Wave 1/2 suspension upserts overwrite ECFA-active rows in the PRC direction. The `_UPSERT_SQL` uses `COALESCE` so an upsert without a `product_en` keeps an existing English name — this is how ECFA-suspended items inherit English labels from the earlier ECFA-active write.

**BOFT gotcha**: `trade.gov.tw` returns a Cloudflare-style block page without a `Referer` header pointing back to `data.gov.tw/dataset/22674`. The scraper sets this on every BOFT request via `BOFT_HEADERS`. CSVs are **UTF-8 with BOM** (not Big5 as the file viewers' Big5 rendering of the BOM suggests). After a few successful test downloads in quick succession, `trade.gov.tw` can soft-block the IP for ~10 minutes — if you see HTML where you expect CSV, wait and retry rather than thrashing.

**ECFA correspondence gotcha**: the file is served with a `.pdf` extension but is actually `.ods` (OpenDocument Spreadsheet). `file(1)` confirms; parse with `pandas.read_excel(engine='odf')`. Merged cells in the source render as NaN — forward-fill PRC-side columns to associate continuation rows with their parent HS code.

## CIFER Tracker (`cifer_snapshot_scraper.py`)

Automates the manual count we baked into TradeAccessTab earlier. PRC's CIFER portal at `ciferquery.singlewindow.cn` is browser-gated — direct POSTs to the underlying API endpoint return generic error pages from this server's IP, so we drive a real headless Chromium via Playwright. The scraper:

1. Loads the landing page.
2. Calls the page's own `tabClick('1')` JS handler to switch to the 港澳台 tab (Taiwan companies are filed under HK/Macao/Taiwan, not 境外 — itself an analytical artefact worth surfacing).
3. Fills the autocomplete country field with `中国台湾` and clicks the matching suggestion to populate the hidden country code.
4. Runs two queries: `status='P'` (暂停进口) and `status='R'` (有效), capturing the count from the `共 X 条记录` pagination header.
5. Writes both counts to `cifer_snapshots` with today's date.

Runs monthly via a dedicated cron entry (`0 3 1 * *`) — NOT in `run_pipeline.py`, because (a) it only needs monthly cadence, (b) the ~30s Playwright launch would slow every 6-hourly pipeline run, and (c) PRC's anti-bot detection could fail intermittently and we don't want that to fail the main pipeline.

**System deps**: chromium needs `libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2t64 libnss3 libnspr4` installed via apt; `playwright install chromium` for the binary (already in `~/.cache/ms-playwright/`).

## Investment by Industry (`mac_invest_industry_{inbound,outbound}.py`)

MAC datasets 7478 (inbound, PRC→TW) and 7473 (outbound, TW→PRC). Both feed `investment_by_industry` keyed on (direction, period, industry_zh). Runs as Step 2h. One CSV per monthly cycle at `www.mac.gov.tw/big5/data/CSESM/<sub>/<N>_<sub>.csv` where `<sub>` is `12` for inbound and `9` for outbound; `N` starts at 316 (snapshot through 2019-06) and increments by 1 per month. Both scrapers probe `N=316..450` and stop after 3 consecutive 404s.

**Inbound (7478) format**: 4 columns — industry / cases / amount(千美元) / share. Each CSV is ONE cumulative snapshot since 2009-07.

**Outbound (7473) format**: ~12 columns — four `(件數, 金額(百萬美元), 金額比重)` triples covering prior month / reporting month / YTD / **cumulative-since-1991**. Only the cumulative group is ingested; `_find_cumulative_columns` locates it by regex on the header. Outbound amount is in **百萬美元 (millions USD)** rather than the inbound's 千美元 (thousands), so it's multiplied by 1000 on ingest to normalise `amount_usd_k` to thousands USD across both directions.

**CSV format gotchas (apply to both)**:
- UTF-8 with BOM (not Big5 as the visual BOM-rendering suggests).
- Older snapshots (≤ ~2022) have a malformed header — missing closing `)` on the period range. The header regexes make the `)` optional and treat year-only periods (annual-summary CSVs like CSV 394 = 2025 cumulative summary) as YYYY-12. The inbound CSV 327 (May 2020) is unrecoverable — MAC dumped a 7MB body with no header at all; the scraper silently skips it.
- Some CSVs have embedded newlines in unquoted fields; we pass `newline=''` to `io.StringIO` so `csv.reader` handles them.
- Numbers use thousands commas inside quoted strings (e.g. `" 753,556 "`); `_parse_number` strips quotes, whitespace, and commas.

**The analytical asymmetry**: TW→PRC cumulative since 1991 is ~$212B across ~50k cases. PRC→TW cumulative since 2009 is ~$2.6B across ~1.7k cases. Roughly **50× larger in dollars** in the outbound direction. The inbound figure is small because Taiwan's Investment Commission (投審會) approves only a fraction of PRC-origin applications. The outbound is also distorted by MAC's coarse outbound categorisation: the single biggest bucket is `其他產業` (Other) at ~30% of cumulative outbound — not a real industry, just everything not pulled out by name.
