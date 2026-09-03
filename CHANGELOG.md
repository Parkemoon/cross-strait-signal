# Changelog

Development history for Cross-Strait Signal. Items are grouped by
delivery state rather than version — the project ships continuously
to a single production deploy.

**Maintenance rule: update this file at the end of every working session**, alongside
`SESSION_LOG.md` — add a dated section under *Delivered* for what shipped (or landed on
`staging`), and prune *In progress / planned*. `git log --since=<last entry date>` is
the source; a session that only touches docs/memory still gets a one-liner. This file
went stale for seven weeks (2026-07-08 → 2026-08-27) once — don't let it again.

## Delivered

### Pipeline + classification

- Multi-source bilingual scraping (RSS + HTML)
- Directional keyword pre-filter (saves ~80% API costs)
- Three-tier AI analysis pipeline with human review queue
- Source bias taxonomy (green / green_leaning / centrist / blue_leaning / blue / state_official / state_nationalist)
- Sentiment audit trail (`sentiment_reasoning`) — one-sentence quoted evidence per non-neutral score
- Sentiment consistency validation — label/score band mismatches and unsupported directional claims auto-flagged to human review queue
- Wikidata-driven officials roster with auto-refresh script (`scripts/refresh_officials.py`) — ~28 positions across TW/US/PRC/JP, injected into every prompt
- Entity name merge CLI (`scripts/merge_entities.py` — fuzzy clustering, interactive merge)
- Editorial accuracy reporting (`scripts/accuracy_report.py`) — override rates + per-topic dismissal + reclassification target distribution

### Sources

- LTN (Politics, World, Business, Defence)
- CNA (Politics, Mainland, International, Finance)
- China Times sections via self-hosted RSSHub (chromium-bundled)
- UDN HTML scraper (Cross-Strait, Breaking, International, Business)
- YDN (ROC MND newspaper) — green_leaning under DPP executive
- Provincial PRC media (海峽導報, 解放軍報, 观察者网)
- HK sources — RTHK Greater China, Ming Pao (Cross-Strait, Editorial, Opinion)
- International Chinese-language sources — BBC Chinese, Zaobao
- Social media signal layer (Weibo hot search + PTT trending)

### Backend + frontend

- FastAPI backend with filtering and full-text search (FTS5)
- React 19 dashboard with dark/light theme
- Priority signals section and review queue UI
- Sentiment trend visualisation + topic breakdown chart
- Event clustering (Jaccard similarity, 48-hour window)
- Analyst commentary and classification override
- Inline translation editing (headline, summary, key quote) with amber override indicator
- Editorial approval gate — all articles held from public feed until analyst sign-off
- Filter-scoped Strait Watch sentiment gauges (scope chip, ghost baseline dots, entity/topic/place/urgency filtering)
- Key Figures panel with manual curation workflow (attributed quotes/actions, analyst approval)
- Public read-only dashboard (`strait-signal.net`) — write controls hidden at build time
- Admin dashboard (`admin.strait-signal.net`) behind HTTP basic auth
- Domain name + SSL (Cloudflare proxy)
- Mobile-responsive layout with tab navigation
- Automated scheduling (cron every 6 hours)
- VPS deployment (Ionos S+, Ubuntu 24.04)

### Structured data tabs

- **Economy tab** — TW-vs-PRC trade with multi-reporter verification (MAC + UN Comtrade + HK CSD direct); the reporter gap is the analytical signal
- **Investment-by-industry** — both directions, with industry colour-coding and the ~50× outbound asymmetry visible
- **Trade Access tab** — BOFT bans + ECFA active/suspended + MoF PRC suspension waves + curated PRC bans, plus the monthly CIFER snapshot scraper (Playwright)
- **People tab** — bidirectional cross-strait residency: TW NIA permits + spouse stock + curated PRC-side data (台胞证 / census / settler floor) — with the 1992 籍貫 cutoff documented inline
- **PLA Incursion tracker** — Taiwan MND daily 共軍動態 scraper + PLATracker historical CSV backfill (2020-09 → 2026-04); KPI strip, daily bars, six-sector ADIZ heatmap, custom Taiwan Strait SVG map
- **Exercise Tracker** — Leaflet map + list of cross-strait exercises and drills, AI-extracted from MIL_EXERCISE articles, with analyst review queue, canonical-key auto-merge, and edit modal
- **Poll tracker** — Taiwan domestic pollster ingestion (My-Formosa, ETtoday, TVBS, NCCU long series); cross-pollster trend charts per canonical question_key

### Hardening & fixes (2026-07-04, multi-agent code review)

Full remediation from a multi-agent review; work order + per-item status in `CODE_REVIEW_2026-07-03.md`.

