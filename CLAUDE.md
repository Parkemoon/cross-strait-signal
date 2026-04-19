# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Cross-Strait Signal** is an open-source intelligence dashboard monitoring PRC-Taiwan cross-strait dynamics through automated bilingual (Chinese-English) media analysis. It scrapes ~30 active news sources, processes articles through a multi-tier AI pipeline, and serves results via a React dashboard backed by FastAPI.

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

### Key Figures backfill (one-off, after pipeline changes)
```bash
# Re-runs Tier 1 only on articles where a key figure entity was already detected
python scripts/backfill_key_figure_statements.py --days 30 --limit 200
```

### Entity name merge (run on server to fix near-duplicate extractions)
```bash
python scripts/merge_entities.py --dry-run                    # survey clusters first
python scripts/merge_entities.py --type person --threshold 0.9 # interactive merge
```
Flags: `--type` (person/military_unit/location/organisation/…), `--days` (default 90), `--threshold` (default 0.85), `--min-mentions` (default 2), `--dry-run`. At the canonical prompt, enter a number to pick a cluster member, free text to supply a custom name (merges all cluster members into it), `s` to skip, `q` to quit. Start with `--dry-run` and a tight threshold (`0.9`) on the server — false positives to watch for: historically distinct place variants (Beiping ≠ Beijing), different people sharing a surname initial.

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
    → Tier 3: Human review queue (model disagreements — translation editing + auto-approve on resolve)
    → Editorial approval gate (analyst_approved=0 until sign-off; hidden from public feed)
    → SQLite + FTS5
    → FastAPI routes
    → React dashboard
