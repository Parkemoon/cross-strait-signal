# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Path-scoped rules in `.claude/rules/` cover subsystem details (loaded on demand when matching files are read):
- `scrapers.md` — scraper inventory, MAC/Comtrade/HK-CSD economic indicators, trade access, CIFER, investment-by-industry, all source-specific gotchas
- `ai-pipeline.md` — Tier 1/2/3 AI, glossary injection, entity canonical, key figure extraction, relevance gate, keyword pre-filter, social translator
- `database.md` — canonical DB path, schema conventions, `get_db()` pattern, migration pattern
- `api-routes.md` — per-route non-obvious rules, `VISIBLE` constant, scoping clauses
- `frontend.md` — React layout, central API client, read-only build, sync points, component-specific notes
- `deployment.md` — two-script deploy, schema migration block, cron schedule, RSSHub

## Project Overview

**Cross-Strait Signal** is an open-source intelligence dashboard monitoring PRC-Taiwan cross-strait dynamics through automated bilingual (Chinese-English) media analysis. Scrapes ~30 active news sources, processes articles through a multi-tier AI pipeline, and serves results via a React dashboard backed by FastAPI.

**Critical design intent**: The sentiment axis is bidirectional — destabilising signals from BOTH sides (PLA exercises AND DPP sovereignty moves) register equally. This is not a "China bad, Taiwan good" instrument.

**Major changes go on staging first.** The `/var/www/cross-strait-signal-staging` worktree (branch `staging`) is for structural work — new tables, new scrapers, new top-level UI sections, new API surface. Bug fixes, copy tweaks, and small doc edits can go on `main` directly. When in doubt, ask.

## Commands

### Backend setup
```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
pip install -r requirements.txt
python scripts/init_db.py
python scripts/seed_sources.py
```

### Running the app (2 terminals)
```bash
python -m uvicorn api.main:app --reload --port 8000   # backend at :8000
cd frontend && npm start                              # frontend at :3000
```

### Pipeline (scrape + AI + clustering)
```bash
python scripts/run_pipeline.py
```

