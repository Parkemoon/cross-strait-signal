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
- `scripts/backfill_key_figure_statements.py --days 30 --limit 200` — re-runs Tier 1 only on articles where a key figure entity was already detected.
- `scripts/refresh_officials.py` — Wikidata SPARQL pull for ~28 officeholder positions across TW/US/PRC/JP. Output is `scraper/processors/current_officials.json` — review the diff, then commit and deploy. Runtime ~80s. Positions config: `scripts/officials_positions.json` (hand-curated QIDs). Manual gap-fill at `scraper/processors/current_officials_manual.json` (manual wins on conflict). `current_officials.json` is generated; don't hand-edit it. Run after elections, cabinet reshuffles, or when officeholder hallucinations are spotted. Aborts (exit 1, no write) if it resolves far fewer current office-holders than the existing file — guards against a Wikidata outage silently gutting the roster.
- `scripts/merge_entities.py --dry-run` (then `--type person --threshold 0.9`) — interactive near-duplicate entity name merge. Flags: `--type`, `--days` (default 90), `--threshold` (default 0.85), `--min-mentions` (default 2), `--dry-run`. False positives to watch for: historically distinct place variants (Beiping ≠ Beijing), different people sharing a surname initial.
- `scripts/renormalise_entities.py` (dry-run by default; `--apply` to write) — re-applies `entity_canonical.json` to **existing** `entities` rows, rewriting `entity_name_en`. `_normalise_entity_name` only runs at extraction time, so editing the canonical JSON never touches rows already in the DB — run this after adding entries to back-fill history. Uses the SAME shared resolver as the pipeline (`shared/entity_norm.py`: exact match → explicit title-strip `國防部長顧立雄`→顧立雄 → opt-in fold prefixes `漢光41號演習`→漢光41), so the back-fill can repair everything the write path would produce — see `.claude/rules/ai-pipeline.md` for the three-table JSON structure and the fold-prefix hazards. Flags: `--scope all|backlog|approved` (default `all`), `--type` (e.g. `person`), `--db` (target another worktree's DB, e.g. prod), `--canon`, `--limit`. Idempotent. Companion to `merge_entities.py` (which clusters near-duplicate *English* spellings on approved rows only); this is the canonical-driven counterpart.
- `scripts/seed_nccu_polls.py` — backfills the NCCU ESC long trend series (identity 1992–, unification 1994–, through the 2026 June interim) into `polls` + `poll_results` as `approved`. Data lives in `scraper/processors/nccu_esc_seed.json` — transcribed from NCCU's labelled trend chart PNG with per-year sum-to-100% cross-validation; sample sizes from the NCCU methodology PDF. NCCU publishes twice yearly: waves flagged `"interim": true` carry the June release (Jan–Jun surveys, `fielded_end=YYYY-06-30`); when the December final lands, drop the flag, update the numbers and re-run — the upsert on `(pollster_id, fielded_start, reviewed_by='backfill:seed_nccu_polls')` overwrites the same row. Run on BOTH worktrees (DBs are separate).
- `scripts/canonicalise_poll_labels.py` (then `--apply`) — collapses option_label variants in `poll_results` to canonical strings. Rules live in `scraper/processors/poll_labels_canonical.json` (per-scope mapping list — `from_zh` / `from_en` match, `to_zh` / `to_en` write; scopes take `question_keys` and/or `families` + `exclude_*` variants — family scoping covers future keys, e.g. every new 2026 race, without re-enumeration). Two seeded rules: (a) no-opinion normalisation across non-NCCU non-vote-intent keys → `未明確回答` / "No response"; (b) vote-intent normalisation (strip party prefixes, fix Su Chiao-hui romanisation, collapse "haven't decided" residuals to `尚未決定` / "Undecided", keep "won't vote" as a separate `不投票或投廢票` / "Won't vote / Spoiled ballot" bucket). Idempotent (skips rows already canonical). **Now also runs automatically as pipeline Step 3d** (`run_pipeline.py` invokes it with `--apply` after Step 3c), so drift self-heals every 6h — manual runs are only needed for ad-hoc checks or after editing the JSON. Edit the JSON to add new mappings; no code change needed.
- `scripts/weekly_digest.py` — builds the weekly editorial brief (Substack raw material) from the dashboard DB and emails it via Gmail SMTP. Sections: lead split-screen (biggest in-window cluster carried by BOTH a PRC and a TW source, with each side's headlines/quotes/sentiment/entity emphasis — the verification angle as narrative), sentiment divergence (per-side tone this window vs prior + top topic movers), social pulse (Weibo filtered to cross-strait via the same `PRC_MUST_MENTION_TAIWAN` list as `/api/social`; PTT by pushes), by-the-numbers (top clusters/entities), watch-list (new-formulation/escalation flags + poll waves fielded in-window). Counts only `analyst_approved=1` articles. Archives every run to a `weekly_digests` table (created on first run; sets up a future dashboard view). Flags: `--days` (default 7), `--db`, `--env-file`, `--to`, `--no-email`, `--no-archive`. SMTP creds (`SMTP_HOST/PORT/USER/PASS`, `DIGEST_TO`) live in `.env`. Runs weekly via cron (Mon 08:00) from the prod worktree so it hits the prod DB + prod `.env`.
- `scripts/check_scraper_health.py` — staleness monitor for every article source + dedicated-table pipeline (48 checks). Compares each source/table's newest row against a per-check threshold (in-script: `ARTICLE_OVERRIDES` / `TABLE_CHECKS` — low-cadence sources like TAO/PLA Daily/poll scrapers get looser limits; a `None` threshold disables a check, currently UN Comtrade since PRC stopped reporting after 2024-12). Emails (`HEALTH_TO`, fallback `DIGEST_TO`) on state changes only — newly stale or recovered — so an outage alerts once, not daily; state in `/var/log/scraper-health-state.json`. Flags: `--db`, `--env-file`, `--state-file`, `--to`, `--no-email` (print table only), `--force-email`. Daily via cron (08:15) from the prod worktree. When adding a source or pipeline table, add/adjust its threshold here.
- `scripts/backfill_diplomacy_statements.py --days 90 --limit 300` — back-populates `diplomacy_statements` (Phase 2c) from already-analysed articles. Shares `_insert_diplomacy_row` with the live Tier-1 pass (so org-exclusion + validation are identical). Flags: `--days`, `--limit`, `--topics`, `--all-topics`, `--db` (target another worktree's DB, e.g. prod), `--dry-run`. Rows land `pending` for the analyst review queue; safe to re-run.
- `scripts/build_world_geojson.py` — builds the Diplomacy map basemap `frontend/public/geo/world-110m.geojson` from Natural Earth 1:110m admin0 (trims to `iso_a2`/`name`/`lx`/`ly` label points, drops Antarctica). Output is committed; re-run only to refresh the basemap.
- `scripts/usage_report.py` — aggregates the per-call Gemini token-usage log (written by `scraper/utils/usage_log.py` to `$GEMINI_USAGE_LOG`, default `/var/log/gemini-usage.jsonl`) by pipeline stage / model / day. Token totals are exact; the `PRICES` dict carries the cost rates (verified against Google's sheet 2026-07-08, incl. the 50%-rate `@batch` model variants) — re-verify when Google reprices. Flags: `--days`, `--by stage|model|day`, `--log`. Use it to attribute the Gemini bill before tuning cost.
- `scripts/dedup_diplomacy.py` (dry-run default; `--apply`) — semantic dedup for approved `diplomacy_statements`: buckets by (country, official/non-official), embeds with `gemini-embedding-001`, union-find clusters at cosine ≥ `--threshold` (0.86), merges to the member nearest the cluster median stance, quarantines wide-spread clusters (genuine timelines), flattens merge chains. Flags: `--db`, `--country`, `--threshold`, `--quarantine-spread`. Run after big review sessions or monthly — replaces the 2026-06-30 scratchpad passes.
- `scripts/sweep_alt_models.py --model deepseek/deepseek-v4-flash --arm neutral --limit 10 --dry-run` — alt-model comparison experiment: re-runs APPROVED articles through Chinese LLMs via OpenRouter with the byte-identical Tier-1 prompt, one `alt_model_analysis` row per (article, model, arm) whatever the outcome (`ok`/`refused`/`parse_error`/`api_error` — refusals are findings). Arms: `neutral` (provider-pinned Western hosts, data never touches PRC) / `originator` (model creator's endpoint via OpenRouter — censorship isolation) / `gemini-control` (current production Gemini on the same articles, for prompt-drift attribution). Flags: `--days`, `--limit` (default 25), `--per-topic` (stratified), `--match-model` (pair subsets), `--article-ids`, `--db`, `--retry-errors`, `--sleep`, `--probe` (one-token routing check per arm — run BEFORE any sweep; OpenRouter account data-policy settings can silently 404 an arm). Needs `OPENROUTER_API_KEY` in `.env`. NEVER feeds editorial queues (side-extracts stay in `raw_response`). Admin UI: per-article panel on the card + Alt Models tab + feed model-lens toggle (re-renders the Signal Feed through a swept (model, arm)'s classifications). Launch big sweeps detached (`setsid nohup`). See `.claude/rules/ai-pipeline.md` → Alt-model experiment.
- `scripts/audit_diplomacy_offaxis.py` (dry-run default; `--apply`) — two-pass off-axis audit of approved `diplomacy_statements` (detect in batches → conservative KEEP-biased confirm per flagged row → dismiss with a dated `offaxis-audit-*` tag; sole-statement countries held back). Flags: `--db`, `--model`, `--country`, `--limit`. Quarterly, or after approving a large backfill — replaces the 2026-07-01 scratchpad detector.
- `scripts/alt_model_aggregates.py --db /path/to/prod.db` — read-only agreement aggregates for the alt-model experiment (outcome counts, topic agreement overall/conditional-on-relevant/paired, NR decomposition, sentiment deltas, urgency/escalation match). Companion to `audit_terminology_markers.py` (which covers terminology/framing); together they reproduce every number in `ALT_MODEL_EXPERIMENT_WRITEUP.md` (§7).
- `scripts/alt_model_monthly_report.py` — emails the live `alt_model_aggregates.py` output next to the FROZEN write-up reference table (embedded in-script — update it when the write-up is revised) so the Alt Models tab's findings text gets a monthly 2-minute review. Same SMTP env as the digest. Flags: `--db`, `--env-file`, `--to`, `--no-email`. Monthly via cron (1st 08:30) from the prod worktree once the alt-model UI deploys; the daily full-window incremental sweep cron + `check_scraper_health.py`'s `alt_model:v4f_sweep` staleness check (5-day threshold) keep the underlying data live — see `.claude/rules/deployment.md` → Cron schedule.
- `scripts/sweep_direct_questions.py --print-battery --db …` (then `--probe`, then the sweep) — direct-question arm of the alt-model experiment: sends the `data/direct_questions.json` battery (literature-calibration / cross-strait-direct / Tier-1-scaffold-hybrid / control bands, matched en/zh pairs, bare prompts, n=5 per cell) to the Western-hosted arms + the V4F `originator` cell (DeepSeek's own endpoint, run 2026-08-28 — see ai-pipeline.md for the guardrail/revision/thinking-mode gotchas) + `deepseek/deepseek-r1-0528` (generation disambiguator, fp4 — see `RUN_NOTES.md`) + gemini-control. Own table `direct_question_runs`; never mixes with article-sweep rows. Companion `scripts/direct_question_aggregates.py --db … --examples …` emits the hand-review JSONL — no refusal number is publishable unread. Findings: `DIRECT_QUESTION_WRITEUP.md` (every number reproducible from the aggregates script). See `.claude/rules/ai-pipeline.md` → Direct-question arm.
- `scripts/bulk_approve_articles.py [--db …] [--apply] [--renormalise] [--force] [--quiet]` — clears the feed backlog: approves every analysed, non-hidden article with no unresolved review flag (articles ONLY — the four editorial queues are never touched). Dry-run default; aborts on consistency failures (taxonomy/sentiment/score/urgency enums, empty summary, duplicate `ai_analysis` rows) unless `--force`; `--renormalise` runs the entity resolver dry-run first and aborts on drift. Prints the attention report (held review rows, flash, escalation signals, new formulations, |score| ≥ 0.8, reported-speech net hits) so the analyst eyeballs only what matters; `--apply` writes a revert manifest (`bulk-approve-<db>-<ts>.manifest`, gitignored) before touching the DB. Replaces the five ad-hoc scratchpad runs.
- `scripts/dedup_articles.py` (dry-run default; `--apply` hides + writes a revert manifest) — same-outlet duplicate article sweep. Detection in `shared/article_dedup.py` (R1 identical content ≤7d / R2 content trigram-Jaccard ≥0.90 ≤72h / R3 title match same-day only — thresholds are MEASURED against the YDN daily PLA-dynamics report, a legitimate same-title series whose templated content runs to 0.80 similarity, and whose short quiet-day variant forces the 200-char content-rule floor; don't retune without re-measuring). Same source only — cross-outlet duplication (agency copy, PRC state messaging) is signal and never touched. Dupes are hidden (`is_hidden=1`, richest copy kept), never deleted. **Also runs every tick as pipeline Step 2m** (8-day window, unanalysed rows included) so an SEO re-push is hidden BEFORE Tier-1 pays for it; the Tier-1/3b/3c selection queries, clustering, and the weekly digest all exclude `is_hidden=1`. Flags: `--db`, `--days`, `--all` (include unanalysed; CLI default is analysed-only), `--apply`. Idempotent.
- `scripts/build_coast_guard_zones.py` — rebuilds `data/coast_guard_zones.geojson` (+ the `frontend/public/geo/` copy) for the Coast Guard tracker: Kinmen from the county gazette's official control points, Matsu bands, median-line band, 24 nm sectors, Pratas, east box. Output is committed; re-run only to retune. `scripts/refresh_coast_guard_roster.py` (`--dry-run`, `--force CCG|CGA|JCG|USCG`, `--db`) — rebuilds `coast_guard_vessels` from GFW's identity index with anomaly flags; monthly or after a backfill. `scripts/triage_coast_guard_roster.py [--db] [--dry-run]` — deterministic roster triage: confirms every hull with an explicit force name or a force-matching MID prefix, rejects (and purges the presence of) hulls the classifier no longer accepts, leaves the residual `auto`; anomaly flags are never a criterion (they're recorded AIS facts, unverifiable from a desk). Runs automatically after every roster refresh and every nightly presence pull; by hand only for a check. `scripts/backfill_coast_guard.py --start 2020-01-01 [--zones a,b] [--force] [--db]` — resumable monthly presence backfill (launch detached; ~880 pulls from 2020). See `.claude/rules/scrapers.md` → Coast Guard presence.
- `scripts/backfill_cga_enforcement.py [--db] [--skip-yearbooks|--skip-monthly|--skip-manual]` — backfills `cga_enforcement` (the Coast Guard tracker's Taiwan-side mirror series) from the CGA yearbooks + linked monthly reports + the transcribed 護永專案 table. Idempotent. See `.claude/rules/scrapers.md` → CGA enforcement statistics.
- `scripts/audit_summary_completeness.py --db /path/to/prod.db --out … --examples …` — omission-side audit for the alt-model experiment (write-up §5.6): per shared article, diffs production-extracted entities against each model's summary + its own `entities[]` extraction, and checks key-quote carry-over (char-trigram Jaccard). Closes the hole marker-scanning can't see (a model silently *not writing* something). gemini-control = run-to-run noise floor. Matching is hyphen/plural/paren-abbreviation-tolerant with glossary + key-figure alias expansion; read-only; deterministic, seconds.

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
    GFW 4Wings presence (Step 2n, nightly) → coast_guard_presence/vessels/pulls
        → roster triage (deterministic) → /api/military/coast-guard/* (Maritime tab)
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
- **Site prose is editable in the admin UI** (`data/site_copy.json` → `GET /api/copy/` → `<Copy k=…>`; admin ✎ → `PATCH /api/copy/{key}`). Adding a block = add the key to the JSON first (`tests/test_site_copy.py` enforces it). Edits land on the SERVER's copy of the file (prod when editing prod) and dirty that tree — sync prod → staging before content changes, same as `positions.json`. Chrome (labels/buttons) stays in code. **Chinese on the page only when it is the source's own words** — never translated chrome (`.claude/rules/frontend.md`).
- **Navigation is grouped** (`frontend/src/navGroups.js`): Feed · Security ▾ (Military, Maritime) · Economy ▾ (Indicators, Trade Access, People) · Politics ▾ (Polls, Diplomacy, Positions) · Admin ▾. Maritime sits beside Military on purpose — coast guards are law enforcement, not military. Adding a tab = one `NAV_GROUPS` entry + a render branch in `App.js`.
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
