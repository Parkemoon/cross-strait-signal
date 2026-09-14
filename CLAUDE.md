# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Path-scoped rules in `.claude/rules/` cover subsystem details (loaded on demand when matching files are read):
- `scrapers.md` — scraper inventory, MAC/Comtrade/HK-CSD economic indicators, trade access, CIFER, investment-by-industry, all source-specific gotchas
- `ai-pipeline.md` — Tier 1/2/3 AI, glossary injection, entity canonical, key figure extraction, relevance gate, keyword pre-filter, social translator
- `database.md` — canonical DB path, schema conventions, `get_db()` pattern, migration pattern
- `api-routes.md` — per-route non-obvious rules, `VISIBLE` constant, scoping clauses
- `frontend.md` — React layout, central API client, read-only build, sync points, component-specific notes
- `deployment.md` — two-script deploy, versioned schema migrations (`db/migrations/` + `scripts/migrate.py`), cron schedule, RSSHub

## Project Overview

**Cross-Strait Signal** is an open-source intelligence dashboard monitoring PRC-Taiwan cross-strait dynamics through automated bilingual (Chinese-English) media analysis. Scrapes ~30 active news sources, processes articles through a multi-tier AI pipeline, and serves results via a React dashboard backed by FastAPI.

**Critical design intent**: The sentiment axis is bidirectional — destabilising signals from BOTH sides (PLA exercises AND DPP sovereignty moves) register equally. This is not a "China bad, Taiwan good" instrument.