```

### Three-Tier AI Pipeline (`scraper/processors/ai_pipeline.py`)
- **Tier 1**: Gemini 2.5 Flash Lite — classifies all pre-filtered articles (batch limit: 500); `temperature=0.1`
- **Tier 2**: Gemini 2.5 Flash — re-reviews only escalation-flagged articles; same temperature
- **Tier 3**: Human review queue — for articles where Tier 1 and Tier 2 disagree; articles stay hidden from dashboard until resolved
- **Age filter**: `process_unanalysed_articles` only processes articles with `published_at >= datetime('now', '-180 days')` — old DB backlog never reaches the AI pipeline

**Dynamic glossary injection** (`scraper/processors/glossary.json`): loaded once at module level; before each API call, both the article title and body text are scanned (`generate_dynamic_glossary(content, title)`) and matching terms (politicians, military assets, institutions in both Simplified and Traditional Chinese) are injected as a `CRITICAL TERMINOLOGY MAPPING` block to prevent romanisation hallucinations. Add new terms to `glossary.json` without touching Python. Always add both Traditional and Simplified Chinese forms for the same term.

**Key figure statement extraction**: Tier 1 also extracts attributed `(speaker, statement)` pairs into the `key_figure_statements` table as `pending` candidates. The curated figure list lives in `scraper/processors/key_figures.json` — 10 figures with Chinese/English names, roles, party field (DPP/KMT/PRC), portrait filenames, and alias lists used for speaker→figure_id matching. Tier 2 does NOT re-insert statements (only Tier 1 writes to this table). Statements require analyst approval via the Key Figures panel before appearing on the dashboard — this is intentional to prevent misattribution.

**Relevance gate**: the prompt requires the model to set `is_cross_strait_primary` (bool) as its first decision before classification. If false, `topic_primary` is forced to `NOT_RELEVANT` both by the model and by a Python-level enforcement check. `NOT_RELEVANT` is a special pseudo-topic that exists in the DB but is not part of the 28 visible categories — it marks filtered articles and is never shown in the UI. PRC sources writing about Taiwan are explicitly exempt — their cultural/lifestyle coverage of Taiwan is analytically relevant (POL_TONGDU framing) and should not be filtered.

**`scraper/processors/test_ai.py`** is a legacy prototype script — do not use it as a reference. It uses a stale prompt with old topic codes (`POL_UNIFICATION`, `POL_DOMESTIC`) and old sentiment values (`escalatory`/`conciliatory`) that no longer match the DB schema or the real pipeline in `ai_pipeline.py`.

### Keyword Pre-Filter (`scraper/processors/keyword_filter.py`)
Directional logic:
- PRC/HK/SG sources: must mention Taiwan, ROC, or relevant territories
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

**Age guard**: both `rss_scraper.py` and HTML scrapers skip articles older than 180 days at insert time (`MAX_ARTICLE_AGE = timedelta(days=180)`). PLA Daily date extraction reads the Chinese date format from the article title (`(\d{4})年(\d{1,2})月(\d{1,2})日`) — do not re-introduce content-based date scraping on 81.cn (the page template contains a static date that overrides real dates).

### Social Pulse (`scraper/processors/social_translator.py`)
Separate lightweight pipeline for social data — does NOT go through the article AI pipeline. Batch-translates `social_pulse` rows where `title_en IS NULL` using Gemini 2.5 Flash Lite. Runs as Step 2b in `run_pipeline.py` after the social scrapers.

### Event Clustering (`scripts/cluster_events.py`)
Groups related articles within a 48-hour window using Jaccard similarity on title keywords (threshold: 0.25).

### Database connections
`api/database.py` exports `get_db()` — returns a `sqlite3.Connection` with `row_factory = sqlite3.Row`. All API routes follow the same pattern: call `get_db()`, run queries, call `conn.close()` manually (no context manager). `scraper/utils/db.py` provides the same for the pipeline side.

### Database (`db/cross_strait_signal.db`)
**Canonical DB file**: `db/cross_strait_signal.db` — used by both the API (`api/database.py`) and the scraper pipeline (`scraper/utils/db.py`). `db/signal.db` also exists but is not the live DB. Always apply schema changes to `cross_strait_signal.db`. `db/schema.sql` is the reference; `scripts/init_db.py` executes it (idempotent for `IF NOT EXISTS` tables only — existing tables are not migrated, apply changes with direct SQL).

SQLite with FTS5 full-text search. Key tables:
- **articles**: raw scraped content, `ai_processed` flag, `is_active` flag, `is_hidden` flag, `analyst_approved` flag (DEFAULT 0 — must be set to 1 before article appears on public feed), `title_en_override` / `summary_en_override` / `key_quote_override` (analyst translation corrections), `event_cluster_id`, `cluster_size`, unique constraint on URL
- **ai_analysis**: structured AI output — `topic_primary`, `sentiment`, `sentiment_score` (−1.0 to +1.0), `urgency`, `is_escalation_signal`, `needs_human_review`, `review_resolved`, confidence.
- **entities**: named entities with type (person, military_unit, ship, aircraft, location, organisation, weapon_system) and geocoding fields (lat/lng deferred to Phase 2)
- **key_figure_statements**: speaker-attributed quotes and actions extracted by Tier 1, requiring analyst approval before display — `figure_id` (matches `key_figures.json`), `statement_text` (English), `statement_kind` (`quote`/`action`), `approval_status` (`pending`/`approved`/`dismissed`)
- **analyst_notes**: human editorial commentary with sentiment/topic override capability
- **articles_fts**: FTS5 virtual table for bilingual full-text search
- **sources**: `is_active=0` deactivates a source without deleting its articles
- **social_pulse**: Weibo and PTT items — `platform`, `item_key` (dedup key), `title` (Chinese), `title_en` (AI translation), `title_en_override` (analyst correction), engagement fields (`rank_position`, `heat_index` for Weibo; `push_count`, `boo_count`, `board`, `url` for PTT)

### API Layer (`api/routes/`)
- `articles.py`: GET `/api/articles` (9 filter params including `include_pending`), cluster, hide, signal, approve, translation endpoints. `include_pending=true` skips the `analyst_approved=1` filter — admin frontend always sends this; public build never does. `POST /api/articles/{id}/approve` sets `analyst_approved=1`. `PATCH /api/articles/{id}/translation` updates `title_en_override`, `summary_en_override`, `key_quote_override`. `source_place` filter: `PRC`/`TW` map to exact `s.place` match; `hk` maps to `s.place IN ('HK', 'MO')`; `intl` maps to `s.place NOT IN ('PRC', 'TW', 'HK', 'MO')`.
- `stats.py`: dashboard aggregations, entity leaderboard; escalation signals use a 24h window; Key Figures endpoints — `GET /api/stats/key-figures` (approved statements only), `GET /api/stats/key-figures/candidates` (pending grouped by figure), `POST /api/stats/key-figures/statements/{id}/approve`, `POST /api/stats/key-figures/statements/{id}/dismiss`. **All aggregation queries must include the `VISIBLE` constant** defined at the top of `dashboard_stats()`: `a.is_hidden = 0 AND a.analyst_approved = 1 AND (ai.needs_human_review = 0 OR ai.review_resolved = 1)`. `dashboard_stats()` accepts optional scoping params (`topic`, `source_place`, `urgency`, `escalation_only`, `entity`) built via `_build_filter_clause()` — when active, sentiment aggregations scope to those filters while topics/sources/entities/escalation signals stay global. The response always includes `global_avg_sentiment_score` and `global_sentiment_by_place` for ghost-dot comparison in the sidebar. `sentiment_by_place` normalises raw `s.place` values into four display buckets (PRC/TW/HK/INTL) via a `PLACE_BUCKET` SQL CASE expression — never group by raw `s.place` in this query or you'll get duplicate rows for UK, SG, etc.
- `notes.py`: CRUD for analyst notes with AI override support
- `review.py`: review queue — confirm / override / dismiss. Confirm and override both set `analyst_approved=1` on the article (auto-approve). Dismiss sets `is_hidden=1`. `GET /review/stats` returns `pending`, `resolved`, and `pending_approval` counts.
- `social.py`: GET `/api/social/` returns latest Weibo snapshot (all 50 items with `is_cross_strait` flag) + PTT posts from last 24h; PATCH `/api/social/{id}/translation` saves analyst translation override

### Frontend (`frontend/src/`)
React 19 + Recharts + Tailwind CSS 4. State management lives in `App.js`. Key components:
- `FilterBar.jsx`: topic, sentiment, source_place, urgency, escalation, search filters. Source place options: PRC / Taiwan / HK/Macao (`hk`) / International (`intl`). Never hardcode place values beyond these four — new places go in the API filter block.
- `ArticleCard.jsx`: article display with inline sentiment/topic override and analyst notes; `onSignalOff` prop for FlashTraffic removal; `onApprove` callback for pending count updates. Unapproved articles (`analyst_approved=0`) show an amber left border and "⚠ Pending Approval" banner with Approve/Dismiss buttons (admin only). `FieldEditor` component handles inline editing of `title_en_override`, `summary_en_override`, `key_quote_override` — pencil icon reveals textarea; overridden fields render in amber.
- `ReviewQueue.js`: human review UI with translation editing fields (headline, summary, key quote) always visible — changed fields saved via `updateArticleTranslation` before resolving. Confirm/override auto-approves the article.
- `SignalCharts.jsx`: sentiment trend (Y-axis clamped to `[-1, 1]`, single YAxis) + topic breakdown charts.
- `StatsSidebar.jsx`: dashboard gauges sorted PRC → TW → HK/Macao → International; Taiwan by camp gauges driven by `sentiment_by_bias` from stats API (`green`, `green_leaning`, `blue`); camp gauges hidden below n=5 articles to avoid noise. Accepts `filters`, `onTopicClick`, and `onClearScopingFilters` props from `App.js`. When a scoping filter is active, a teal chip appears above "Strait Watch" with a dismissable `×`; each gauge shows a grey ghost dot at the global baseline position (only when scoped score differs by >0.01). `TopicBreakdownChart` hides when `filters.topic` is set (one bar is useless) but stays visible under entity-only filters. `fetchStats` in `api.js` accepts a `filters` object; the stats `useEffect` in `App.js` re-fires only on scoping key changes (`topic`, `source_place`, `urgency`, `escalation_only`, `entity`) — not on `search` or `sentiment`. Sources section groups feeds by publication via `PUBLICATION_NAMES` map — when adding new multi-feed sources, add entries there too.
- `FlashTraffic.jsx`: priority signals section — renders full `ArticleCard` components, inverted colour scheme (`.signal-inverted` CSS class)
- `SocialPulse.jsx`: accepts `column` prop — in column mode (right-hand aside in App.js) always expanded, vertical stack layout; in default inline mode, collapsible with two-column Weibo/PTT panel. Weibo shows only cross-strait relevant items. Inline translation correction via pencil icon (hidden in read-only build). Override colour highlight is also hidden in read-only build.
- `KeyFigures.jsx`: horizontal scrollable row of cards above SocialPulse; each card shows portrait (images in `frontend/public/figures/`, initials fallback with party colour), name, role, latest approved statement; pencil icon (amber when candidates pending) opens per-card curation modal; hidden in read-only build via `READ_ONLY` constant
- `AboutModal.jsx`: triggered from header (desktop) and mobile header "i" button; explains methodology, sentiment axis, source bias taxonomy, AI pipeline, author bio. Follows CSS variable conventions.
- `SourceBadge.jsx`: colour-coded by `bias` prop — `SOURCE_ABBREV` map covers all active sources; multi-feed publications collapse to a shared abbreviation (e.g. all CT sections → `CT`)
- `hooks/useWindowWidth.js`: returns `window.innerWidth`, updates on resize. Used in `App.js` to derive `isMobile = windowWidth < 768`.

**Mobile layout** (`App.js`): below 768px the 3-column grid collapses to a single column with a sticky top tab bar (Feed / Stats / Social / Review). Each tab shows/hides the corresponding panel via `display: none`. When adding new panels or layout elements, check `isMobile` for any fixed widths or multi-column structures that would break on mobile.

**`frontend/src/api.js`** is the central API client — every fetch call in the frontend goes through a named function here. When adding a new API endpoint, add the corresponding function to `api.js` first; components import from it directly (not from `fetch` inline).

**Other components**: `ThemeToggle.jsx` — light/dark theme switcher in the header. `TopicPill.jsx` — inline topic category label used in `ArticleCard`.

All API calls use relative URLs (`API_BASE = ""`). Dev server proxies to `localhost:8000` via `"proxy"` in `package.json`.

## Deployment

Two-script deploy pattern:
- `deploy.sh` (local): builds frontend, git push, SSHs to server to run `server_deploy.sh`
- `server_deploy.sh` (server only): `git pull`, `npm run build` (admin), `npm run build:public` (public read-only), `systemctl restart cross-strait-signal`

**Live URLs**: `strait-signal.net` (public read-only) · `admin.strait-signal.net` (password protected, admin build)
Server path: `/var/www/cross-strait-signal`. Service name: `cross-strait-signal`.

**Read-only build**: `src/readOnly.js` exports `READ_ONLY = process.env.REACT_APP_READ_ONLY === 'true'`. Import it in any component that has write controls to hide them in the public build. Build with `npm run build:public` (sets `BUILD_PATH=build-public`). Nginx blocks POST/PATCH on the public server at the nginx level.

After deploying changes to `seed_sources.py`, always run `python scripts/seed_sources.py` on the server to apply source additions/deactivations.

**RSSHub**: Several sources use a self-hosted RSSHub instance on the server (`http://localhost:1200`) — People's Daily, Global Times, The Paper, Zaobao, RTHK Greater China, and all CT sections. It runs as a Docker container:
```bash
docker run -d --name rsshub --restart always -p 1200:1200 diygod/rsshub:chromium-bundled
```
The `chromium-bundled` tag is required — CT sections use Puppeteer to render chinatimes.com and will return 503 without it. If these feeds return 0 entries, check `docker ps` to confirm the container is running. rsshub.app (the public instance) blocks automated clients — always use localhost.

