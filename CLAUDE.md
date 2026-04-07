# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Cross-Strait Signal** is an open-source intelligence dashboard monitoring PRC-Taiwan cross-strait dynamics through automated bilingual (Chinese-English) media analysis. It scrapes ~20 active news sources, processes articles through a multi-tier AI pipeline, and serves results via a React dashboard backed by FastAPI.

**Critical design intent**: The sentiment axis is bidirectional — destabilising signals from BOTH sides (PLA exercises AND DPP sovereignty moves) register equally. This is not a "China bad, Taiwan good" instrument.

## Commands

### Backend Setup
```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
pip install -r requirements.txt
python scripts/init_db.py
python scripts/seed_sources.py
```

### Running the App (2 terminals)
```bash
# Terminal 1 — FastAPI backend (http://localhost:8000)
python -m uvicorn api.main:app --reload --port 8000

# Terminal 2 — React frontend (http://localhost:3000)
cd frontend && npm start
```

### Pipeline (Scrape + AI Analysis + Clustering)
```bash
python scripts/run_pipeline.py
```

### Frontend
```bash
cd frontend
npm install
npm run build
npm test
```

### API Docs
Interactive Swagger UI at `http://localhost:8000/docs` when backend is running.

### Windows environment note
The project venv at `venv/` may be near-empty on Windows. Use the user-level venv if packages are missing: `/c/Users/Ed/venv/Scripts/python.exe`. Always add `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` at the top of any script that prints Chinese text.

## Architecture

### Data Flow
```
~20 RSS/HTML sources
    → Keyword pre-filter (directional: saves ~80% API cost)
    → Tier 1 AI: Gemini 2.5 Flash Lite (topic, sentiment, entities, urgency)
    → Tier 2 AI: Gemini 2.5 Flash (escalation review, conditional)
    → Tier 3: Human review queue (model disagreements)
    → SQLite + FTS5
    → FastAPI routes
    → React dashboard
```

### Three-Tier AI Pipeline (`scraper/processors/ai_pipeline.py`)
- **Tier 1**: Gemini 2.5 Flash Lite — classifies all pre-filtered articles (batch limit: 500); `temperature=0.1`
- **Tier 2**: Gemini 2.5 Flash — re-reviews only escalation-flagged articles; same temperature
- **Tier 3**: Human review queue — for articles where Tier 1 and Tier 2 disagree; articles stay hidden from dashboard until resolved

**Dynamic glossary injection** (`scraper/processors/glossary.json`): loaded once at module level; before each API call, article text is scanned and matching terms (politicians, military assets, institutions in both Simplified and Traditional Chinese) are injected as a `CRITICAL TERMINOLOGY MAPPING` block to prevent romanisation hallucinations. Add new terms to `glossary.json` without touching Python.

**Relevance gate**: the prompt requires the model to set `is_cross_strait_primary` (bool) as its first decision before classification. If false, `topic_primary` is forced to `NOT_RELEVANT` both by the model and by a Python-level enforcement check. PRC sources writing about Taiwan are explicitly exempt — their cultural/lifestyle coverage of Taiwan is analytically relevant (POL_TONGDU framing) and should not be filtered.

### Keyword Pre-Filter (`scraper/processors/keyword_filter.py`)
Directional logic:
- PRC/Singapore sources: must mention Taiwan, ROC, or relevant territories
- Taiwan sources: must mention PRC, mainland, Hong Kong, or Macau

Only `title + content[:2000]` is checked — full content is not used, to prevent page navigation/sidebar cruft from passing irrelevant articles. Irrelevant articles are marked `ai_processed=1` and skipped — they never reach the AI API.

### Scrapers (`scraper/scrapers/`)
Two types:
- **RSS** (`rss_scraper.py`): handles all `scrape_method='rss'` sources generically via `scrape_all_rss_sources()`
- **HTML scrapers**: one file per source for sites without usable RSS feeds

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
| `weibo_hot_scraper.py` | Weibo Hot Search — fetches top 50 from `weibo.com/ajax/side/hotSearch` JSON API; stores all items in `social_pulse` table |
| `ptt_scraper.py` | PTT BBS — scrapes Military (5 pages), Gossiping (15 pages), HatePolitics (12 pages); requires `over18=1` cookie; page depth in `BOARD_PAGES` dict |

When adding a new HTML scraper: follow the pattern in any existing one. Register the source in `seed_sources.py` and add the import + call to `run_pipeline.py`.

### Social Pulse (`scraper/processors/social_translator.py`)
Separate lightweight pipeline for social data — does NOT go through the article AI pipeline. Batch-translates `social_pulse` rows where `title_en IS NULL` using Gemini 2.5 Flash Lite. Runs as Step 2b in `run_pipeline.py` after the social scrapers.

### Event Clustering (`scripts/cluster_events.py`)
Groups related articles within a 48-hour window using Jaccard similarity on title keywords (threshold: 0.25).

### Database Schema (`db/schema.sql`)
SQLite with FTS5 full-text search. Key tables:
- **articles**: raw scraped content, `ai_processed` flag, `is_active` flag, unique constraint on URL
- **ai_analysis**: structured AI output — `topic_primary`, `sentiment`, `sentiment_score` (−1.0 to +1.0), `urgency`, `is_escalation_signal`, `needs_human_review`, confidence
- **entities**: named entities with type (person, military_unit, ship, aircraft, location, organisation, weapon_system) and geocoding fields
- **analyst_notes**: human editorial commentary with sentiment/topic override capability
- **articles_fts**: FTS5 virtual table for bilingual full-text search
- **sources**: `is_active=0` deactivates a source without deleting its articles
- **social_pulse**: Weibo and PTT items — `platform`, `item_key` (dedup key), `title` (Chinese), `title_en` (AI translation), `title_en_override` (analyst correction), engagement fields (`rank_position`, `heat_index` for Weibo; `push_count`, `boo_count`, `board`, `url` for PTT)

