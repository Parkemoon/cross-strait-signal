---
paths:
  - "api/routes/**"
  - "api/main.py"
---

# API Layer

Endpoint list is in `/docs` (Swagger). Non-obvious rules per route below.

## `articles.py` — `/api/articles`

Filter params: `topic`, `sentiment`, `source_place`, `source_name`, `bias`, `urgency`, `escalation_only`, `entity`, `search`, `include_pending`.

- `source_name` is prefix-matched against `s.name` (so `"LTN"` matches all LTN feeds).
- `bias` is exact match on `s.bias`.
- `source_place` maps: `PRC`/`TW` → exact `s.place` match; `hk` → `s.place IN ('HK', 'MO')`; `intl` → `s.place NOT IN ('PRC', 'TW', 'HK', 'MO')`. Never hardcode places beyond these four.
- `include_pending=true` skips the `analyst_approved=1` filter — admin build always sends it, public build never does.
- `POST /api/articles/{id}/approve` sets `analyst_approved=1`.
- `PATCH /api/articles/{id}/translation` updates `title_en_override`, `summary_en_override`, `key_quote_override`.

## `stats.py` — `/api/stats`

**All aggregation queries must include the `VISIBLE` constant** defined at the top of `dashboard_stats()`:

```sql
a.is_hidden = 0 AND a.analyst_approved = 1 AND (ai.needs_human_review = 0 OR ai.review_resolved = 1)
```

Scoping filters are centralised in `_build_filter_clause(topic, source_place, urgency, escalation_only, entity, source_name, bias)` — add new article-level filters there, not inline. When active, sentiment aggregations scope to those filters while topics/sources/entities/escalation signals stay global. The response always includes `global_avg_sentiment_score` and `global_sentiment_by_place` for ghost-dot comparison in the sidebar. `sentiment_by_place` normalises raw `s.place` values into four display buckets (PRC/TW/HK/INTL) via a `PLACE_BUCKET` SQL CASE expression — never group by raw `s.place` in this query or you'll get duplicate rows for UK, SG, etc.

Escalation signals use a 24h window.

Key Figures endpoints:
- `GET /api/stats/key-figures` — approved statements only
- `GET /api/stats/key-figures/candidates` — pending grouped by figure
- `POST /api/stats/key-figures/statements/{id}/approve`
- `POST /api/stats/key-figures/statements/{id}/dismiss`

## `review.py` — `/api/review`

Confirm and override both set `analyst_approved=1` on the article (auto-approve). Dismiss sets `is_hidden=1`. `GET /review/stats` returns `pending`, `resolved`, and `pending_approval` counts.

## `notes.py` — `/api/notes`

CRUD for analyst notes with AI override support.

## `social.py` — `/api/social/`

Returns latest Weibo snapshot (all 50 items with `is_cross_strait` flag) + PTT posts from last 24h. `PATCH /api/social/{id}/translation` saves analyst translation override.

## `economy.py`

- `GET /api/economy/series` — params `ids`, `start`, `end`, `months`. Returns time-series JSON with metadata baked in.
- `GET /api/economy/series/meta` — just the indicator catalog.
- `GET /api/economy/verification` — all reporter pairs with computed `gap_pct = (value_b - value_a) / value_a * 100`. Each pair carries a `kind` field (`prc_customs` / `hk_customs` / `hk_csd_direct`) for UI grouping. Add new pairs in `VERIFICATION_PAIRS`.
- `GET /api/economy/investment-by-industry?direction=prc_to_tw|tw_to_prc&top=N` — returns `{direction, latest_period, latest, top_industries, series}`. `latest` is the most recent snapshot's industries sorted by amount desc; `series` is a flat list for the top-N industries across all periods (caller pivots for area charts).
- `GET /api/economy/people-records` — bidirectional cross-strait residency. Pivots `cross_strait_population` into `directions.{prc_in_taiwan|hk_macao_in_taiwan|taiwanese_in_prc}.{metric}: [...]`; loads `policy_timeline` from the JSON sidecar (`scraper/processors/prc_tw_people_records.json`, also home to `_meta`); pairs with existing `tw_visitors_prc_10k` and `prc_visitors_tw_10k` series under `flows.{tw_visitors_to_prc|prc_visitors_to_tw}` so the frontend can show stock alongside flow. Sidecar JSON is loaded once at module import — touch `economy.py` (or restart uvicorn) after editing the JSON to see changes.

**Indicator catalog and verification pairs are declared in `SERIES_META` and `VERIFICATION_PAIRS`** — add new series/pairs there. Each series needs a `category` field (`trade`/`verification`/`investment`/`people`/`macro`).

## `trade_access.py`

- `GET /api/trade-access/items` — params `direction`, `status`, `hs_prefix`, `search`, `limit`, `offset`. Filtered slice of `trade_access`, sorted with banned/suspended first via a CASE expression on `STATUS_ORDER`.
- `GET /api/trade-access/summary` — returns asymmetry counts (`by_direction[direction][status] = n`), `status_labels`, and the hardcoded `SUSPENSION_WAVES` timeline. Add new waves there when MoF announces them.
- `GET /api/trade-access/cifer-snapshot` — most recent `cifer_snapshots` row plus a short history (replaces the previously hardcoded `CIFER_SNAPSHOT` constant in the frontend).