## Environment

Requires `.env` in project root:
```
GEMINI_API_KEY=your_key_here
```

## Key Domain Concepts

**Topic taxonomy (28 categories)**: `MIL_EXERCISE`, `MIL_MOVEMENT`, `MIL_HARDWARE`, `MIL_POLICY`, `DIP_STATEMENT`, `DIP_VISIT`, `DIP_SANCTIONS`, `PARTY_VISIT`, `ARMS_SALES`, `ECON_TRADE`, `ECON_INVEST`, `ENERGY`, `SCI_TECH`, `POL_DOMESTIC_TW`, `POL_DOMESTIC_PRC`, `POL_TONGDU`, `INFO_WARFARE`, `CYBER`, `LEGAL_GREY`, `HUMANITARIAN`, `TRANSPORT`, `INT_ORG`, `US_PRC`, `US_TAIWAN`, `HK_MAC`, `CULTURE`, `SPORT`

**POL_TONGDU** (統獨): Captures both unification rhetoric AND independence moves — bidirectional by design.

**PARTY_VISIT**: KMT/opposition visits to PRC — distinct from `DIP_VISIT` (state-level). A KMT chair visiting Beijing is always `PARTY_VISIT`, never `DIP_VISIT`.

**ARMS_SALES**: US or third-party arms transfer events and export control decisions — specific package approvals, delivery milestones, export licence decisions. Use `MIL_POLICY` for broader defence posture; `MIL_HARDWARE` when a platform is the primary subject.

