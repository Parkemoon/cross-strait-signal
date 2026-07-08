# Full-code review — 2026-07-03 — suggested changes (work order)

Multi-agent review of production (`main`, was @ 3b9ba01): 11 finder angles + adversarial
verification of every candidate. ~40 findings confirmed. Items in **§0 are already
applied and committed** — do not redo them. Everything else is TODO, ordered by
priority. Each item is independent unless noted. After backend changes run
`./venv/bin/python -m pytest tests/ -q`; after frontend changes run
`cd frontend && npm run build` (admin) and `npm run build:public`.

Per CLAUDE.md: bug fixes may go on `main`; items tagged **[STAGING-FIRST]** are
structural and belong on the `staging` worktree first. Schema changes go in a new
numbered `db/migrations/` file AND `db/schema.sql` (the old server_deploy.sh
heredoc dual-maintenance was retired by §4.2 on 2026-07-08).

---

## Implementation status (applied 2026-07-04)

**DEPLOYED 2026-07-08 (evening):** all three 2026-07-08 batches below were
merged to `main` (`e7d7f63`) and deployed — the migration runner's first
prod run applied 0001+0002 cleanly, `seed_sources.py` set the new source
flags, and prod Tier 1 runs batch-mode from the 18:00 tick. Remaining
open items: §3.3 remainder, §4.3, §4.6.

**Applied in this commit:** §0 (security/visibility); all of §1.1–1.12; all of
§2.1–2.9; §3.2, §3.3 (safe subset — see below), §3.4, §3.6, §3.7b; §4.1 (index in
schema.sql + deploy migration block, plus a `.timeout` on the deploy heredoc); and
the §5 items — removed `mfa_debug.html`/`python`/root `cross_strait.db`/`.pytest_cache`,
dropped the dead `/api/economy/series/meta` route and 6 dead `api.js` exports,
flattened the `App.js` tab chain, and added a min-count guard to `refresh_officials.py`.
`pytest` 42/42 green; public frontend bundle compiles.

**Partial / deviations:**
- **§3.3** applied conservatively: the Tier-2 escalation review keeps the shared
  `ANALYSIS_SYSTEM_PROMPT` scoring rules (so Tier-1/Tier-2 still judge sentiment
  identically — no drift risk to production output) but now (a) injects the small
  CURRENT roster + article-matched FORMER officials instead of the full 14.5k-char
  block, and (b) appends a REVIEW-MODE directive telling the model to skip the
  extraction arrays (cuts most output tokens). A full standalone lean prompt is
  **not** done — it would change analytical output and needs a staging A/B.

**Deferred (need production DDL/DML or a staging-first structural change):**
- **§3.1** (poll/exercise `scanned_at` marker columns) — new columns + backfill;
  the single biggest cost win but requires a schema change + live-DB migration.
- **§1.2 back-fill, §3.6 back-fill** — the code/JSON fixes are in, but repairing
  the already-written rows needs DML on the prod DB: run
  `scripts/renormalise_entities.py --apply` (fixes 中國/台灣 history) and
  `scripts/canonicalise_poll_labels.py --apply` (folds any 未決定 rows).
- **§4.1 index creation on the live DB** — added to schema + deploy block; the
  actual `CREATE INDEX` runs on next `./deploy.sh` (not executed here).
- **§3.5** (Batch API), **§3.7a** (diplomacy-rule dedup — touches Tier-1 prompt),
  **§4.2/4.3/4.6/4.7/4.8/4.9** (migration framework, review-queue unification,
  shared modules), **§4.10** (auth fail-closed), and the `.env` SMTP-dup / notes
  PUT-DELETE / mac_poll shape-assert notes — all left as-is; see their sections.

**Deploy note (unchanged):** the admin bundle must be rebuilt with
`REACT_APP_ADMIN_TOKEN` set, or the admin feed loses pending articles and the
curate queue 401s (the new §0 gates enforce the token server-side).