**Update `CHANGELOG.md` at the end of every session** (dated section under *Delivered*, prune *In progress / planned*) — it is the human-readable history; `git log --since=<last entry>` is the source. Companion to the gitignored `SESSION_LOG.md` handoff.

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
Catalogued in `.claude/rules/scripts.md` (path-scoped to `scripts/**`, so it loads only when a script is being read or edited). Each entry carries the flags, the gotchas and when to run it.

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
    → Same-outlet dedup (Step 2m: deterministic, no AI — hides same-source
      SEO re-pushes/rewrites before Tier-1; cross-outlet dupes untouched)
    → Keyword pre-filter (directional: saves ~80% API cost)
    → Tier 1 AI: Gemini 3.1 Flash Lite (topic, sentiment, entities, urgency)
        ↳ via the Gemini BATCH API by default (~50% token price): submit
          backlog as one job, collect on the same tick when it finishes
          within the wait window, else next tick. GEMINI_TIER1_MODE=
          interactive restores the sequential path. See ai-pipeline.md.
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
    GFW 4Wings presence (Step 2n, every 6-hourly tick) → coast_guard_presence/vessels/pulls
        → roster triage (deterministic) → /api/military/coast-guard/* (Maritime tab)
        ↳ the SAME response's non-coast-guard CHN/TWN rows → maritime_civil_daily /
          _presence / _vessels (Phase 2g civilian-fleet layer; militia = roster citation only)
    GFW Sentinel-1 SAR detections (Step 2p, trailing 120 d, once a day per zone — product
        lags ~2 months) → maritime_sar_daily (matched-to-AIS vs unmatched = the radar
        CEILING to the AIS floor) → /api/military/maritime/* (Maritime tab, second section)
    CGA 績效統計月報 / 年報 PDFs (Step 2o) → cga_enforcement → /api/military/coast-guard/enforcement
        (the Taiwan-side MIRROR of the presence series — always charted together)

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

Cross-strait visits pass (Step 3e):
    Analysed DIP_VISIT / PARTY_VISIT articles (not yet visit-scanned) →
    visits-only prompt (scraper/processors/visits_extract.py, one call
    each) → cross_strait_visits (status=pending; cross-strait scope
    enforced in code via the affiliation enum) → pre-queue dedup
    (shared/visit_dedup.py: one keeper per visitor + direction +
    ≤21-day date chain; per-article dupes marked merged) → /api/visits/*
    (analyst review queue with merge picker, then Politics ▾ Visits tab)

Name lookup (Step 3f):
    Taiwan-side person entities from Tier 1 with no `name_registry` row →
    Wikidata exact label (auto-approve only when clean) → grounded search
    with URL check (pending) → generated Wade-Giles (pending) → Admin ▾
    Names queue. Approved rows join glossary.json + entity_canonical.json
    at run time (shared/name_registry.py): the prompt-time terminology
    block, the entity resolver and a rewrite of the model's own rendering
    in title/summary/quote/reasoning all read the merged map.

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

Optional: `GEMINI_TIER1_MODE=interactive` (Tier 1 defaults to the Batch API — this restores the sequential per-article path), `TIER1_BATCH_WAIT_MIN` (same-tick batch collection window, default 20 minutes; 0 = never wait, always collect next tick), `OPENROUTER_API_KEY` (alt-model comparison sweeps only — `scripts/sweep_alt_models.py`).

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

**Source bias labels**: `green`, `green_leaning`, `centrist`, `china_centrist`, `blue_leaning`, `blue`, `state_official`, `state_nationalist`. Canonical roster in `seed_sources.py`. Source-specific judgement calls worth keeping:
- **YDN** is `green_leaning` because it's MND state media under the current DPP executive — reclassify if the government changes.
- **RTHK** is `state_official` post-NSL.
- **Ming Pao** is `china_centrist` (muted-rose badge), not plain `centrist` — editorially moderate but Beijing-accommodating, distinct from genuinely neutral internationals (BBC, Zaobao). `china_centrist` is a China-leaning centrist band, not a PRC state organ; **China Taiwan Net** (中国台湾网, the TAO news portal) is a full `state_official`.
- **BBC Chinese** stores only the RSS `<description>` summary — the article page is Next.js CSR and yields no extractable text via BeautifulSoup. Sufficient for keyword filtering + AI analysis; don't waste time rebuilding the content scraper.

**Romanisation**: Wade-Giles/Tongyong for Taiwanese entities (people, places, organisations); Hanyu Pinyin for PRC entities. Never leave a Chinese name untranslated — apply the appropriate system if no established romanisation exists.

**Sentiment colour convention**: negative = hostile = purple (`var(--hostile)`), positive = cooperative = amber (`var(--coop)`), neutral (±0.3) = grey (`var(--neut)`) — tokens in `frontend/src/index.css` (light + dark values; since the 2026-09 Morning Brief redesign the hues are muted paper-register, but the purple/amber split is locked). Purple/amber chosen to avoid conflict with source alignment colours (PRC red, DPP green). Band thresholds live once in `frontend/src/sentimentBand.js` (`bandColour`) — import it, never re-implement ±0.3. Applies to gauges, `SentimentBadge`, the masthead ticker, chart tooltips, and any future sentiment indicators.

**Party colours**: single source of truth is `frontend/src/partyColours.js` (`PARTY_COLOURS`), shared by Key Figures (`figureAccent()`) and the poll trend charts. Since the 2026-09 redesign the values are `var(--party-*)` CSS custom properties defined in `index.css` (light + dark, muted paper-register derivatives of the Wikipedia canonicals): DPP→`--green`, KMT→`--blue`, TPP→`--cyan` (TPP owns cyan — it no longer means cooperative), PRC→`--red` for PRC-side figures / state-pollster chips / CCP series (not a party row in the picker); minor parties (NPP/TSP/GPT/NP/PFP/CUPP) have their own muted tokens, IND = `--muted`. **Never concatenate an alpha suffix onto these** — they're `var()` strings; use `partyTint()` / `color-mix()`. Poll-chart options resolve a party via `poll_option_parties` (analyst-assigned, keyed on `option_label_zh`) → key_figures `party` fallback → positional palette; a per-option `colour_override` hex wins. Key figures set `party` in `key_figures.json`.

## Important behaviours

- **All articles require analyst approval** (`analyst_approved=1`) before appearing on the public feed. New articles start at `analyst_approved=0`. Approve via the article card or via review-queue confirm/override (which auto-approves).
- Articles with `needs_human_review=1` and unresolved status are **additionally hidden** until the review queue is resolved.
- **Admin-only reads are gated server-side** when `ADMIN_TOKEN` is set: the non-raising `is_admin` dependency means `include_pending`, single-article + cluster visibility, and the `/candidates` queues only return unapproved rows to a valid `X-Admin-Token` (the public build sends none). Falls back to legacy nginx-only mode when `ADMIN_TOKEN` is unset. Detail in `.claude/rules/api-routes.md`.
- Chinese-language sources are treated as primary — they break stories earlier.
- Bias labels reflect editorial reality and should not be softened (e.g. CNA is `green_leaning`, not neutral).
- The human review queue and inline analyst overrides exist because political classification requires editorial judgment — AI output is a starting point, not the final word.
- Deactivating a source (`is_active=0`) preserves all its historical articles; use this instead of deleting.
- **Key figure statements require manual approval** — misattributing a quote to a senior political figure is a credibility-ender. Never auto-approve or bypass `approval_status='pending'`.
- **Site prose is editable in the admin UI** (`data/site_copy.json` → `GET /api/copy/` → `<Copy k=…>`; admin ✎ → `PATCH /api/copy/{key}`). Adding a block = add the key to the JSON first (`tests/test_site_copy.py` enforces it). Edits land on the SERVER's copy of the file (prod when editing prod) and dirty that tree — sync prod → staging before content changes, same as `positions.json`. Chrome (labels/buttons) stays in code. **Chinese on the page only when it is the source's own words** — never translated chrome (`.claude/rules/frontend.md`).
- **Navigation is grouped** (`frontend/src/navGroups.js`): Feed · Security ▾ (Military, Maritime) · Economy ▾ (Indicators, Trade Access, People) · Politics ▾ (Polls, Diplomacy, Visits, Positions) · Admin ▾ · About (direct page). Maritime sits beside Military on purpose — coast guards are law enforcement, not military. Adding a tab = one `NAV_GROUPS` entry + a render branch in `App.js`. Layout since the 2026-09 Morning Brief redesign: the Feed is a twin-rail brief (stats rail | 820px column | social rail); every other view is a single-column reading document — see `.claude/rules/frontend.md`.
- **Person names live in three places that must agree**: `glossary.json` (prompt-time), `entity_canonical.json` (resolver + `renormalise_entities.py` history repair) and the `name_registry` table (live growth from Step 3f + the Admin ▾ Names queue; approved rows override both files at run time). Add a name to the two JSON files (both scripts) and re-seed, or approve it in the queue and `seed_name_registry.py --export`. `renormalise_entities.py` and `collapse_entity_spellings.py` layer the approved registry over the JSON canon (registry wins, as on the write path), so keep the two files and the registry saying the same thing — a disagreement makes the spelling ping-pong (`tests/test_name_files_agree.py` enforces one English form per shared key, every person in both files, both scripts). Taiwanese people keep Wade-Giles / their own established English name even in simplified-script PRC articles — the Tier-1 rule now carries the syllable table and the affiliation-not-script test (trial 2026-09-13). English forms follow the house style in `shared/name_style.py` (no commas; Taiwanese three-character names `Surname First-name`; Japanese surname-first; adopted English names and the Hanyu forms Ed chose untouched) — applied at the registry upsert and the Names routes, `scripts/restyle_names.py` for catch-up. History follows in two steps: `renormalise_entities.py` for the entity rows, then `renormalise_prose.py` for the English title / summary / quote / reasoning (renderings recovered from the text by exact reading, `shared/prose_names.py`).
- When updating `glossary.json` romanisations, the old romanisation must also be added to the relevant figure's `aliases` array in `key_figures.json`, and the entry must be updated in `entity_canonical.json` — historical entity rows in the DB will still have the old name and must still resolve.

## OSINT Navigator CLI

Use the navigator CLI for OSINT tool recommendations.
`navigator tools find "<task>"` returns matching tools; `navigator tools show <tool-id>` returns the full record and documentation.
Return tool names, URLs, and concise reasons for each recommendation.
Do not invent tools or URLs; if there is no good match, say so and suggest a broader query.

Install notes: `navigator` is a pipx install at `/root/.local/bin/navigator` (not on PATH in tool
calls — use the full path or export `~/.local/bin`), logged in on Ed's pro membership. The token lives
in a `keyrings.alt` file keyring (headless box, no OS keychain) — never ask for, print, or handle it.
`navigator auth status` checks the connection; if it's disconnected, tell Ed to run
`! navigator auth login <email>` (magic link). `navigator skill print` shows the bundled SKILL.md with
the full evidence rules (cite the underlying source URL; treat sanctions/PEP/identity hits as leads).