**US_PRC**: US-China relations as the primary subject — Washington-Beijing diplomacy, tech/trade sanctions, US Pacific deterrence posture against China. Use when the US-China relationship itself is the focus, not Taiwan's relationship with the US.

**US_TAIWAN**: US-Taiwan relations — political support, economic ties, congressional legislation, US officials visiting/meeting Taiwanese counterparts, US statements on Taiwan's status.

**HK_MAC**: Hong Kong and Macao with cross-strait relevance — "one country, two systems" credibility, Beijing governance, HK/Macao as bellwether or warning for Taiwan. (Code is `HK_MAC`; display label is "HK/Macao" — do not rename the code as it exists in the DB.)

**CULTURE**: Cross-strait cultural exchange and soft power — Taiwanese artists/films popular on the mainland or vice versa, tourism with cultural dimensions, people-to-people ties where cultural exchange (not sovereignty framing) is the primary subject. Use `POL_TONGDU` when cultural framing is explicitly about sovereignty or national identity.

**CYBER**: Cyber operations, hacking, digital espionage, infrastructure intrusions — distinct from `INFO_WARFARE` (narrative/propaganda). PRC-attributed attacks on Taiwan, cross-strait cyber espionage cases, critical infrastructure intrusions.

**SPORT**: Sporting events and disputes with cross-strait political dimensions — Olympic naming ("Chinese Taipei"), cross-strait athletic competitions, sports boycotts, sport as soft power.