**Applied 2026-07-08 (staging), third batch:** **§4.2** — versioned
migrations: `db/migrations/` ordered files (`0001_baseline.sql` = frozen
heredoc content incl. the run-once data fixes; `0002_….py` = the tolerant
ALTERs) applied by `scripts/migrate.py` into a `schema_migrations` ledger;
`server_deploy.sh`'s heredoc + `|| true` ALTERs replaced by the runner
(real errors now fail the deploy; cron locks wait on the 30s busy_timeout);
`init_db.py` records history after `schema.sql`. **§4.9** — shared
`scraper/utils/{dates,http,llm}.py` + `save_article()`/`get_connection(db_path)`
in `db.py`; ROC-year (6 sites), URL-date (3), browser headers/client
(~13 scrapers), article INSERT (13 scrapers, truncation standardised at
25K = MAX_PROMPT_CONTENT_CHARS), Gemini client bootstrap (5 sites) and
LLM JSON parsing (6 sites) all consolidated; bare-connection scripts
(cluster_events, rebuild_fts, seed_sources, weekly_digest, init_db)
routed through `get_connection`.

**Applied 2026-07-08 (staging), second batch:** **§3.7a** (shared
`_DIPLOMACY_RULES` + `_NAMED_EXERCISES` constants; the exercise-only prompt
had drifted, not the backfill); **§4.5** (Tier-1 loop calls
`_insert_exercise_row`); **§4.7** (`sources.is_pollster_direct` /
`exercise_only_scan` columns, seed-driven); **§4.8** (family scoping in
`canonicalise_poll_labels` + the no-response→undecided repair mapping);
**§4.10** (loud startup banner when `ADMIN_TOKEN` unset — warn, not
fail-closed); **§4.4** (`shared/exercise_keys.py` — one canonical-key
implementation for api/ + scraper/ + backfill); **§5** stragglers (notes.py
trimmed to the used POST, mac_poll shape assertions with per-question skip,
.env SMTP dedup applied); **§3.5** (Tier 1 through the Gemini Batch API by
default — `run_tier1` collect→submit→bounded-wait flow, `gemini_batch_jobs`
table, interactive fallback on submission error, `GEMINI_TIER1_MODE` escape
hatch; verified end-to-end on staging with a real 4-article job). Also from
the session-log backlog: `scripts/dedup_diplomacy.py` +
`scripts/audit_diplomacy_offaxis.py` promote the scratchpad dedup/off-axis
passes to maintenance scripts (on `gemini-embedding-001` — the old
`text-embedding-004` is retired), and `usage_report.py` PRICES verified
against Google's 2026-07 sheet incl. `@batch` variants.

**Applied 2026-07-08 (staging):** **§3.1** — `poll_scanned_at` /
`exercise_scanned_at` marker columns on `articles` (schema.sql + idempotent
ALTERs in the `server_deploy.sh` migration block), stamped after every Step
3b/3c scan including zero-yield; selection adds `IS NULL` on the marker.
Transient API errors (`_is_transient_error`) skip the stamp (retry next tick);
parse failures stamp it (no infinite retry). No backfill needed — NULL markers
on backlog rows mean each gets scanned at most once more, then drops out. The
two selection queries' `datetime('now', ?)` comparisons were also switched to
the T-format `strftime` convention (same class as the §0 stats.py fix). Bundled
in the same commit: the 180-day age guard for `guancha_scraper.py` /
`fjsen_scraper.py` (flagged in the 2026-07-01 session log, not a review
finding).

---

## §0 — Already applied (this commit) — do NOT redo

- `api/auth.py`: added `is_admin()` dependency (non-raising admin check for GETs with an
  admin superset); both comparisons now use `hmac.compare_digest`.
- `api/routes/articles.py`: `include_pending` now requires a valid `X-Admin-Token`;
  `GET /{id}` and `GET /{id}/cluster` apply the strict public-visibility predicate for
  non-admin callers; `GET /{id}` 404s properly (was 200 + `{"error": ...}`);
  `content_original` removed from the list SELECT (dead payload, zero frontend refs).
- `api/routes/stats.py`: `GET /key-figures/candidates` is now admin-gated; all 16
  date-window comparisons changed from `datetime('now', ?)` (space format — lexically
  broken vs stored `T`-format ISO, measured 5.5% over-inclusion) to
  `strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)`; escalation N+1 entities query batched into
  one `IN (...)`; `content_original` removed from the escalation SELECT.
