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