**SCI_TECH**: Science, technology, and innovation — semiconductor industry (TSMC, chip supply chains), chip/tech export controls as technology policy, space programmes, AI competition, scientific exchanges, tech talent flows. Use `ECON_TRADE` for broad trade sanctions; `CYBER` for intrusion operations; `ARMS_SALES` for defence hardware. `SCI_TECH` is for civilian/dual-use technology, research, and innovation as the primary subject.

**ENERGY**: Energy security with cross-strait relevance — Taiwan LNG imports, nuclear policy, shipping lane economics, energy infrastructure vulnerability, PRC energy leverage.

**POL_DOMESTIC_TW / POL_DOMESTIC_PRC**: Classified by the *subject* of the article, not the source country.

**Sentiment values**: `hostile` / `cooperative` / `neutral` / `mixed` with numeric score (−1.0 hostile to +1.0 cooperative). Measures how positively or negatively the article frames the opposing side of the strait, not geopolitical "stability." PRC source → how does it portray Taiwan? TW source → how does it portray the PRC?

**Urgency levels**: `flash` / `priority` / `routine`

**Source bias labels**: `green`, `green_leaning`, `blue`, `centrist`, `state_official`, `state_nationalist`

**Active TW sources**: LTN Politics/World/Business/Defence (green), CNA Politics/Mainland/International/Finance (green_leaning), UDN Cross-Strait/Breaking/International/Business (blue), CT Cross-Strait/Politics/Military/Opinion (blue), YDN (green_leaning — MND state media under DPP executive; reclassify if government changes)