- `frontend/src/api.js`: `fetchArticles` / `fetchArticle` / `fetchArticleCluster` /
  `fetchKeyFigureCandidates` now send `authHeaders()` (needed by the new gates; no-op in
  the public build).
- `frontend/src/components/KeyFigures.jsx`: candidates fetch skipped when `READ_ONLY`.

`pytest`: 42 passed. **Deploy note:** the admin bundle must be rebuilt with
`REACT_APP_ADMIN_TOKEN` set, or the admin feed loses pending articles and the curate
queue 401s. Public bundle unaffected.

---

## §1 — Critical pipeline correctness (P0)

**1.1 Transient Gemini errors permanently tombstone articles** — `scraper/processors/ai_pipeline.py:1227-1234`.
The blanket `except Exception` marks `ai_processed = 1` for ANY failure (429, 5xx,
timeout, truncated JSON). Selection is `WHERE ai_processed = 0`; nothing ever resets it;
there is no retry anywhere (`tenacity` is in requirements.txt but imported nowhere).
A one-hour Gemini outage silently and permanently loses every article in that batch.
Fix: catch transient API errors separately (`google.genai.errors.APIError` with
`code == 429 or code >= 500`, plus `httpx` timeout/transport errors) and leave those
articles at `ai_processed = 0` (they retry next 6h tick); tombstone only genuine
parse/validation failures. Consider a `scripts/` one-off to reset `ai_processed = 1`
rows that have no `ai_analysis` row (the existing casualties — they are identifiable).

**1.2 Entity canonicalisation corrupts 中國 and 台灣** — `ai_pipeline.py:318,327` +
`scraper/processors/entity_canonical.json`.
No exact entry exists for 中國/中国/台灣/臺灣 (all 234 keys checked), so the tier-3
bidirectional prefix loop rewrites bare 中國 → first key starting with it, 中國國民黨 →
**"Kuomintang (KMT)"**, and 台灣 → 台灣民眾黨 → **"Taiwan People's Party (TPP)"** — the
corpus's two most common entities mislabelled as political parties.
Fix (two parts): (a) add exact entries `"中國": "China"`, `"中国": "China"`,
`"台灣": "Taiwan"`, `"臺灣": "Taiwan"` to entity_canonical.json (exact tier wins, blocks
the prefix tier); (b) run `scripts/renormalise_entities.py --apply` (exact-match only —
safe) to repair existing rows. Longer-term see §4.6.