## `military.py`

PLA incursion endpoints (MND + PLATracker dual-source):
- `GET /api/military/incursions` — params `start`, `end`, `source`. Day-level rows.
- `GET /api/military/incursions/monthly` — monthly aggregates. Fields PLATracker never published (vessels, coast-guard counts, zone breakdown) return `null` not `0` — by design; the frontend renders MND-era only for those sparklines.
- `GET /api/military/incursions/summary` — KPI strip (7d / 30d / 365d counters, trend deltas).
- `GET /api/military/zones` — ADIZ zone heatmap (six MND sector codes — see [[mnd-incursion-parsing]] memory for parser wording variants).

Exercise tracker endpoints:
- `GET /api/military/exercises` — public read: approved rows only. Params `start`, `end`, `performer`. Uses LEFT JOIN against `ai_analysis` with a relaxed VISIBLE predicate so Step 3b exercise-only rows (no `ai_analysis` row) are still served.
- `GET /api/military/exercises/summary` — counts by performer/kind.
- `GET /api/military/exercises/candidates` (admin) — `status='pending'` rows grouped by canonical key for batch review.
- `POST /api/military/exercises/{id}/approve` (admin) — flips status. Auto-merges other same-`canonical_name` pending rows into this one (one click clears a whole exercise group).
- `POST /api/military/exercises/{id}/dismiss` (admin)
- `POST /api/military/exercises/{id}/merge` (admin) — explicit merge with `merged_into_id`.
- `PATCH /api/military/exercises/{id}` (admin) — analyst edits. Sends only changed fields (the frontend builds a minimal patch via `buildExercisePatch`). Always recomputes `canonical_name` from the final `name_en`. Coordinates bbox-validated to 8–35°N / 105–135°E — out-of-bbox PATCHes return 400 (vs the AI ingest path which silently nulls — at the analyst layer we'd rather argue). If the patch explicitly touched `location_label`, the (label → lat/lng) pair is auto-recorded into `military_locations_auto.json` for future AI extractions.

Used by `MilitaryTab.jsx` for both the incursion KPI strip / ADIZ map and the Exercise Tracker section (map + list + analyst review queue + edit modal).

## `polls.py` — `/api/polls` (Phase 2d, read endpoints)

Public-safe read routes only in this file; admin endpoints (candidates queue, approve/dismiss/merge, PATCH, manual create) will land in a follow-up commit. All routes apply `approval_status = 'approved'` so pending / dismissed / merged rows stay in the review queue.

- `GET /api/polls/` — recent approved feed, paginated (`limit`, `offset`). Filters: `pollster` (slug), `family` (question family), `question_key` (canonical key). `question_key` wins over `family` if both supplied. Each poll envelope carries its full `questions[]` array with nested `options[]` — one polls row CAN hold multiple questions (see [[database]] on the multi-question survey envelope), so the frontend gets the whole survey context, not just the filtered question. Sort: `fielded_start DESC, id DESC`.
- `GET /api/polls/by-question/{question_key}` — cross-pollster time series for the trend charts. Filters: `pollster` (one slug), `start`, `end` (ISO dates on `fielded_start`). Returns canonical question metadata at top level (`question_text_zh/en`, `family`, `scale_type`, `description`) plus a `waves[]` array sorted `fielded_start ASC` (ready for left-to-right plotting). 404 on unknown `question_key`. Each wave carries pollster slug + bias so the frontend can colour per-pollster.
- `GET /api/polls/roster` — pollster list with `approved_count` per pollster (LEFT JOIN so zero-poll pollsters still appear in the filter dropdown). Sorted by `status` then `name_en`.
- `GET /api/polls/topics` — question families grouped, each carrying its `poll_questions` entries with `approved_count`, `first_wave`, `last_wave`. Within each family, questions sort by `approved_count DESC`.

Non-obvious rules:
- The list endpoint's `question_key` / `family` filter uses an `EXISTS` subquery (not a `JOIN`) so polls aren't multiplied when a poll carries the filtered question — one row per polls envelope, not one per (poll, result).
- `poll_results` are batch-fetched in ONE follow-up query keyed on the page of poll_ids returned, then pivoted in Python — avoids N+1.
- `polls.methodology_note` is survey-level (pollster, mode, fielding window), never question-specific. Question wording lives on `poll_questions.question_text_*`. If you need per-pollster wording variants for the same canonical question, that's a future feature (`pollster_question_phrasings` table) — don't bake it into `methodology_note`.
- Provenance discriminators on returned polls: `source_article_id NOT NULL` = AI extraction; `reviewed_by LIKE 'backfill:%'` = script-seeded (NCCU long series); otherwise manual analyst entry.