- **Access control** — admin-only reads gated server-side via a new non-raising `is_admin` dependency: `include_pending`, single-article + cluster visibility (with real 404s, not 200+error bodies), and `GET /api/stats/key-figures/candidates` no longer leak unapproved rows to anonymous callers. Tokens compared with `hmac.compare_digest`.
- **Entity canonicalisation** — bare `中國`/`台灣` were resolving to "Kuomintang (KMT)"/"TPP" via prefix-collision; added exact canonical entries and back-filled **2,749** existing rows (`renormalise_entities.py --apply`).
- **Pipeline resilience** — transient Gemini errors (429/5xx/timeout) now retry next run instead of tombstoning articles as processed; explicit JSON-null guards; `run_pipeline.py` isolates each step so one bad source can't abort AI analysis + clustering.
- **Data integrity** — `cluster_events` no longer tears apart clusters straddling the 48h window edge; `published_at` window filters use `strftime` `T`-format (a `datetime('now')` string mis-compare was over-including ~a day); weekly digest sends before archiving (no false "emailed" rows); MND KPI leap-day 500 fixed; `schema.sql` re-synced (`review_reason`/`reviewed_at`).
- **Scrapers** — RSS content no longer clobbered by an untrimmed generic selector; PTT pagination walks all pages; YDN/UDN timestamps stored UTC-correct (were 8h off); trade-access `banned`-list crash + propylene HS code (2901.22).
- **Prompt / cost** — officials roster trimmed to static-current + article-matched-former (~14.5k→3.1k chars/call); `poll_only`/`exercise_only` dropped to `thinking_level=low`; Tier-2 escalation review skips the extraction arrays; poll example labels made canonical.
- **Performance / hygiene** — `entities(article_id)` index; removed committed scratch files, a dead route, and 6 dead `api.js` exports.

### Cost & structure (2026-07-08, code-review work order continued)

