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

**Override propagation, and the resulting audit-trail gap:** when `topic_override` or `sentiment_override` is set on POST/PUT, the route writes the new value to BOTH `analyst_notes` AND `ai_analysis.topic_primary` / `ai_analysis.sentiment` (notes.py:41–55, review.py:70–80). The original AI value is overwritten in place — no audit log. Consequence: after an override, `analyst_notes.topic_override` always equals `ai_analysis.topic_primary`, so an inequality check (`override != ai.<field>`) catches zero real overrides — only anomalies where ai_analysis drifted post-write. Count stored overrides directly; every non-empty override is a real reclassification per the UI flow (ReviewQueue.js:51 only sends overrides when the analyst explicitly chose "override"; ArticleCard.jsx:207-208 starts the state empty). The lost-original-AI-value side effect means per-category accuracy ("AI got DIP_STATEMENT right 95% of the time") can't be computed from current schema — would need a `topic_primary_ai_original` column or change log.

**Low-frequency race condition (deferred):** the override propagation also has no expected-old check, so if the ReviewQueue's auto-populated form state goes stale (Tier 2 reclassifies between form-open and form-save), an "override" submission that wasn't actually changed will silently revert Tier 2's call. Rare in practice — needs Tier 2 to fire in the form-edit window AND the analyst to click "override" without changing the dropdown. Real fix requires optimistic concurrency (expected-old field) or frontend dirty-tracking; neither in scope yet.

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
- `PATCH /api/military/exercises/{id}` (admin) — analyst edits. Sends only changed fields (the frontend builds a minimal patch via `buildExercisePatch`). Always recomputes `canonical_name` from the final `name_en`. Coordinates bbox-validated to 8–35°N / 105–135°E — out-of-bbox PATCHes return 400 (vs the AI ingest path which silently nulls — at the analyst layer we'd rather argue). If the patch explicitly touched `location_label`, the (label → lat/lng) pair is auto-recorded into `military_locations_auto.json` for future AI extractions. Also rejects `end_date < start_date` (the same date-range guard polls applies — symmetric across the two editorial-gated trackers).

Used by `MilitaryTab.jsx` for both the incursion KPI strip / ADIZ map and the Exercise Tracker section (map + list + analyst review queue + edit modal).

## `polls.py` — `/api/polls` (Phase 2d)

Read routes are public-safe and apply `approval_status = 'approved'`; admin routes (below) are gated by `Depends(require_admin)`. Pending / dismissed / merged rows live entirely behind the admin surface.

Public reads:
- `GET /api/polls/` — recent approved feed, paginated (`limit`, `offset`). Filters: `pollster` (slug), `family` (question family), `question_key` (canonical key). `question_key` wins over `family` if both supplied. Each poll envelope carries its full `questions[]` array with nested `options[]` — one polls row CAN hold multiple questions (see [[database]] on the multi-question survey envelope), so the frontend gets the whole survey context, not just the filtered question. Sort: `fielded_start DESC, id DESC`.
- `GET /api/polls/by-question/{question_key}` — cross-pollster time series for the trend charts. Filters: `pollster` (one slug), `start`, `end` (ISO dates on `fielded_start`). Returns canonical question metadata at top level (`question_text_zh/en`, `family`, `scale_type`, `description`) plus a `waves[]` array sorted `fielded_start ASC` (ready for left-to-right plotting). 404 on unknown `question_key`. Each wave carries pollster slug + bias so the frontend can colour per-pollster. **Each option also carries `party` + `colour_override`**: `party` = explicit `poll_option_parties` assignment (keyed on `option_label_zh`) `?? _FIGURE_PARTY` (the key_figures person→party map, loaded once at import — auto-colours the curated roster); `colour_override` is the explicit hex (independents / clashes). Frontend resolves these to the canonical palette in `partyColours.js`; identity/agree-disagree buckets resolve to `null` and keep the positional palette.
- `GET /api/polls/roster` — pollster list with `approved_count` per pollster (LEFT JOIN so zero-poll pollsters still appear in the filter dropdown). Sorted by `status` then `name_en`.
- `GET /api/polls/topics` — question families grouped, each carrying its `poll_questions` entries with `approved_count`, `first_wave`, `last_wave`. Within each family, questions sort by `approved_count DESC`.
- `GET /api/polls/questions` — flat catalogue of every `poll_questions` row. Cheap public read for the manual-entry modal's question_key picker (admin `/candidates` already inlines the catalogue but requires auth and does the full pending-row join — overkill for a dropdown source).

Admin / review queue (all `Depends(require_admin)`):
- `GET /api/polls/candidates` — `approval_status='pending'` rows with `pending_results_json` already deserialised into a `pending_questions[]` array, pollster + source-article context joined in, AND the full `poll_questions` catalogue inlined under `question_keys` so the review UI can populate its dropdown without a second roundtrip. Sorted `created_at DESC, id DESC`.
- `POST /api/polls/{id}/approve` — body `{questions:[{question_key, skip?, text_zh?, text_en?, family?, scale_type?, description?}, …], pollster_slug?, fielded_start?, fielded_end?, sample_size?, methodology_note?, source_url?, notes?, reviewed_by?}`. The `questions[]` array MUST be the same length as the pending blob's questions and order-aligned (resolution `i` materialises question `i`). Entries with `skip: true` are dropped from materialisation — used for subgroup breakdowns or single-statistic factoids the analyst doesn't want as canonical questions (cross-tabs of "voters who voted for X", "% undecided" cited in isolation). Server rejects an approve where every question is skipped (400 — use dismiss instead). For each non-skipped entry: if `question_key` exists it's reused, otherwise `text_zh/text_en/family/scale_type` are required and a new `poll_questions` row is created inline. Server materialises `poll_results` from the (filtered) pending blob, NULLs `pending_results_json`, and runs the canonical-merge: if an approved twin exists on `(pollster_id, fielded_start)` after the optional envelope overrides apply, this candidate is merged INTO it (response `status='merged_into_existing'`); otherwise other pending rows on the same key are folded into this one. `family` must be one of `identity|unification|approval|attitude|vote_intent|issue`; `scale_type` one of `approve_disapprove|support_oppose|five_point|six_point|choice|numeric`; `question_key` must match `^[a-z0-9][a-z0-9_]*$`.
- **Richness guards on approve (symmetric across both merge paths):** refuse the approve (409) if either merge path would NULL a richer extraction. (a) Step 1 — when an approved twin exists on the same `(pollster_id, fielded_start)` key but the pending row being approved carries more questions than the twin's materialised `poll_results`, refuses with a message naming the twin (analyst clears by dismissing the twin first). Rare; bites when manual-entered approved row collides with later AI extraction. (b) Step 2 — when any pending peer on the same key carries more questions than the row being approved, refuses with a message naming the richer peer (analyst clears by approving the richest one first; the others get folded in automatically). Common; bit the 2026-05 My-Formosa wave (1-question UDN rehash would have swallowed the 15-question release page). Both guards compare AI-extracted question counts in `pending_results_json`, not analyst `skip` decisions.
- `POST /api/polls/pollsters` (admin) — body `{slug, name_en, name_zh?, bias, place?, status?, cadence?, methodology?, notes?, homepage_url?}`. Used by the review queue when the AI's `pollster_hint` doesn't resolve to any seeded pollster and the analyst doesn't want to fall back to the `unknown` bucket. Slug must match `^[a-z0-9][a-z0-9_]*$`; bias one of `academic|green|green_leaning|centrist|blue_leaning|blue|state_official`; `place` one of `TW|PRC|HK|MO|SG|JP|US|UK|INTL` (default `TW`) — used by the PollsTab chip colour to side-disambiguate `state_official` between TW exec (green) and PRC state (red); status one of `active|historical|ad_hoc|unknown` (default `active`). 409 on slug conflict.
- `POST /api/polls/{id}/dismiss?reviewed_by=…` — flips to `dismissed` and NULLs `pending_results_json` (the AI extraction is discarded).
- `POST /api/polls/{id}/merge` — body `{target_id, reviewed_by?}`. Target must itself be `approved` (same constraint `military.py` enforces — the chain can't dangle into a dismissed/merged target). Source must be `pending` or `approved` — refusing to silently flip a `dismissed` or already-`merged` row into `merged` (those carry editorial intent that shouldn't be overwritten).
- `PATCH /api/polls/{id}` — envelope-level edits only: `pollster_slug`, `fielded_start`, `fielded_end`, `sample_size`, `methodology_note`, `source_url`, `notes`. `fielded_start` cannot be cleared (NOT NULL); other text fields take empty-string → NULL. Question wording / option percentages are NOT editable here — those live on `poll_results` and changing them after publication would corrupt cached trend charts. Dismiss + manual re-entry instead.
- `POST /api/polls/` — manual entry fallback. Body mirrors approve's `questions[]` shape but each question ALSO carries its `options[]` directly (no pending staging — the row lands as `approved`). 409 if an approved twin already exists on `(pollster_id, fielded_start)`.
- `GET /api/polls/option-parties` — all EXPLICIT option→party/colour assignments (the key_figures-derived party auto-resolved in `/by-question` is NOT listed — only analyst-pinned rows, so the colour picker shows pinned vs auto).
- `PUT /api/polls/option-parties` — upsert `{option_label_zh, party?, colour_override?, reviewed_by?}` keyed on `option_label_zh`. `party` ∈ `DPP|KMT|TPP|NPP|TSP|GPT|NP|PFP|CUPP|IND`; `colour_override` matches `^#[0-9a-fA-F]{6}$` and wins over party. Clearing BOTH deletes the row (revert to auto/positional). Drives candidate/party trend-line colour; seeded with the party-NAME labels (民進黨→DPP etc.) in schema.sql / server_deploy.sh.
- `DELETE /api/polls/option-parties/{label_zh}` — remove an assignment (the option reverts to key_figures auto-resolution or the positional palette).

Validation invariants (all three write paths — approve, PATCH, manual create — enforce these):
- `fielded_end >= fielded_start` when both are set (`_validate_date_range`). Reversed ranges plot at the wrong x-axis position on trend charts (waves anchor on `fielded_end || fielded_start`).
- Empty-string `pollster_slug` 400s rather than silently resolving to NULL (would violate `polls.pollster_id NOT NULL`). Use the slug `unknown` for explicit "unknown pollster" — never empty string.
- Option-shape validation lives in one helper (`_validated_option`): label_zh OR label_en non-empty, percentage numeric in `[0.0, 100.0]`. Shared by the manual-entry path AND the materialise-from-pending-blob path so a corrupt `pending_results_json` can't sneak past the guard the AI ingest already applies.

Non-obvious rules:
- The list endpoint's `question_key` / `family` filter uses an `EXISTS` subquery (not a `JOIN`) so polls aren't multiplied when a poll carries the filtered question — one row per polls envelope, not one per (poll, result).
- `poll_results` are batch-fetched in ONE follow-up query keyed on the page of poll_ids returned, then pivoted in Python — avoids N+1.
- `polls.methodology_note` is survey-level (pollster, mode, fielding window), never question-specific. Question wording lives on `poll_questions.question_text_*`. If you need per-pollster wording variants for the same canonical question, that's a future feature (`pollster_question_phrasings` table) — don't bake it into `methodology_note`.
- Provenance discriminators on returned polls: `source_article_id NOT NULL` = AI extraction; `reviewed_by LIKE 'backfill:%'` = script-seeded (NCCU long series); otherwise manual analyst entry.
- `question_key` is analyst-assigned at approve time, never AI-extracted — the AI's free-text wording lives in `polls.pending_results_json` until the analyst picks (or creates) a canonical key per question.
