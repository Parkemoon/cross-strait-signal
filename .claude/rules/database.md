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
- **articles_fts** is the FTS5 mirror; use it for bilingual full-text search. Triggers keep it in sync with `articles`.

## Schema migration pattern

`init_db.py` runs the full `schema.sql` and would fail on an existing DB because original tables don't use `IF NOT EXISTS`. When adding new tables or indexes:

1. Append a `CREATE … IF NOT EXISTS` block to the inline migration in `server_deploy.sh`.
2. Add the same statement to `db/schema.sql` (with `IF NOT EXISTS`) so fresh init still works.