**Active PRC sources**: Xinhua, People's Daily, China News Service, Global Times, The Paper, MFA Spokesperson, Taiwan Affairs Office, Guancha, Haixia Daobao, PLA Daily

**Active HK sources**: RTHK Greater China (state_official — post-NSL government-controlled), Ming Pao Cross-Strait/Editorial/Opinion (centrist)

**Active international sources**: Zaobao Cross-Strait (SG, centrist), BBC Chinese (UK, centrist). BBC Chinese articles are stored with only the RSS `<description>` summary — the full article page is Next.js client-side rendered and yields no extractable text via BeautifulSoup. This is sufficient for keyword filtering and AI analysis.

## Important Behaviors

- **All articles require analyst approval** (`analyst_approved=1`) before appearing on the public feed. New articles start at `analyst_approved=0`. Use the Approve button on the article card or resolve via the review queue (confirm/override auto-approves).
- Articles with `needs_human_review = 1` and unresolved status are **additionally hidden** until the review queue is resolved
- Chinese-language sources are treated as primary — they break stories earlier
- Bias labels reflect editorial reality and should not be softened (e.g. CNA is green_leaning, not neutral)
- The human review queue and inline analyst overrides exist because political classification requires editorial judgment — AI output is a starting point, not final word
- Deactivating a source (`is_active=0`) preserves all its historical articles; use this instead of deleting
- Key figure statements require **manual approval** before display — misattributing a quote to a senior political figure is a credibility-ender. Never auto-approve or bypass the `approval_status='pending'` gate.
- When updating `glossary.json` romanisations, the old romanisation must also be added to the relevant figure's `aliases` array in `key_figures.json` — historical entity rows in the DB will still have the old name and must still resolve.
- Sentiment axis measures how an article frames the **opposing side of the strait**, not geopolitical stability. Taiwan-US military cooperation does NOT score as cross-strait cooperative — it's neutral or hostile depending on PRC framing. KMT/opposition party visits to the mainland score cooperative regardless of political symbolism.
- Romanisation: use Wade-Giles/Tongyong for all Taiwanese entities (people, places, organisations); Hanyu Pinyin for PRC entities. Never leave a Chinese name untranslated — apply the appropriate system if no established romanisation exists.
- Key figure party colours: PRC → red (`#dc2626`), DPP → green (`#16a34a`), KMT → blue (`#1d4ed8`), TPP → teal (`#14B8A6`). Set via `party` field in `key_figures.json`; `figureAccent()` in `KeyFigures.jsx` resolves it.
- Sentiment score colour convention: **negative = hostile = purple** (`#7c3aed`), **positive = cooperative = amber** (`#f59e0b`), neutral (±0.3) = grey (`#6b7280`). Purple/amber was chosen to avoid conflict with source bias colours (PRC red, DPP green). Applies to gauges (`StatsSidebar.jsx`), `SentimentBadge.jsx`, chart tooltips (`SignalCharts.jsx`), and any future sentiment indicators.