### Maintenance scripts
- `scripts/backfill_key_figure_statements.py --days 30 --limit 200` — re-runs Tier 1 only on articles where a key figure entity was already detected.
- `scripts/refresh_officials.py` — Wikidata SPARQL pull for ~28 officeholder positions across TW/US/PRC/JP. Output is `scraper/processors/current_officials.json` — review the diff, then commit and deploy. Runtime ~80s. Positions config: `scripts/officials_positions.json` (hand-curated QIDs). Manual gap-fill at `scraper/processors/current_officials_manual.json` (manual wins on conflict). `current_officials.json` is generated; don't hand-edit it. Run after elections, cabinet reshuffles, or when officeholder hallucinations are spotted. Aborts (exit 1, no write) if it resolves far fewer current office-holders than the existing file — guards against a Wikidata outage silently gutting the roster.
- `scripts/merge_entities.py --dry-run` (then `--type person --threshold 0.9`) — interactive near-duplicate entity name merge. Flags: `--type`, `--days` (default 90), `--threshold` (default 0.85), `--min-mentions` (default 2), `--dry-run`. False positives to watch for: historically distinct place variants (Beiping ≠ Beijing), different people sharing a surname initial.
- `scripts/renormalise_entities.py` (dry-run by default; `--apply` to write) — re-applies `entity_canonical.json` to **existing** `entities` rows by **exact** Chinese-name match, rewriting `entity_name_en`. `_normalise_entity_name` only runs at extraction time, so editing the canonical JSON never touches rows already in the DB — run this after adding entries to back-fill history. Exact-match only on purpose (the pipeline's prefix logic would corrupt title-prepended rows, e.g. `國防部長顧立雄` → "Ministry of National Defense"); the trade-off is it won't fold genuine sub-forms (`解放軍海軍` under `解放軍`). Flags: `--scope all|backlog|approved` (default `all`), `--type` (e.g. `person`), `--db` (target another worktree's DB, e.g. prod), `--canon`, `--limit`. Idempotent. Companion to `merge_entities.py` (which clusters near-duplicate *English* spellings on approved rows only); this is the canonical-driven counterpart.
- `scripts/seed_nccu_polls.py` — backfills the NCCU ESC long trend series (1992–2025 identity; unification deferred until cleaner data) into `polls` + `poll_results` as `approved`. Data lives in `scraper/processors/nccu_esc_seed.json` — transcribed from NCCU's labelled trend chart PNG with per-year sum-to-100% cross-validation; sample sizes from the NCCU methodology PDF. Idempotent on `(pollster_id, fielded_start, reviewed_by='backfill:seed_nccu_polls')`. Re-run after adding new waves to the JSON.
- `scripts/canonicalise_poll_labels.py` (then `--apply`) — collapses option_label variants in `poll_results` to canonical strings. Rules live in `scraper/processors/poll_labels_canonical.json` (per-scope mapping list — `from_zh` / `from_en` match, `to_zh` / `to_en` write). Two seeded rules: (a) no-opinion normalisation across non-NCCU non-vote-intent keys → `未明確回答` / "No response"; (b) vote-intent normalisation (strip party prefixes, fix Su Chiao-hui romanisation, collapse "haven't decided" residuals to `尚未決定` / "Undecided", keep "won't vote" as a separate `不投票或投廢票` / "Won't vote / Spoiled ballot" bucket). Idempotent (skips rows already canonical). **Now also runs automatically as pipeline Step 3d** (`run_pipeline.py` invokes it with `--apply` after Step 3c), so drift self-heals every 6h — manual runs are only needed for ad-hoc checks or after editing the JSON. Edit the JSON to add new mappings; no code change needed.
- `scripts/weekly_digest.py` — builds the weekly editorial brief (Substack raw material) from the dashboard DB and emails it via Gmail SMTP. Sections: lead split-screen (biggest in-window cluster carried by BOTH a PRC and a TW source, with each side's headlines/quotes/sentiment/entity emphasis — the verification angle as narrative), sentiment divergence (per-side tone this window vs prior + top topic movers), social pulse (Weibo filtered to cross-strait via the same `PRC_MUST_MENTION_TAIWAN` list as `/api/social`; PTT by pushes), by-the-numbers (top clusters/entities), watch-list (new-formulation/escalation flags + poll waves fielded in-window). Counts only `analyst_approved=1` articles. Archives every run to a `weekly_digests` table (created on first run; sets up a future dashboard view). Flags: `--days` (default 7), `--db`, `--env-file`, `--to`, `--no-email`, `--no-archive`. SMTP creds (`SMTP_HOST/PORT/USER/PASS`, `DIGEST_TO`) live in `.env`. Runs weekly via cron (Mon 08:00) from the prod worktree so it hits the prod DB + prod `.env`.
- `scripts/backfill_diplomacy_statements.py --days 90 --limit 300` — back-populates `diplomacy_statements` (Phase 2c) from already-analysed articles. Shares `_insert_diplomacy_row` with the live Tier-1 pass (so org-exclusion + validation are identical). Flags: `--days`, `--limit`, `--topics`, `--all-topics`, `--db` (target another worktree's DB, e.g. prod), `--dry-run`. Rows land `pending` for the analyst review queue; safe to re-run.
- `scripts/build_world_geojson.py` — builds the Diplomacy map basemap `frontend/public/geo/world-110m.geojson` from Natural Earth 1:110m admin0 (trims to `iso_a2`/`name`/`lx`/`ly` label points, drops Antarctica). Output is committed; re-run only to refresh the basemap.
- `scripts/usage_report.py` — aggregates the per-call Gemini token-usage log (written by `scraper/utils/usage_log.py` to `$GEMINI_USAGE_LOG`, default `/var/log/gemini-usage.jsonl`) by pipeline stage / model / day. Token totals are exact; fill the `PRICES` dict for an estimated cost column. Flags: `--days`, `--by stage|model|day`, `--log`. Use it to attribute the Gemini bill before tuning cost.

### Frontend builds
```bash
cd frontend
npm install
npm run build          # admin bundle (needs .env sourced — see frontend.md)
npm run build:public   # public read-only bundle (no token, safe to run plain)
npm test
```

### API docs
Swagger UI at `http://localhost:8000/docs` when backend is running.

### Windows note
The project venv at `venv/` may be near-empty on Windows. Use `/c/Users/Ed/venv/Scripts/python.exe`. Always add `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` at the top of any script that prints Chinese text.

## Data flow

```
~30 RSS/HTML news sources
    → Keyword pre-filter (directional: saves ~80% API cost)
    → Tier 1 AI: Gemini 3.1 Flash Lite (topic, sentiment, entities, urgency)
        ↳ side-extract: military exercise candidates from MIL_EXERCISE
                        articles → military_exercises (status=pending)
        ↳ side-extract: third-country diplomatic stances on Taiwan →
                        diplomacy_statements (status=pending; intl orgs
                        excluded, EU bloc kept) → /api/diplomacy/*
    → Tier 2 AI: Gemini 3.5 Flash (escalation review, conditional)
    → Tier 3: Human review queue (model disagreements — translation editing + auto-approve on resolve)
    → Editorial approval gate (analyst_approved=0 until sign-off; hidden from public feed)
    → SQLite + FTS5 → FastAPI → React dashboard

Parallel pipelines (no AI processing):
    Weibo / PTT → social_pulse → Gemini batch translation
    MAC 7887/7459/7888 + UN Comtrade + HK CSD → economic_indicators → /api/economy/*
    BOFT + ECFA + MoF + curated bans → trade_access → /api/trade-access/*
    MAC 7478/7473 monthly snapshots → investment_by_industry → /api/economy/investment-by-industry
    CIFER portal (Playwright, monthly) → cifer_snapshots → /api/trade-access/cifer-snapshot
    TW NIA + curated PRC data → cross_strait_population → /api/economy/people-records
    MND daily briefing + PLATracker backfill → pla_incursions → /api/military/*

Exercise-only pass (Step 3b):
    YDN military articles the keyword pre-filter rejected → Tier 1 exercise
    extraction only (no full ai_analysis row written) → military_exercises
    → /api/military/exercises (analyst review queue, then map + list)

Poll-only pass (Step 3c):
    TW-side articles the keyword pre-filter rejected whose title carries
    民調/民意調查 → stripped poll-only Tier 1 prompt (no ai_analysis row
    written) → polls + pending_results_json (questions/options blob held
    until analyst assigns question_keys) → /api/polls/* (analyst review
    queue, then cross-pollster trend charts)

MAC poll pass (Step 2L):
    MAC 即時民調 配布表 PDFs (structured tables, not prose) → deterministic
    pdfplumber parse → polls + poll_results as APPROVED (no AI, no review
    queue) with config-driven canonical question_keys → /api/polls/*.
    See .claude/rules/scrapers.md → MAC Polls.

Poll-label canonicalise (Step 3d):
    scripts/canonicalise_poll_labels.py --apply runs after Step 3c as an
    idempotent drift-catcher, re-collapsing any variant option labels that
    slipped past the AI extraction prompt's canonical-label rules.
```

Event clustering (`scripts/cluster_events.py`) groups related articles within a 48-hour window using Jaccard similarity on title keywords (threshold: 0.25).

## Environment

Requires `.env` in project root:
```
GEMINI_API_KEY=your_key_here
ADMIN_TOKEN=...                # gates write endpoints AND admin-only reads (is_admin); also inlined into the admin frontend build
```

## Key domain concepts

**Topic taxonomy (28 categories)**: `MIL_EXERCISE`, `MIL_MOVEMENT`, `MIL_HARDWARE`, `MIL_POLICY`, `DIP_STATEMENT`, `DIP_VISIT`, `DIP_SANCTIONS`, `PARTY_VISIT`, `ARMS_SALES`, `ECON_TRADE`, `ECON_INVEST`, `ENERGY`, `SCI_TECH`, `POL_DOMESTIC_TW`, `POL_DOMESTIC_PRC`, `POL_TONGDU`, `INFO_WARFARE`, `CYBER`, `LEGAL_GREY`, `HUMANITARIAN`, `TRANSPORT`, `INT_ORG`, `US_PRC`, `US_TAIWAN`, `HK_MAC`, `CULTURE`, `SPORT`

Less-obvious categories:
- **POL_TONGDU** (統獨): Captures both unification rhetoric AND independence moves — bidirectional by design.
- **PARTY_VISIT**: KMT/opposition visits to PRC — distinct from `DIP_VISIT` (state-level). A KMT chair visiting Beijing is always `PARTY_VISIT`, never `DIP_VISIT`.
- **ARMS_SALES**: US or third-party arms transfer events and export control decisions. Use `MIL_POLICY` for broader defence posture; `MIL_HARDWARE` when a platform is the primary subject.
- **US_PRC**: US-China relations as the primary subject (Washington-Beijing diplomacy, tech/trade sanctions, Pacific deterrence) — not Taiwan's relationship with the US.
- **US_TAIWAN**: US-Taiwan relations — congressional legislation, US officials visiting Taiwanese counterparts, US statements on Taiwan's status.
- **HK_MAC**: Hong Kong and Macao with cross-strait relevance — "one country, two systems" credibility, Beijing governance. (Code is `HK_MAC`; display label is "HK/Macao" — don't rename the code, it exists in the DB.)
- **CULTURE**: Cross-strait cultural exchange and soft power. Use `POL_TONGDU` when cultural framing is explicitly about sovereignty.
- **CYBER**: Cyber operations, hacking, digital espionage, infrastructure intrusions — distinct from `INFO_WARFARE` (narrative/propaganda).
- **LEGAL_GREY**: Grey-zone coercion below armed-conflict threshold — coast guard confrontations, sand dredging, undersea cable incidents, quasi-military harassment using civilian or law-enforcement vessels.
- **SPORT**: Sport with cross-strait political dimensions — Olympic naming ("Chinese Taipei"), athletic competitions, sport as soft power.
- **SCI_TECH**: Civilian/dual-use technology — semiconductor industry, chip/tech export controls, space, AI, scientific exchanges, tech talent flows. Use `ECON_TRADE` for broad trade sanctions; `CYBER` for intrusion operations; `ARMS_SALES` for defence hardware.
- **ENERGY**: Energy security with cross-strait relevance — LNG imports, nuclear policy, shipping lane economics, PRC energy leverage.
- **POL_DOMESTIC_TW / POL_DOMESTIC_PRC**: Classified by the *subject* of the article, not the source country.

**Sentiment values**: `hostile` / `cooperative` / `neutral` / `mixed` with numeric score (−1.0 hostile to +1.0 cooperative). Measures how positively or negatively the article frames the **opposing side of the strait**, not geopolitical "stability." PRC source → how does it portray Taiwan? TW source → how does it portray PRC? Taiwan-US military cooperation does NOT score as cross-strait cooperative — it's neutral or hostile depending on PRC framing. KMT visits to the mainland score cooperative regardless of political symbolism.

**Urgency levels**: `flash` / `priority` / `routine`

**Source bias labels**: `green`, `green_leaning`, `centrist`, `blue_leaning`, `blue`, `state_official`, `state_nationalist`. Canonical roster in `seed_sources.py`. Source-specific judgement calls worth keeping:
- **YDN** is `green_leaning` because it's MND state media under the current DPP executive — reclassify if the government changes.
- **RTHK** is `state_official` post-NSL.
- **BBC Chinese** stores only the RSS `<description>` summary — the article page is Next.js CSR and yields no extractable text via BeautifulSoup. Sufficient for keyword filtering + AI analysis; don't waste time rebuilding the content scraper.

**Romanisation**: Wade-Giles/Tongyong for Taiwanese entities (people, places, organisations); Hanyu Pinyin for PRC entities. Never leave a Chinese name untranslated — apply the appropriate system if no established romanisation exists.

**Sentiment colour convention**: negative = hostile = purple (`#7c3aed`), positive = cooperative = amber (`#f59e0b`), neutral (±0.3) = grey (`#6b7280`). Purple/amber chosen to avoid conflict with source bias colours (PRC red, DPP green). Applies to gauges, `SentimentBadge`, chart tooltips, and any future sentiment indicators.

**Party colours (canonical, Wikipedia-derived)**: single source of truth is `frontend/src/partyColours.js` (`PARTY_COLOURS`), shared by Key Figures (`figureAccent()`) and the poll trend charts. DPP `#1B9431` · KMT `#000099` · TPP `#28C7C7` · NPP `#FFE31A` · TSP `#A73F24` · GPT (Green Party) `#3AB483` · NP (New Party) `#FFD700` · PFP `#FF6310` · CUPP `#253686` · IND (independent) `#6b7280`. `PRC` `#dc2626` is retained for PRC-side figures / state-pollster chips / CCP series (not a party row in the picker). Poll-chart options resolve a party via `poll_option_parties` (analyst-assigned, keyed on `option_label_zh`) → key_figures `party` fallback → positional palette; a per-option `colour_override` hex wins. Key figures set `party` in `key_figures.json`.

## Important behaviours

- **All articles require analyst approval** (`analyst_approved=1`) before appearing on the public feed. New articles start at `analyst_approved=0`. Approve via the article card or via review-queue confirm/override (which auto-approves).
- Articles with `needs_human_review=1` and unresolved status are **additionally hidden** until the review queue is resolved.
- **Admin-only reads are gated server-side** when `ADMIN_TOKEN` is set: the non-raising `is_admin` dependency means `include_pending`, single-article + cluster visibility, and the `/candidates` queues only return unapproved rows to a valid `X-Admin-Token` (the public build sends none). Falls back to legacy nginx-only mode when `ADMIN_TOKEN` is unset. Detail in `.claude/rules/api-routes.md`.
- Chinese-language sources are treated as primary — they break stories earlier.
- Bias labels reflect editorial reality and should not be softened (e.g. CNA is `green_leaning`, not neutral).
- The human review queue and inline analyst overrides exist because political classification requires editorial judgment — AI output is a starting point, not the final word.
- Deactivating a source (`is_active=0`) preserves all its historical articles; use this instead of deleting.
- **Key figure statements require manual approval** — misattributing a quote to a senior political figure is a credibility-ender. Never auto-approve or bypass `approval_status='pending'`.
- When updating `glossary.json` romanisations, the old romanisation must also be added to the relevant figure's `aliases` array in `key_figures.json`, and the entry must be updated in `entity_canonical.json` — historical entity rows in the DB will still have the old name and must still resolve.