### API Layer (`api/routes/`)
- `articles.py`: GET `/api/articles` (8 filter params), cluster, hide, signal endpoints; `/signal` is a toggle
- `stats.py`: dashboard aggregations, entity leaderboard; escalation signals use a 24h window
- `notes.py`: CRUD for analyst notes with AI override support
- `review.py`: review queue — confirm / override / dismiss
- `social.py`: GET `/api/social/` returns latest Weibo snapshot (all 50 items with `is_cross_strait` flag) + PTT posts from last 24h; PATCH `/api/social/{id}/translation` saves analyst translation override

### Frontend (`frontend/src/`)
React 19 + Recharts + Tailwind CSS 4. State management lives in `App.js`. Key components:
- `FilterBar.jsx`: topic, sentiment, source_country, urgency, escalation, search filters
- `ArticleCard.jsx`: article display with inline sentiment/topic override and analyst notes; `onSignalOff` prop for FlashTraffic removal
- `ReviewQueue.js`: human review UI
- `SignalCharts.jsx`: sentiment trend + topic breakdown charts
- `StatsSidebar.jsx`: dashboard gauges by country and bias label; Taiwan by camp gauges driven by `sentiment_by_bias` from stats API (`green`, `green_leaning`, `blue`)
- `FlashTraffic.jsx`: priority signals section — renders full `ArticleCard` components, inverted colour scheme (`.signal-inverted` CSS class)
- `SocialPulse.jsx`: collapsed by default; header shows "Weibo N · PTT N" counts (N = cross-strait relevant count); expands to two-column panel — Weibo column shows **only** cross-strait relevant items (with rank position); shows "No cross-strait related topics in top 50 trending" when none; inline translation correction via pencil icon
- `SourceBadge.jsx`: colour-coded by `bias` prop, not country — `SOURCE_ABBREV` map covers all active sources

All API calls use relative URLs (`API_BASE = ""`). Dev server proxies to `localhost:8000` via `"proxy"` in `package.json`.

## Deployment

Two-script deploy pattern:
- `deploy.sh` (local): builds frontend, git push, SSHs to server to run `server_deploy.sh`
- `server_deploy.sh` (server only): `git pull`, `npm run build`, `systemctl restart cross-strait-signal`

Server path: `/var/www/cross-strait-signal`. Service name: `cross-strait-signal`.

After deploying changes to `seed_sources.py`, always run `python scripts/seed_sources.py` on the server to apply source additions/deactivations.

**RSSHub**: Four PRC/SG sources (People's Daily, Global Times, The Paper, Zaobao) use a self-hosted RSSHub instance on the server (`http://localhost:1200`). It runs as a Docker container:
```bash
docker run -d --name rsshub --restart always -p 1200:1200 diygod/rsshub
```
If these feeds return 0 entries, check `docker ps` to confirm the container is running. rsshub.app (the public instance) blocks automated clients — always use localhost.

## Environment

Requires `.env` in project root:
```
GEMINI_API_KEY=your_key_here
```

## Key Domain Concepts

**Topic taxonomy (19 categories)**: `MIL_EXERCISE`, `MIL_MOVEMENT`, `MIL_HARDWARE`, `MIL_POLICY`, `DIP_STATEMENT`, `DIP_VISIT`, `DIP_SANCTIONS`, `PARTY_VISIT`, `ECON_TRADE`, `ECON_INVEST`, `POL_DOMESTIC_TW`, `POL_DOMESTIC_PRC`, `POL_TONGDU`, `INFO_WARFARE`, `LEGAL_GREY`, `HUMANITARIAN`, `TRANSPORT`, `INT_ORG`

**POL_TONGDU** (統獨): Captures both unification rhetoric AND independence moves — bidirectional by design.

**PARTY_VISIT**: KMT/opposition visits to PRC — distinct from `DIP_VISIT` (state-level). A KMT chair visiting Beijing is always `PARTY_VISIT`, never `DIP_VISIT`.

**POL_DOMESTIC_TW / POL_DOMESTIC_PRC**: Classified by the *subject* of the article, not the source country.

**Sentiment values**: `destabilising` / `stabilising` / `neutral` / `ambiguous` with numeric score (−1.0 to +1.0)

**Urgency levels**: `flash` / `priority` / `routine`

**Source bias labels**: `green`, `green_leaning`, `blue`, `centrist`, `state_official`, `state_nationalist`

**Active TW sources**: LTN Politics/World/Business/Defence (green), CNA Politics/Mainland/International/Finance (green_leaning), UDN Cross-Strait/Breaking/International/Business (blue), YDN (state_official)

**Active PRC sources**: Xinhua, People's Daily, China News Service, Global Times, The Paper, MFA Spokesperson, Taiwan Affairs Office, Guancha, Haixia Daobao, PLA Daily

**Active SG sources**: Zaobao Cross-Strait (centrist)

## Important Behaviors

- Articles with `needs_human_review = 1` and unresolved status are **hidden from the public feed** until reviewed
- Chinese-language sources are treated as primary — they break stories earlier
- Bias labels reflect editorial reality and should not be softened (e.g. CNA is green_leaning, not neutral)
- The human review queue and inline analyst overrides exist because political classification requires editorial judgment — AI output is a starting point, not final word
- Deactivating a source (`is_active=0`) preserves all its historical articles; use this instead of deleting
