---
paths:
  - "db/**"
  - "api/database.py"
  - "scraper/utils/db.py"
---

# Database

## Canonical DB file

`db/cross_strait_signal.db` — used by both the API (`api/database.py`) and the scraper pipeline (`scraper/utils/db.py`). `db/signal.db` also exists but is **not** the live DB. Always apply schema changes to `cross_strait_signal.db`. `db/schema.sql` is the reference; `scripts/init_db.py` executes it (idempotent for `IF NOT EXISTS` tables only — existing tables are not migrated, apply changes with direct SQL).

SQLite with FTS5 full-text search.

## Connection pattern

`api/database.py` exports `get_db()` — returns a `sqlite3.Connection` with `row_factory = sqlite3.Row`. All API routes follow the same pattern: call `get_db()`, run queries, call `conn.close()` manually (no context manager). `scraper/utils/db.py` provides the same for the pipeline side.

## Cross-table conventions worth remembering

- **articles.analyst_approved** defaults to 0; the article is hidden from the public feed until it flips to 1 (Approve button or review-queue confirm/override). Three analyst translation overrides: `title_en_override`, `summary_en_override`, `key_quote_override` — when set they take precedence over the AI translation in the frontend.
- **ai_analysis.sentiment_reasoning** is a one-sentence audit trail (who is framed how, toward whom, with a quoted phrase). Empty for neutral. `needs_human_review=1` + `review_resolved=0` additionally hides the article.
- **entities** carries lat/lng fields deferred for Phase 2c (maps).
- **key_figure_statements.approval_status** must be `approved` before display — `pending` is the default for Tier-1 candidates. Never bypass.
- **economic_indicators.period_type**: in practice always `'month'` — quarterly GDP is stored at the last month of the quarter so the monthly API serves it without special-casing.
- **trade_access** unique on (direction, hs_code); status priority `banned > ecfa_suspended > conditional > ecfa_active` is enforced in the scraper.
- **cifer_snapshots** unique on (snapshot_date, status) — one row per (date, suspended/valid).
- **investment_by_industry.amount_usd_k** is normalised to thousands of USD in both directions (outbound source CSVs are 百萬美元 and get ×1000 on ingest).
- **cross_strait_population** unique on (direction, metric, period, period_type). Three directions: `prc_in_taiwan` (TW NIA scraper writes here), `hk_macao_in_taiwan` (same scraper, spouse data only), `taiwanese_in_prc` (curated seed script). `unit` is `'persons'` or `'permits'` — distinct because one person may hold multiple permits over time. `period_type`: `'annual'` for full-year flows, `'monthly'` for sub-annual snapshots, `'snapshot'` for milestone counts.
- **pla_incursions** unique on (record_date, source). Two ingest sources: `'mnd'` (daily MND briefing scraper, full vessel/coast-guard/zone breakdown from 2020-09 onwards) and `'platracker'` (one-shot CSV backfill for 2020-09 → 2026-04, ADIZ-entry count only — vessels/coast-guard/zones are NULL by design, don't paper over with zeros). The monthly endpoint deliberately returns null for fields PLATracker never published.
- **military_exercises** is gated like `key_figure_statements` — rows start `status='pending'` and are hidden until an analyst flips them to `'approved'` (review queue) or `'dismissed'`. Also supports `status='merged'` with `merged_into_id` for duplicate collapsing. `canonical_name` is auto-derived from `name_en` and drives one-click auto-merge of same-name pending rows on approve. AI-extracted rows write `article_id`; the parallel YDN extraction (Step 3b) still writes `article_id` even when no `ai_analysis` row exists for the article — the exercise endpoint uses LEFT JOIN + a relaxed VISIBLE predicate. `latitude`/`longitude` bbox-validated to the Indo-Pacific rectangle (8–35°N, 105–135°E) on PATCH.
- **pollsters / poll_questions / polls / poll_results** (Phase 2d) — TW polling tracker, four-table set. `pollsters` is a controlled vocabulary keyed by `slug` (seeded with NCCU ESC, MyFormosa, TVBS, ETtoday, TPOF=historical, MAC, and an `unknown` fallback for AI extractions that can't identify the pollster). `pollsters.bias` extends the source-bias enum with `state_official` for state polling instruments — used today for MAC (TW executive branch); the chip colour in PollsTab is side-aware because the same value will attach to PRC state pollsters when they're added. `poll_questions.question_key` is THE cross-pollster join key — analyst-assigned during approval (never AI-extracted), so long-tail miscategorisation can't corrupt trend charts. `polls` follows the same editorial-gate pattern as `military_exercises` (`approval_status` ∈ `'pending'|'approved'|'dismissed'|'merged'`, `merged_into_id` for duplicate collapsing). Canonical-merge on approve groups multi-outlet coverage of the same underlying poll on (pollster_id, fielded_start) match. `polls.source_article_id` is populated by AI extractions, NULL for manual entries. `polls.pending_results_json` holds the AI-extracted `{questions:[…]}` blob while the row is `pending` — needed because `poll_results.question_id` is a NOT NULL FK to `poll_questions` but `question_key` is analyst-assigned, so results can't materialise until approval. `poll_results` is one row per (poll, question, option) with `option_order` preserved for stacked-chart display.
- **articles_fts** is the FTS5 mirror; use it for bilingual full-text search. Triggers keep it in sync with `articles`.

## Schema migration pattern

`init_db.py` runs the full `schema.sql` and would fail on an existing DB because original tables don't use `IF NOT EXISTS`. When adding new tables or indexes:

1. Append a `CREATE … IF NOT EXISTS` block to the inline migration in `server_deploy.sh`.
2. Add the same statement to `db/schema.sql` (with `IF NOT EXISTS`) so fresh init still works.