**1.3 Explicit JSON nulls crash extraction after commit** — `ai_pipeline.py:972,974,344,1108`.
No `response_schema` is set anywhere (JSON mode only), so the model can emit
`"speaker": null` → `stmt.get('speaker', '').strip()` raises AttributeError (`.get`
default doesn't cover present-but-null), aborting all remaining inserts for the article
and landing in the 1.1 tombstone. Same class: `"sentiment_score": null` →
`None > -0.3` TypeError in `_validate_sentiment` (line 344, called at 1108 — six lines
AFTER `conn.commit()`), skipping review-flagging and Tier-2.
Fix: use the `(stmt.get('speaker') or '').strip()` idiom (already used at line 289 in
the diplomacy loop) at 972/974; guard `_validate_sentiment` input
(`score = 0.0 if score is None else score`); ideally add a `response_schema` to the
generation config so types are enforced upstream.

**1.4 rss_scraper stores untrimmed page furniture** — `scraper/scrapers/rss_scraper.py:94-101`.
A leftover generic-selector block (`div.archives` / `article` / `div.article-content` /
`div.content`) unconditionally overwrites the source-specific content extracted and
furniture-trimmed just above it; `<article>` matches virtually every news page, so the
trimming loop (lines 89-92) is dead code and sidebar/related-news junk is stored and fed
into every Gemini prompt. Fix: only run the generic block when the source-specific pass
found nothing (`if content_div is None:` — check indentation/flow when editing).

**1.5 PTT pagination never advances** — `scraper/scrapers/ptt_scraper.py:116-121`.
`prev_url` (the 上頁 link) is extracted only `if page_num == 0:`, so iterations 2..N
re-fetch the same second page; for Gossiping (15 configured pages) ~87% of the intended
24h window is never scanned, masked by dedup and a page count that lies. Fix: extract
the 上頁 link on EVERY iteration (move the block out of the `page_num == 0` guard).

**1.6 YDN/UDN timestamps are wrong by 8 hours** — `scraper/scrapers/ydn_scraper.py:20`,
`scraper/scrapers/udn_scraper.py:80`.
YDN parses Taipei-local times then stamps `tzinfo=timezone.utc` (published_at up to 8h
in the FUTURE — live rows show published_at > scraped_at); UDN stores naive local
strings with no offset. Both corrupt cross-source ordering and every windowed query.
Fix in both: parse as Asia/Taipei and convert:
`datetime.strptime(...).replace(tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc).isoformat()`
(Taiwan has no DST, fixed +8 is safe; matches ltn_defence_scraper.py:21-22's pattern).
Optional one-off: correct existing YDN (`-8h`) and UDN (naive → assume +8, convert) rows.

**1.7 trade_access: one fetch failure kills both TW datasets + wrong tariff line** —
`scraper/scrapers/trade_access_scraper.py:291-315` and `:58`.
(a) `banned` is assigned only inside step 1's try; the failure path never sets it, so
step 2's comprehension raises UnboundLocalError, caught and misreported as a
conditional-fetch failure. Fix: initialise `banned = []` before the try. Also hoist
`{b['hs_code'] for b in banned}` out of the comprehension (rebuilt per item, O(n²)).
(b) Wave-1 ECFA list codes 丙烯/Propylene as `29012100` — that is ethylene; propene is
`2901.22`. Fix the tuple to `('29012200', '丙烯', 'Propylene')` and check the live
`trade_access` table for a stale `29012100` row marked `ecfa_suspended` (manual
correction or one-off UPDATE).

**1.8 run_pipeline has no per-scraper fault isolation** — `scripts/run_pipeline.py` (Steps 1-2, ~lines 40-90).
Only the Step-3d subprocess is wrapped; any scraper raising (e.g. `raise_for_status()`
in mac_economic's catalog fetch on a transient 503) aborts the entire 6-hourly run
BEFORE AI analysis and clustering, silently (cron → log file only). Fix: a small helper
`def _step(name, fn, *a):` wrapping each call in try/except that logs and continues;
keep a failure count and exit non-zero at the end if any step failed (so the log shows
it) while still running all steps.

**1.9 cluster_events tears apart window-edge clusters** — `scripts/cluster_events.py:102,120,157`.
Every run regenerates cluster UUIDs for all in-window (48h) articles and NULLs
in-window singletons; the existing `event_cluster_id` is fetched but never read. An
article whose cluster partners aged out of the window is stripped of its cluster while
the aged-out partner keeps a stale id and `cluster_size=2` — stories vanish from
cluster views and the weekly digest. Fix (choose depth): minimally, when a within-window
article is a singleton but already HAS an `event_cluster_id` shared with out-of-window
rows, leave it untouched; better, select clusters by cluster-min-date rather than
per-article date, and reuse existing cluster ids for unchanged groupings.
Also fix the same lexical-datetime bug fixed in stats.py: `cluster_events.py:105` and
`scripts/merge_entities.py:50` compare `published_at >= datetime('now', ?)` — change to
`strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)`.

**1.10 weekly_digest records delivery before sending** — `scripts/weekly_digest.py:445-457` and `:262`.
(a) `archive()` (commits a row with `emailed_to` set) runs before `send_email()`; SMTP
failure → archive falsely records delivery; `--no-email` also records `emailed_to`.
Fix: send first, then archive with `emailed_to = to if sent else None`; wrap send in
try so a send failure still archives (with NULL emailed_to) rather than crashing.
(b) Poll watch-list uses `COALESCE(p.fielded_end, p.fielded_start) < end[:10]` —
excludes polls whose fielding ended on digest day (they show up a week late). Change
`<` to `<=` (the article windows use full timestamps; this one is date-truncated).

**1.11 schema.sql has drifted from the live DB** — `db/schema.sql:46-73`.
`ai_analysis` in schema.sql lacks `review_reason` and `reviewed_at`, which the pipeline
writes (`ai_pipeline.py:1116`) and the review API reads/writes (`review.py:47,98-99`).
A fresh `scripts/init_db.py` database crashes the pipeline on first review-flag. Fix:
add both columns to schema.sql (`review_reason TEXT`, `reviewed_at TIMESTAMP`). Audit
`PRAGMA table_info` of the live DB vs schema.sql for any other drifted table while at it.

**1.12 military.py 500s every leap day** — `api/routes/military.py:340,363`.
`today.replace(year=today.year - 1)` raises ValueError when `date.today()` is Feb 29
(unguarded; no app exception handlers). Fix: helper
`def _year_ago(d): try: return d.replace(year=d.year-1); except ValueError: return d.replace(year=d.year-1, day=28)`.

---

## §2 — Frontend correctness

**2.1 Article fetch race** — `frontend/src/hooks/useDashboardData.js:22-40`.
No abort/latest-wins guard; FilterBar fires a state update per keystroke (no debounce
anywhere), so a slow stale response clobbers newer results and clears the spinner early.
Fix: `useRef` request counter — capture `const id = ++latest.current` before the fetch,
apply results only `if (id === latest.current)`. (Same guard on the stats fetch.)
Optionally debounce the search input ~250ms in FilterBar.

**2.2 Filter change doesn't reset pagination** — `App.js:486` / `FilterBar.jsx:42-44`.
Every sidebar callback pairs `setFilters(...)` with `setPage(1)` (e.g. App.js:393) but
FilterBar gets the raw setter, so filtering while on page 3 shows "No articles match"
with "25 results" in the header. Fix: pass FilterBar a wrapped setter in App.js:
`(updater) => { setFilters(updater); setPage(1); }`.

**2.3 Stats ignore bias/source_name scoping** — `useDashboardData.js:44-46`.
Destructures only 5 filter keys; `api.js` `SCOPING_KEYS` declares 7 and
`stats.py:66-67` accepts both missing ones — clicking a bias segment or source in
StatsSidebar narrows the feed but not the charts beside it. Fix: add `bias` and
`source_name` to the destructure, the `fetchStats` object, and the effect deps.

**2.4 Unhandled rejections leave dead UI** — `ReviewQueue.js:477` (no `.catch` →
permanent "Loading..."), `ReviewQueue.js:36-54` (`handleResolve` no try/finally →
`submitting` stuck, buttons dead), `KeyFigures.jsx:66-70` (same for the candidate
modal's `processing`). Fix: `.catch(...).finally(() => setLoading(false))`;
try/finally around the awaits; surface the error (even `alert()` beats silence —
there is no toast/error-boundary in the app).

**2.5 Military heatmap shifted one day for UTC+ viewers** — `MilitaryTab.jsx:406,468`.
Cells are local midnights keyed via `toISOString().slice(0,10)`; in Taipei (+08:00,
the primary audience) local midnight converts to the PREVIOUS UTC day, so every cell
shows the prior day's data and today never renders. Fix: derive the key from local
fields — `` `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}` `` —
(API rows are plain `YYYY-MM-DD` strings).

**2.6 NaN in sentiment trend (latent)** — `SignalCharts.jsx:112`.
`parseFloat(d.avg_score?.toFixed(3))` → NaN when a day's `avg_score` is null (possible
per schema; zero rows today; recharts drops NaN points but the tooltip would print
"NaN"). Fix: `score: d.avg_score == null ? null : +d.avg_score.toFixed(3)`.

**2.7 Bias filter can't select blue_leaning** — `FilterBar.jsx:110-117`.
The dropdown omits `blue_leaning`, which `seed_sources.py:228` assigns (ETtoday Polls)
and `SourceBadge.jsx:9` colours. Add the option.

**2.8 economy.py returns 200 for invalid direction** — `api/routes/economy.py:626-627`.
`return {"error": ...}` → FastAPI 200; the shared `request()` wrapper only checks
`res.ok`, so consumers see "success". Fix: `raise HTTPException(400, "invalid direction")`
(pattern: diplomacy.py:443). Low severity (UI sends only fixed values).

**2.9 notes.py never persists score_override** — `api/routes/notes.py:14,36-39,51-55`.
`create_note` applies `score_override` to `ai_analysis.sentiment_score` but the
`analyst_notes` INSERT omits the `score_override` column (schema.sql:125 defines it) and
`_NOTE_UPDATE_COLUMNS` excludes it — the audit trail of what was overridden is lost.
Fix: add the column to the INSERT and the update whitelist.

---

## §3 — Prompt & LLM cost (the headline ask)

Measured from `/var/log/gemini-usage.jsonl` (14.4-day window). Tier 1 = 4,830 calls /
66M prompt tokens; per-stage numbers below re-verified independently.

**3.1 [STAGING-FIRST] Negative-result markers for the poll/exercise passes** —
`ai_pipeline.py:1829,1849` and `:1519,1540`.
Idempotency is only `NOT EXISTS (inserted rows)`, and a no-yield article writes no
marker, so it re-qualifies every 6h tick for 14 days: **poll_only: 895 calls on 33
unique articles (96% repeats — one article scanned 56×); exercise_only: 1,738 calls on
519 unique (70% repeats)**, and `LIMIT 30 DESC` starves older articles entirely.
Fix: add columns (e.g. `poll_scanned_at`, `exercise_scanned_at` on `articles` — schema.sql
+ server_deploy.sh migration block), stamp them after every scan, and add
`AND a.poll_scanned_at IS NULL` to the selection. Eliminates ~95% of both stages' spend.

**3.2 thinking_level medium on template-extraction stages** — `ai_pipeline.py:1331,1777`
(and tier1:795, diplomacy:1406).
Thinking tokens bill at the output rate and dwarf useful output: **poll_only 51.4×,
exercise_only 12.1×, diplomacy_only 3.79×** thinking:output. social_translator.py:96
already uses `low`. Recommend: `low` for poll_only and exercise_only (pure
template-following extraction). Keep tier1 and diplomacy at medium for now (stance-sign
reasoning is the pipeline's hardest task — measure before touching).

**3.3 Tier-2 escalation review resends everything and discards most of it** —
`ai_pipeline.py:1131-1159`.
Re-sends the 29.8K-char system prompt + 14.5K officials block + full article to
gemini-3.5-flash requesting the complete extraction schema, then reads back only
sentiment/escalation/entities (+confidence/topic for flags) — ~13.8K prompt tokens/call,
0% cache. Fix: a dedicated ~2K-token review prompt (sentiment scale + escalation
rubric + the Tier-1 extraction to second-guess) requesting only those fields.

**3.4 Officials roster injected wholesale** — `ai_pipeline.py:378,778`.
`_OFFICIALS_BLOCK` is 14,504 chars (29 current + 99 FORMER officials) sent on every
Tier-1/Tier-2 call (~17M tokens per fortnight). `generate_dynamic_glossary` (line 566)
already demonstrates filter-by-article-content. Recommend: keep the small CURRENT
roster static (preserves the implicit-cache prefix) and move FORMER officials into the
dynamic glossary section, injected only when the name appears in the article. Mind
prompt ordering: static prefix first, dynamic content last, to keep implicit caching.

**3.5 [STAGING-FIRST] Batch API for Tier 1** — `ai_pipeline.py:788`.
Results aren't needed for 6 hours, yet 500-article batches run as sequential
interactive calls (+0.3s sleep each). Gemini Batch pricing is ~50% off the same
tokens — that's ~half the bill of the largest line item. Bigger refactor: submit batch,
collect on the next tick (or poll at end of run).

**3.6 Poll prompt example contradicts its own canonical rules** — `ai_pipeline.py:1728,1734,1740`.
The few-shot example emits `未決定`/"Undecided" and `沒意見`/"No opinion" while the
canonical block (1684-1712) mandates `尚未決定` and `未明確回答`/"No response". Models
imitate examples over instructions; `未決定` appears in NO poll_labels_canonical.json
mapping, so Step 3d can never repair those rows (they split PollsTab trend series —
PollsTab keys series on `label_en`). Fix: correct the example labels to the canonical
forms; add a `未決定 → 尚未決定` mapping to rule 2 anyway (belt and braces for rows
already written).

**3.7 Diplomacy rules duplicated across two prompts** — `ai_pipeline.py:552 vs 1349-1373`.
~2.3KB of scope-gate/sign/worked-example rules duplicated verbatim with a keep-in-sync
comment; the claimed blocker (brace-heavy plain string) doesn't prevent plain string
concatenation. Fix: extract a `_DIPLOMACY_RULES` constant and build both prompts with
`+`. Same drift class: `scripts/backfill_military_exercises.py:83` already lost
"Talisman Sabre" from the named-exercise list vs live `ai_pipeline.py:550` — re-sync it
(or extract that list to a shared constant too).

---

## §4 — Architecture / structural ([STAGING-FIRST] unless noted)

**4.1 Missing index: `entities(article_id)`** — `db/schema.sql:111` (can go on main —
one line + migration). 96,978 rows; every feed page and entity filter does correlated
scans (EXPLAIN-verified `SCAN e`); identical to the fixed 20s `/diplomacy/summary`
regression (idx_analysis_article, line 108-110). Add
`CREATE INDEX IF NOT EXISTS idx_entities_article ON entities(article_id);` to BOTH
schema.sql and the server_deploy.sh migration block.

**4.2 Versioned migrations instead of deploy-script heredocs** — `server_deploy.sh:32,264-268,313-344`.
Today: new schema objects hand-appended to an inline heredoc AND schema.sql; `ALTER
TABLE ... 2>/dev/null || true` swallows every error including SQLITE_BUSY (the sqlite3
CLI has no busy_timeout, and deploys can coincide with the 6h cron lock → migration
silently skipped → API 500s on the missing column); dated data-fix UPDATEs re-run on
every deploy. Fix: a `schema_migrations` table + ordered migration files applied by
both `init_db.py` and deploy; at minimum add `.timeout 30000` to every sqlite3 CLI call
and stop swallowing stderr (`|| true` only after checking for "duplicate column").

**4.3 Unify the four review-queue state machines** — `db/schema.sql` (military_exercises,
polls, diplomacy_statements share approval_status/merged_into_id/reviewed_at/reviewed_by;
key_figure_statements is a divergent fifth missing merged_into_id/reviewed_by), each
with its own near-identical candidates/approve/dismiss/merge endpoints (military.py
~533-748, diplomacy.py ~273-417, polls.py ~771-1338, stats.py 421-444). Fix: shared
route/service factory implementing the approve/dismiss/merge machine once; align
key_figure_statements' columns.

**4.4 Shared canonical-key module** — `api/routes/military.py:208` mirrors
`ai_pipeline.py:30-45` (`_build_exercise_canonical_key`, suffix regexes, `_COORD_BBOX`)
with a comment admitting manual sync ("api/ cannot import from scraper/"). Identical
today; any tweak forks the key space and silently breaks exercise auto-grouping.
Fix: a top-level `shared/` (or `common/`) module both packages import.

**4.5 Tier-1 loop inlines `_insert_exercise_row`** — `ai_pipeline.py:1000-1080` vs
`1425-1487`: ~80 duplicated lines (whitelists, CJK guard, bbox, INSERT). Polls already
share `_insert_poll_row` (line 1088). Fix: call the helper from the Tier-1 loop.

**4.6 One entity-normalisation semantics** — `ai_pipeline.py:327` (bidirectional prefix)
vs `scripts/renormalise_entities.py` (exact-only, documented as such BECAUSE the prefix
logic corrupts title-prepended names). After the §1.2 hotfix, do the deeper fix: shared
normalisation with exact match + an explicit alias/title-strip table in
entity_canonical.json, used by both write path and backfill.

**4.7 Source behaviour flags belong on the sources table** — `ai_pipeline.py:702`
(`_POLLSTER_DIRECT_SOURCES` name set), `:1493` (`EXERCISE_ONLY_SOURCES = ['YDN']`) —
display-name strings owned by seed_sources.py; the code even WARNs about renames
(603-607) but only for one of the two sets. Fix: `is_pollster_direct` /
`exercise_only_scan` columns on `sources`, set by seed_sources.py.

**4.8 poll_labels_canonical rules should scope by family** —
`scripts/canonicalise_poll_labels.py:42-75` supports only `question_keys` enumeration;
schema.sql:483 already has `poll_questions.family` (`'vote_intent'` etc.). Any new
race's key falls into rule 1's catch-all (不知道 → "No response"), contradicting the
vote-intent canonical, and the mangled rows are unrecoverable afterwards (en-name
mismatch). Fix: add `families` / `exclude_families` scoping to `_resolve_scope` and
re-scope rule 1/rule 2 by family instead of enumerated keys.

**4.9 Shared scraper utils** (one PR, mechanical):
- `scraper/utils/dates.py`: ROC-year conversion (6 copies: mac_economic:80,
  mac_poll:109, mnd_incursion:83, tw_nia_population:60, trade_access:139,
  mac_macro:96 — which also cross-imports from mac_economic); `date_from_url`
  (fjsen:16 / guancha:17 — note their shared fallback silently stamps `now()` on
  unmatched URLs, worth a `None`+skip instead).
- `scraper/utils/http.py`: `BROWSER_HEADERS` + client factory (~15 copies; already
  drifted — trade_access still Chrome/120, weibo/ptt timeout=20 vs 30, refresh_officials
  bot UA).
- `scraper/utils/db.py`: `save_article()` (the 6-column INSERT is cloned in ~12
  scrapers with truncation drift 10K vs 25K — pick one, document it); route ALL scripts
  through `get_connection()` (cluster_events:96, rebuild_fts:25, weekly_digest:435,
  seed_sources:433, init_db:15 open bare connections missing the busy_timeout/FK
  pragmas — cluster_events runs inside the cron pipeline and can hit "database is
  locked").
- `scraper/utils/llm.py`: `get_gemini_client()` (3 copies of the bootstrap) and
  `parse_llm_json()` (6 copies, 2 divergent algorithms — ai_pipeline:804/1336/1411/1782,
  backfill_military_exercises:168, social_translator:101).

**4.10 auth.py fail-open default** — `api/auth.py:30-32`: when `ADMIN_TOKEN` is unset,
`require_admin`/`is_admin` are no-ops (documented legacy mode). Prod has the token set,
but consider failing closed (or at least logging loudly at startup) so a lost env file
doesn't silently disable app-level auth.

---

## §5 — Hygiene / dead code (safe on main)

- `git rm mfa_debug.html python` (65KB scraper-dev scratch capture + a 0-byte
  shell-redirect accident, both tracked); `rm cross_strait.db` (0-byte, root; canonical
  DB is `db/cross_strait_signal.db`) and `rm -r .pytest_cache` (both untracked,
  already gitignored).
- `.env` has the SMTP_HOST/PORT/USER/DIGEST_TO block duplicated three times — collapse
  to one (verify values match first).
- Dead exports in `frontend/src/api.js` (zero importers): `fetchEntities`, `fetchNotes`,
  `fetchMilitaryIncursionsMonthly`, `fetchMilitaryExerciseSummary`, `deleteOptionParty`,
  `mergeDiplomacyStatement` (note: `fetchArticle`/`fetchArticleCluster` are NOW used —
  keep). Dead route `GET /api/economy/series/meta` (economy.py:357, zero callers).
  `notes.py` PUT/DELETE have no UI; notes are write-only — finish the feature or trim
  to the used POST.
- `App.js:330-337`: seven-branch else-if that mostly maps `tab.id` to itself →
  `setView(["feed","stats","social"].includes(tab.id) ? "feed" : tab.id)`.
- `refresh_officials.py`: add a minimum-holder-count guard before overwriting
  current_officials.json (Wikidata outage currently produces a gutted roster, exit 0;
  mitigated today only by the documented manual diff review).
- `mac_poll_scraper.py:171`: the any-None binary heuristic + blind `vals[0..2]` fails
  loudly (KeyError → per-URL retry) rather than corrupting data, but a shape assertion
  with a clear log line would stop the silent every-run re-fail while an anomalous PDF
  persists.

## Deferred / rejected

- `GET /review/queue` unauthenticated — **refuted**: nginx `deny all` on `/review/`
  (public vhost) + basic-auth (admin vhost); app-level gate would still be nice
  defence-in-depth if ever re-proxied.
- keyword_filter's 2000-char window — documented, accepted trade-off
  (.claude/rules/ai-pipeline.md:78).
- Relaxed vs strict VISIBLE predicates — documented intent (api-routes.md); the copies
  within each family are covered by §4.9-style dedup if desired.