- **Tier 1 via the Gemini Batch API** (~50% token price on the largest bill line) — collect-previous / submit-backlog / bounded same-tick wait per pipeline tick, `gemini_batch_jobs` state table, 150-article job chunking, interactive fallback + `GEMINI_TIER1_MODE` escape hatch
- **Scan markers for the poll/exercise side-passes** — zero-yield articles no longer re-scanned every tick (was 96%/70% repeat calls; ~95% of those stages' spend eliminated)
- **Versioned schema migrations** — `db/migrations/` + `scripts/migrate.py` + `schema_migrations` ledger replace the deploy-script heredoc; real migration errors now fail deploys loudly
- **Shared modules end copy-drift** — `shared/exercise_keys.py` (canonical keys, api+scraper), `scraper/utils/{dates,http,llm}.py`, `save_article()` (content cap standardised at 25K), prompt constants (`_DIPLOMACY_RULES`, `_NAMED_EXERCISES`), source behaviour flags on the `sources` table
- **Diplomacy corpus maintenance scripts** — `dedup_diplomacy.py` (embedding clustering on `gemini-embedding-001`) + `audit_diplomacy_offaxis.py` (two-pass detect/confirm), promoted from scratchpad one-offs
- Family-scoped poll-label canonicalisation (future race keys auto-inherit vote-intent semantics); MAC poll PDF shape assertions; notes API trimmed to the used POST (closing an ungated read of analyst commentary); loud startup banner when `ADMIN_TOKEN` is unset; 180-day age guard on guancha/fjsen

### Review work order closed (2026-07-10)

The three deferred structural items from `CODE_REVIEW_2026-07-03.md` — the work order is now fully applied.

- **§4.6 One entity-normalisation semantics** (`0d88ea1`) — `shared/entity_norm.py`: a single resolver (exact → explicit `title_tokens` strip → opt-in `fold_prefixes`) shared by the pipeline write path and `scripts/renormalise_entities.py`; `entity_canonical.json` restructured to `{canonical, title_tokens, fold_prefixes}`. The old bidirectional prefix match had done far more damage than the review's examples (`中華民國`→"ROC Armed Forces" ×336, `韓國`→"Han Kuo-yu" ×87, `福建`→the carrier ×165); staging repaired (6,311 rows), prod via `renormalise_entities.py --db <prod> --apply`. 11 tests.
- **§4.3 Unified review-queue state machine** (`549f55a`) — `api/review_queue.py`: `approve_row` / `dismiss_row` / `merge_row` primitives shared by the military, diplomacy, polls and key-figure queues (guards, `reviewed_at`/`reviewed_by` stamping, uniform responses). Migration `0004` adds `reviewed_by` + `merged_into_id` to `key_figure_statements`. Fixes en route: military `/merge` refuses dismissed/merged sources; kfs approve/dismiss 404 on a missing id. 7 tests.
- **§3.3 Lean Tier-2 escalation prompt** (`71eefef`) — `ANALYSIS_SYSTEM_PROMPT` split into shared blocks (Tier-1 reassembly verified byte-identical) + a dedicated `_ESCALATION_REVIEW_PROMPT` built from the same blocks, so Tier 1/2 sentiment rules are identical by construction. Review stays blind to Tier-1 answers. A/B on 55 escalation articles against an old-vs-old noise floor: indistinguishable band agreement, two small rule-consistent fail-safe shifts. Prompt −43% / output −62%.
- Also: NCCU 2026 June interim wave + `poll_results` constraint migration; poll scrapers can no longer poison `articles` with empty bodies; Somaliland statements no longer paint Somalia's polygon; **Positions & Legal Status page** schema + scaffold (admin-only).

### Ops hardening (2026-07-21)

- **Scraper staleness monitor** (`scripts/check_scraper_health.py`) — 48 per-source/per-table checks with tuned thresholds; emails on state change only (newly stale / recovered); daily cron 08:15
- Shared browser UA bumped Chrome/124 → 143 (UDN was 403-ing stale UAs)
- RSSHub chinatimes route patched in the container layer (upstream still broken — see `deployment.md`)

### Alt-model comparison experiment (2026-07-28 → 2026-08-16)

Do Chinese LLMs classify the same cross-strait articles differently from production Gemini? Everything side-tabled — never feeds editorial queues.

- **Article sweep** (`scripts/sweep_alt_models.py`) — approved articles re-run through DeepSeek/Kimi/etc. via OpenRouter with the byte-identical Tier-1 prompt; three arms (`neutral` Western-hosted / `originator` creator endpoint / `gemini-control`); every outcome recorded incl. refusals and parse errors; `--probe` routing check; 5-min busy_timeout to survive prod write locks
- **Analysis scripts** — `alt_model_aggregates.py` (agreement/sentiment deltas), `audit_terminology_markers.py` (spec-driven framing markers), `audit_summary_completeness.py` (omission-side check, §5.6) → `ALT_MODEL_EXPERIMENT_WRITEUP.md`, every number reproducible
- **Direct-question arm** (`scripts/sweep_direct_questions.py`, `data/direct_questions.json`) — prompt-shape test: literature-calibration / cross-strait-direct / scaffold-hybrid / control bands, matched en/zh, n=5 per cell; content-label taxonomy (migration `0007`); literature reference rates transcribed → `DIRECT_QUESTION_WRITEUP.md`
- **Admin UI** — per-article alt-model panel, Alt Models tab, Signal Feed model-lens toggle (lensed sidebar stats too)
- **Ops** — daily full-corpus V4F incremental sweep cron, `alt_model:v4f_sweep` staleness check, monthly review email (`alt_model_monthly_report.py`) with the frozen write-up table
- Fixes: K3 reasoning-token exhaustion misread as refusal; NOT_RELEVANT verdicts with empty summary; alt_models routes shared a sqlite connection across threadpool threads (rule: never `Depends()`-inject a connection)
- **Tier-1 sentiment rules tightened (v2)** — actions, mockery and securitisation count as framing
- 22 canonical entity corrections from the approved-corpus consistency audit

### Positions page, dedup, About (2026-08-12 → 2026-08-25)

- **Positions & Legal Status** — inline admin editing (co-writing without the chat round-trip); US entry (draft), Europe section (EU floor + six capitals), Russia card; concept readings carry `formulation_en` + romanisation; card-grid layout fixes
- **Same-outlet duplicate article detection** (`shared/article_dedup.py`, `scripts/dedup_articles.py`, pipeline Step 2m) — identical-content / trigram-Jaccard / same-day-title rules measured against the YDN daily PLA report; dupes hidden (`is_hidden=1`) before Tier-1 pays for them; cross-outlet duplication untouched (it's signal)
- About modal refresh + Positions concept scaffolds; OSINT Navigator CLI documented in `CLAUDE.md`

### Coast Guard tracker → Maritime tab (2026-08-25 → 2026-08-26, Phase 2e)

Coast-guard presence around Taiwan, framed as the AIS-visible *floor*, paired with the Taiwan-side enforcement mirror so the chart is bidirectional.

- **Data layer** — Global Fishing Watch 4Wings presence puller (Step 2n, nightly) → `coast_guard_presence` / `coast_guard_vessels` / `coast_guard_pulls`; official Kinmen control-point zones + Matsu bands, median-line band, 24 nm sectors, Pratas, east box (`scripts/build_coast_guard_zones.py`); four-flag roster (CCG/CGA/JCG/USCG) with recorded AIS identity anomalies; resumable monthly backfill from 2020
- **CGA enforcement mirror** (Step 2o) — 績效統計月報 / 年報 PDFs → `cga_enforcement`; yearbook backfill + transcribed 護永專案 table; every table citation links to its report PDF
- **Deterministic roster triage** — explicit force name or force-matching MID prefix confirms; classifier rejection purges; residual left `auto`; runs after every refresh/pull. The roster modal asks the analyst only the answerable question
- **Frontend** — Presence & Enforcement section (monthly strip, zone map, roster modal); data-audit fixes (yearbook year offset, CCG classifier flag gate, hull-number keying, empty-period guard, structured caveats)
- **Grouped navigation** (`frontend/src/navGroups.js`) — Feed · Security ▾ (Military, Maritime) · Economy ▾ (Indicators, Trade Access, People) · Politics ▾ (Polls, Diplomacy, Positions) · Admin ▾. Maritime un-gated 2026-08-27 once the prod 2020→ backfill completed
- **Editable site prose** — `data/site_copy.json` → `/api/copy` → `<Copy k=…>`; admin ✎ → `PATCH /api/copy/{key}`; all 42 tab prose blocks migrated; `JsonFileStore` (mtime cache + atomic write) shared with `positions.json`. Rule: Chinese on the page only when it is the source's own words — never translated chrome

### Maritime public + backlog (2026-08-27)

- Prod GFW presence backfill verified complete (880 pulls, 4h32m); three months lost to `database is locked` / a truncated GFW response re-pulled (`contiguous_s` 2020-02 + 2022-06, `contiguous_n` 2022-04)
- **Maritime tab un-gated for the public** (`88b0b5b`); Ed's inline Maritime/coast-guard intro prose committed from prod (`498446b`); deployed
- `CHANGELOG.md` regenerated after seven stale weeks; every-session update rule added here, in `CLAUDE.md` and in the session-log memory
- Prod article backlog cleared: 226 review-clean articles bulk-approved (manifest `bulk-approve-prod-20260827.manifest`); 1 review-flagged YDN editorial held for Ed
- Guancha scraper: the Taiwan section went dormant site-side on 08-10; now also scans 国际/军事/国内 with a title-keyword gate
- `scripts/bulk_approve_articles.py` — the feed-backlog clear as a real script (dry-run, consistency checks, attention report, manifest); replaces five ad-hoc runs
- **Reported-speech sentiment axis fix** — a TW outlet quoting a TAO/MND/MFA attack was scored on the PRC's framing of Taiwan (18% of TW-source scores ≤ −0.6 over 90 days), double-counting the statement and flattening the per-side divergence. Prompt: REPORTED SPEECH rule, checklist step (0) on source side, reasoning-subject constraint, worked examples (Tier 1 + Tier 2 by construction). Validator: `_reported_speech_problem()` routes the residual to review (subject-anchored regex; actions and passive outlet framing excluded). A/B vs an old-vs-old noise floor: no control collateral, prompt alone fixes ~half. Prod history re-scored with a manifest: 59 of 170 flagged rows → neutral, mean −0.63 → −0.37; 35 residual hits in the 90-day corpus

### Cross-strait visits tracker + Maritime 2017 extension (2026-08-30, staging)

- **Cross-strait visits tracker (Phase 2f)** — Politics ▾ **Visits**. New `cross_strait_visits` table (migration 0010) fed by a topic-gated pipeline pass (**Step 3e**, `scraper/processors/visits_extract.py`) over analysed `DIP_VISIT` / `PARTY_VISIT` articles — deliberately NOT in the unconditional Tier-1 prompt. Scope is cross-strait only (Ed's call): Taiwan↔third-country travel stays on the Diplomacy axis, and the rule is enforced in code (side derived from the affiliation enum, contradictory rows dropped) as well as in the prompt. Keeps planned / rumoured / cancelled / **blocked** visits as labelled rows. `/api/visits/*` (list / summary / monthly + admin queue with a same-direction ±21-day merge picker), `VisitsTab.jsx` (KPIs, monthly bars by direction, frequent travellers, month-grouped timeline, admin edit/dismiss), `scripts/backfill_cross_strait_visits.py`, `tests/test_visits_extract.py` (scope gate + API-enum mirror). Staging backfill (400 days) running; first dry-run: 8 articles → 3 rows, third-country visits correctly empty.
- **Maritime 2017 extension** — `backfill_coast_guard.py --start 2017-01-01` launched detached on prod then staging (~400 new windows; also retries the four errored 2020–22 windows). Chart floor is now data-derived (`summary.coverage_start`) instead of a hardcoded 2020-01. Pre-2020 caveats (coverage step, USCG count) to be re-audited when the run lands.
- Changelog planned list pruned: alt-model write-up done; Positions still under Ed's review.

### Alt-model originator arm + Substack draft (2026-08-28, staging `4240814`/`1916bc3`, not yet on main)

- **Originator arm unblocked**: the 07-2x 404 was an OpenRouter account *guardrail* (provider allowlist), not the privacy toggle — it also hides DeepSeek from the model's endpoint listing. Cleared by Ed; `--probe` routes via DeepSeek.
- **Direct-question battery on DeepSeek's own endpoint** (150 calls, $0.06): PRC host refuses 21/25 Chinese calibration questions (Tiananmen/Xinjiang/Xi/Falun Gong 5/5 each) vs 10/25 Western-hosted; spreads to the ROC-status question (3/5 zh) and once to a neutral control (D-01 zh). Taiwan-status never refused on either host — state line verbatim. English 8/25 (Xi 0/5, answered with the recital). **Band C (Tier-1 scaffold): 20/20 answered** — the scaffold holds on the PRC host; two C-01 runs scored a TW 統獨 column +0.4 where every Western run said −0.6 (hand-review verdict: dropped — coherent alternative reading of a blue column). Originator hand review complete: 33 refused / 2 caveat / 1 answered; 10% FN sample clean.
- **Three confounds recorded in `RUN_NOTES.md`**: DeepSeek serves revision `-0731` (Western hosts `-20260423`), in thinking mode (Band C needed 24k tokens), with different refusal templates. The comparison is host × mode × revision.
- Classifier fix: DeepSeek app template 「我还没有学会回答」 added to both refusal regexes (25 rows reclassified in place, manifest kept; neutral rows 0/390 changed). `ARM_MAX_TOKENS` per (model, arm) + arm-aware probe headroom. 2 tests added (44 pass).
- Substack draft rewritten corpus-first (`SUBSTACK_DRAFT_refusal_v2.md`, untracked) with every corpus number re-run live (15,418 V4F rows).
- **Write-up numbers refreshed to the full corpus** (evening session): every V4F cell in `ALT_MODEL_EXPERIMENT_WRITEUP.md` (untracked) re-derived from the 15,418-row sweep (was the 3,936 frozen on 08-02) — agreement 40.3%/58.8% conditional, NR 31.5% (sovereignty 6.1% vs 36.7%), sensitive-slice omission 2.9% (166/5,638), extraction recall 75.8% (down from 87.2% on the subset; not sensitivity-selective). `scripts/alt_model_monthly_report.py`'s frozen reference block and the Alt Models tab findings text updated to match. Substack draft fact-check: three errors caught — the control's sensitive-slice figure is 8.8% (8/91: Xi ×4, Lai ×3, Tsai ×1), not 9.1% (that is V4F's *reverse* cell); 台獨-mention count is 2,517 not 2,498; the "Taiwan authorities + so-called" rate is 9%/3% (PRC/TW) with both markers, 6%/2% with the first alone.

### Maritime re-audit + two-force display, no-editorialising pass, Visits dedup + map (2026-08-31, staging)

- **Maritime pre-2020 caveat re-audit** — the 2017 backfill landed on both DBs overnight (coverage now 2017-01 → present, 1,276 windows prod). 2017–19 Kinmen/Matsu CCG presence verified real (19/20 hulls roster-confirmed Haijian/Haijing identities, multi-year spans). `uscg_absent` corrected ("since 2020" → 2 hull-days ever, one cutter June 2023); `ccg_pre_2023` remeasured on the full series (~8× step-up, 107 → 822 hull-days, window extended back to the 2017 series start, plus a coverage-growth note for every force); About-modal coverage date fixed.
- **No-editorialising pass over site prose** (Ed's rule, saved to memory): the Kinmen "Read the gap as go-dark behaviour, not de-escalation" sentence deleted; four verdict lines cut (USCG "Not a signal", CGA "only … carry meaning", JCG "not Taiwan-related activity", People "the asymmetric recovery is the analytical story"); six softer lines neutrally rewritten (maritime.intro causal clause, Diplomacy "honest national posture", Visits "a signal in its own right", People "suggests recovery is underway", Investment "suggesting …" / "the story this chart tells"). Applied to prod's live `site_copy.json` too — prod tree dirty by exactly the committed content until the next deploy.
- **Maritime display is now two-force, CCG vs CGA** (Ed's call: JCG/USCG are noise for a cross-strait instrument) — JCG (≥93% Senkaku/Yonaguni east-box overspill every year 2017→) and USCG (2 hull-days ever) removed from every chart and public aggregate (`DISPLAY_FORCES` in the API + `CHART_FORCES`); both still collected and roster-classified, `?force=JCG` still returns the hidden series; `jcg_east_only`/`uscg_absent` caveats deleted; co-presence strictly CCG × CGA; intro/co-presence/About copy now two-force.
- **Visits pre-queue dedup** (`shared/visit_dedup.py`, `scripts/dedup_visits.py`, pipeline step straight after 3e) — one article per outlet per day of one trip flooded the queue: 495 of 522 staging backfill rows were a single Cheng Li-wun trip (both script variants). Clusters by direction + visitor (figure_id, else romanised name, else zh) with effective dates chained ≤21 days; richest keeper (approved rows anchor; cancelled/blocked/reported outrank planned/rumoured; location deliberately NOT a key). Staging apply: **520 pending → 16**; revert manifest kept. 7 unit tests (182 green).
- **Visits map** (`VisitsMap.jsx`) — per-(place, direction) markers sized by visit count, resolved through an in-file gazetteer over the extraction prompt's English `location_label`; unresolvable labels ("Mainland China") stay timeline-only. Shares the timeline's filter pills; `DIR_COLOUR` moved to `VisitsReviewQueue.jsx` beside the other shared visit constants.

### China Times Cloudflare outage fixed (2026-08-31 evening, ops — container only, no repo change)

- CT Politics / Military / Opinion went dark 2026-08-26 ~12:00 UTC (health cron had them `STALE`): chinatimes.com enabled a Cloudflare JS challenge (`cf-mitigated: challenge`, 403) on a subset of section list pages (politic/armament/opinion/star; chinese/money/realtimenews exempt). Not the July container patch — that was intact.
- Fix: third minified edit to the RSSHub container's `chinatimes-CoSBu9wp.mjs` — category fetches now use the unchallenged 總覽 pagination endpoint (`/{category}/total?page=1&chdtv`), conditional so the default `realtimenews` route keeps its original URL (no `/total` there). Article pages were never challenged. All four CT feeds + realtimenews verified live; feed titles now "總覽 -政治" etc. Details in memory `rsshub_chinatimes_patch.md` — the patch lives in the container writable layer and dies on image re-pull.

### Maritime long view — annual CGA enforcement vs CCG presence (2026-08-31 evening, staging)

- New "The long view · annual" section on the Maritime tab, between the paired monthly strips and the dual-frame cards: two synced annual strips — CGA PRC-vessel expulsions per year (表8-1, constant methodology 2011→, spans the 2016 change of administration) and AIS-visible CCG hull-days per year, all zones (2017→). Full calendar years only (no asymmetric partial-year bars — the monthly strips above carry the recent period); pre-2017 CCG renders null, never zero (no coverage ≠ no activity); annual rows dedupe yearbook-first; the `ccg_pre_2023` caveat always renders with it.
- `MonthlyStrip` generalised with `xKey`/`fmt` props (default unchanged) rather than a parallel annual component. Data is client-side aggregation of the existing `/monthly` (months=200, all zones) + `/enforcement` `annual` payloads — no API change.
- Two new copy keys (`coast_guard.longview`, `coast_guard.longview_aircraft` — the queued pre-2020 aircraft measurement-problem note, pointing at MND's Sept-2020 series start). Prod's admin-edited `site_copy.json` synced over staging first, per the content-change rule.
- **DEPLOYED to prod 2026-08-31 same evening** (with the yearbook-editions source line, Ed's catch: each 表8-1 prints ~12 years, 2011/2012 bars come from the 112年/113年 editions — now all contributing editions are cited under the strip): FF main → `9a6d323`, pushed, `server_deploy.sh` clean, prod verified (copy keys served, long view rendering on the live site).

### Server security hardening (2026-08-31 evening, ops — server only, no repo change)

- Cloudflare Security Center triage: HSTS enabled by Ed at the CF edge (all four hostnames now send `strict-transport-security`); `security.txt` now really served (the SPA catch-all had been returning index.html at that path) via an exact-match nginx location → `/var/www/security-txt/security.txt`, contacts = public GitHub repo + Substack, Expires 2027-08-31; "dangling A record" insights assessed false-positive (all four records proxied, origin correct); the analytics `/script.js` Access policy is the deliberate Umami tracker bypass.
- **ufw enabled** (was inactive — origin answered 80/443 to the whole internet, bypassing CF): SSH open, 80/443 allowlisted to Cloudflare's 20 published v4+v6 ranges. If CF adds ranges and a host 522s, re-fetch cloudflare.com/ips and add the rule. Also same evening: Umami admin password reset (bcrypt UPDATE in the umami-db-1 postgres; username showmeasignal).


### 2026-09-01 — "Morning Brief" frontend redesign (phase 1)

Full visual restyle from Ed's Claude Design handoff (`/root/redesign/design_handoff_morning_brief/`): warm-paper token system (light + dark) with Newsreader / Public Sans / Archivo, centred masthead with double-rule stats ticker, the Feed as a twin-rail brief (alignment legend, hairline gauges, dotted-leader topics, Voices, Top of the Brief), section pages as single-column reading documents. Sentiment keeps the locked purple-hostile / amber-cooperative split (±0.3); TPP keeps cyan; 8-value alignment colour system with the filled/hollow marker rule (`BIAS_META`). Post-review refinements the same day: presidential-approval hero on Polls (trailing-60-day per-pollster composite beside the cross-pollster trend; NCCU flagships half-width with latest-wave value legends), page renamed Taiwan Polling, Visits timeline rebuilt with labelled fields + portraits/initials medallions, About converted from modal to a full page (same site_copy keys). Every deployed feature survived the restyle (maps, Maritime paired charts, admin queues). Cloud ultrareview findings all fixed (CoastGuardMap NaN fills, hex-alpha concat, bandColour consolidation into `sentimentBand.js`, legacy rgba→color-mix sweep, dead CSS removal). Phase 2 remaining: per-tab document headers, KPI hairline grids, admin surface restyles.

### 2026-09-01 — Visit portraits: auto-pull script + paired avatars (staging)

`scripts/fetch_visit_portraits.py`: resolves named visit participants against Wikidata (exact zh-label/alias match, human + political-actor gate, zh-Wikipedia lead-image fallback when P18 is missing) and downloads free-licensed Commons portraits into `frontend/public/figures/visits/` + `manifest.json` (names incl. simplified/traditional variants, attribution, licence — review the diff, then commit, like `refresh_officials.py`). Ambiguous names (王宁: six candidate officials) are never auto-picked — rerun with `--accept "名字=Qxxxx"`; unresolved people get a Baidu Baike lead URL for manual sourcing (Baike images are unlicensed, so never auto-pulled). First staging run: 5 portraits (Chiang Wan-an, Hsiao Tsu-tsen, Hung Hsiu-chu, Ma Ying-jeou, Wang Huning). **2026-09-02 follow-up**: Wang Ning pinned to the Yunnan party secretary (`--accept "王宁=Q24833108"`); prod-DB run added Andrew Hsia, Chang Jung-kung (zh-wiki lead image via `--accept`), Chen Yu-chen, Hung Sun-han, Liao Hsien-hsiang, Rao Ching-ling, Zhang Zhijun (two wide shots head-cropped by hand); new **official party-site tier** (`PARTY_SITES` — the KMT officer grids on www1.kmt.org.tw, exact zh-name match; not free-licensed, credited as the party's own press portrait — Ed's call) picked up Lien Sheng-wu, plus a `--manual "名字=URL"` escape hatch. Ed then supplied the TAO 机构设置 page (gwytb.gov.cn/jgsz/, gb2312) — second `PARTY_SITES` entry; a matched-but-imageless Wikidata item now lends its label forms to the site lookup, so traditional 彭慶恩 finds simplified 彭庆恩 → Peng Qing'en and Wu Xi (TAO deputy directors) added; the KMT 中常委 grid also yielded Cheng Jen-tsung. 賴軍 came in through `--manual` from a Baike URL Ed supplied (credited "Photo: Baidu Baike", licence string marks it analyst-supplied; the bare CDN URL avoids the watermark). Manifest 18 entries — every named person on prod's approved visits now has a portrait; still unsourced on staging: 魯霞光 / 陸獻德 / 蔡孟君 / 趙世通. **Precision fix** found while checking that last name: the English-label path had matched 趙世通 to Q18914182, who is 赵世同 — a different official with the same romanisation (harmless only because that item had no photo). An English hit on a row that also carries a Chinese name must now be corroborated by that name's presence among the item's zh labels; otherwise it is rejected and the report says why. VisitsTab timeline cards now show TWO stacked avatars — visitor on top, counterpart below, matching the "X met Y" headline order — each resolving curated key-figure portrait → visit manifest by name → initials medallion; the counterpart's photo no longer stands in for the visitor's.

### 2026-09-02 — Click affordances: three verbs, three cues (deployed to prod same day)

Ed: "it isn't entirely clear which items you can click to expand." Inventory found three kinds of clickable thing and only the inline Social Pulse header signalling itself. Now each verb has a typographic cue, hover changing colour or border only (the design rule): **expands in place** — article cards carry a `detail ▾` / `less ▴` micro-caps marker at the right end of the metadata line, the left rule turns hairline on hover, and the card is a keyboard-operable `role="button"` with `aria-expanded`; **opens elsewhere** — Diplomacy country rows show a `→` on hover (matching the Spotlight's "More →"); **filters the feed** — sidebar gauges, source rows, entity rows and the topic leaders underline on hover, with the existing "Filter by …" title. Classes (`.expandable` / `.expand-cue` / `.nav-row` / `.nav-arrow` / `.filter-row`) live in `index.css`; rule documented in `frontend.md`. Verified on 8082 by Playwright (cue text flips, `aria-expanded` toggles via Enter, arrow appears on row hover).

### 2026-09-02 — Redesign phase 2, step A: document headers + hairline stat bands (staging)

New `components/documentChrome.jsx`. Every section page (Military, Maritime, Indicators, Trade Access, People, Polls, Diplomacy, Visits, Positions) now opens with the design's document header — eyebrow `Group · View`, Newsreader 34px title, the page intro as a standfirst, data-vintage meta right, admin actions above it — replacing the rule-label-as-page-title pattern. Titles are new editable copy keys (`<view>.title`) and carry the plain section headings the pages already had ("PLA Activity Around Taiwan", "Taiwan Polling", …) — the handoff's editorial titles ("Tariff concessions as leverage", "Grey-zone at sea") were tried and rejected by Ed as editorialised; change a title from the admin pencil, not in code. KPI card strips on six pages became one hairline `StatGrid` (1px gap on a `--hair` ground, figures Newsreader 28px, accents on the figure not a border), deleting five per-file `KPICard` copies. Verified on 8082 across all nine pages by Playwright. Remaining phase 2: AltModelLens / review-queue / modal restyles, entity alignment colouring in the rail, `role`/`role_zh` per key figure, Trade Access stat band.

### 2026-09-02 — Masthead: the two sides of the strait flank the nameplate (deployed to prod 2026-09-03)

Ed's idea: "either side of Cross-Strait Signal there were the sides of the strait." New `MastheadCoasts.jsx` draws the mainland coast with Kinmen, Wuqiu and the Matsu groups to the west of the nameplate and Taiwan with Penghu, Lanyu and Green Island to the east, so the title sits in the strait. Geometry comes from a new `--masthead` mode of the strait-map builder (wider Natural Earth box, so the coast runs from Ningde down past Xiamen and Shantou to the Pearl River mouth — Ed's "more thorough build-out to the south"), split along the Median Line and drawn on one shared latitude scale (Fujian correctly rides north of Taiwan's bulk); paths are re-simplified at load for masthead scale and sub-pixel island groups get fixed dots. Token colours, so light and dark need nothing extra. After Ed's first look the flanks moved out to 300px from the centre line and are pinned to span exactly the eyebrow line down to the nav row (never above "BILINGUAL · …"); hidden below 1100px. Phase 2A (document headers + stat bands, plain titles) deployed to prod earlier the same day. **Round 3 (2026-09-03):** Ed's verdict on the shared-scale version was "not instantly recognisable as China's coast" — a Fujian coast segment is not an icon at any smoothing. Rebuilt as two emblems at their own scales: west, China's whole eastern seaboard from the Shandong peninsula past the Yangtze mouth, Fujian and the Pearl River to Leizhou and Hainan, as filled land fading inland (so no box cut shows) with the coast as the crisp edge; east, Taiwan with the Penghu group, Green Island and Lanyu, filled. Own builder `scripts/build_masthead_emblems.py` → `mastheadEmblems.js` (box-clipped fill + open coast runs; the Waisanding sandbar dropped by box because it read as a spike); the `--masthead` mode was removed from the Military-map builder, which is back to its main-branch state. **Flag wash (same day, Ed: "excellent, that looks good"):** each side's flag over its silhouette as a soft wash, not a hard fill — the PRC star group over the Jiangsu coast; Taiwan the flag-map way, north blue carrying the whole sun, south red, soft blend between — fading from the north-west corner to the south-east so the emblems stay paper underneath. Flag geometry is the flags' own (Commons public-domain SVGs).

## In progress / planned

- **Maritime tab**: militia/dredger layer, go-dark events
- **Cross-strait visits tracker**: DEPLOYED to prod 2026-08-31 (migration 0010; detached prod backfill + auto-dedup launched → `/var/log/visits-backfill-prod.log`); next = analyst pass over the deduped prod queue; later: link visits to feed clusters so both sides' coverage of one trip sits together
- **AidData / Lowy finance layer** on the Diplomacy map — recognition-switch finance, not a China-vs-Taiwan totals chart
- Positions page: US entry pending Ed's editorial review; concept scaffolds have no public definitions until then
- Maps for geocoded entities (entity table already carries lat/lng schema fields)
- Incursion × exercise cross-reference — apply the verification angle to military data (do PLA spikes track MIL_EXERCISE / MIL_MOVEMENT article volume?)
- Monthly-aggregated sentiment endpoint (revisit when 12+ months of data exists)
- Audit trail for AI classifications — `topic_primary_ai_original` column or change log to unlock per-category accuracy measurement
- Override-propagation race fix — optimistic concurrency control on the notes/review write paths, or frontend dirty-tracking on the override dropdowns
- ADS-B / AIS data integration (Phase 3) — coast-guard AIS now covered; aircraft still open
