---
paths:
  - "scraper/processors/**"
---

# AI Pipeline + Processors

## Three-tier AI pipeline (`ai_pipeline.py`)

- **Tier 1**: Gemini 3.1 Flash Lite — classifies all pre-filtered articles (batch limit: 500); `temperature=0.1`, `thinking_level=medium`.
- **Tier 2**: Gemini 2.5 Flash — re-reviews only escalation-flagged articles; same temperature.
- **Tier 3**: Human review queue — articles where Tier 1 and Tier 2 disagree; stay hidden from dashboard until resolved.
- **Age filter**: `process_unanalysed_articles` only processes articles with `published_at >= datetime('now', '-180 days')` — old DB backlog never reaches the AI pipeline.

## Dynamic glossary injection (`glossary.json`)

Loaded once at module level. Before each API call, both the article title and body text are scanned (`generate_dynamic_glossary(content, title)`) and matching terms (politicians, military assets, institutions in both Simplified and Traditional Chinese) are injected as a `CRITICAL TERMINOLOGY MAPPING` block to prevent romanisation hallucinations. Add new terms to `glossary.json` without touching Python. Always add both Traditional and Simplified Chinese forms for the same term.

## Entity canonical normalisation (`entity_canonical.json`)

Applied *after* AI extraction to normalise `name_en` on entity rows already written to the DB. Distinct from `glossary.json` (which is injected into the prompt *before* analysis). Covers parties, PLA branches, theater commands, and institutions in addition to named individuals. Keys ≥ 2 characters use substring matching, so `解放軍` catches the longer form `中國人民解放軍海軍`. When adding a person to `glossary.json`, add the same entry to `entity_canonical.json` too — otherwise the AI may translate their name correctly but store it under a non-canonical romanisation in the entities table.

## Key figure statement extraction (`key_figures.json`)

Tier 1 also extracts attributed `(speaker, statement)` pairs into the `key_figure_statements` table as `pending` candidates. The curated figure list lives in `key_figures.json` — 10 figures with Chinese/English names, roles, party field (DPP/KMT/PRC), portrait filenames, and alias lists used for speaker→figure_id matching. Tier 2 does NOT re-insert statements (only Tier 1 writes to this table). Statements require analyst approval via the Key Figures panel before appearing on the dashboard — intentional to prevent misattribution.

## Military exercise extraction

When Tier 1 classifies an article as `MIL_EXERCISE`, it side-extracts up to a handful of exercise candidates (name_en, name_zh, performer ∈ {PRC, ROC, US, JP, MULTI}, kind, start/end date, location label + best-effort lat/lng, English description) into `military_exercises` with `status='pending'`. The published year of the article is passed in as an anchor so partial date strings ("Aug 19") resolve to the right year. Pending rows are hidden from `/api/military/exercises` until an analyst approves them — see [[api-routes]] for the editorial flow and the canonical-name auto-merge. Extracted dates that fall outside ±1 year of `published_at` are silently dropped (likely a hallucination).

A second pass (**Step 3b** in `run_pipeline.py`, `process_exercise_only_articles`) runs the same extraction against military-source articles (YDN) the keyword pre-filter rejected. No `ai_analysis` row is written for these — they exist only to feed the exercise tracker. Capped at 30 per run, last 14 days. See `.claude/rules/scrapers.md` for the geocoding sidecars.

## Relevance gate

The prompt requires the model to set `is_cross_strait_primary` (bool) as its first decision before classification. If false, `topic_primary` is forced to `NOT_RELEVANT` both by the model and by a Python-level enforcement check. `NOT_RELEVANT` is a special pseudo-topic that exists in the DB but is not part of the 28 visible categories — it marks filtered articles and is never shown in the UI. PRC sources writing about Taiwan are explicitly exempt — their cultural/lifestyle coverage of Taiwan is analytically relevant (POL_TONGDU framing) and should not be filtered.

## Sentiment consistency check (`_validate_sentiment()`)

Called after each Tier 1 and Tier 2 extraction. Flags label/score band mismatches (e.g. `hostile` with score > −0.3) and directional labels with empty `sentiment_reasoning` to the human review queue (`needs_human_review=1`). Reuses the same low-confidence flag path — review reasons are concatenated with ` | `.

## Keyword pre-filter (`keyword_filter.py`)

Directional logic:
- PRC/HK/SG sources: must mention Taiwan, ROC, or relevant territories.
- Taiwan sources: must mention PRC, mainland, Hong Kong, or Macau.

Only `title + content[:2000]` is checked — full content is not used, to prevent page navigation/sidebar cruft from passing irrelevant articles. Irrelevant articles are marked `ai_processed=1` and skipped — they never reach the AI API.

## Social Pulse translator (`social_translator.py`)

Separate lightweight pipeline for social data — does NOT go through the article AI pipeline. Batch-translates `social_pulse` rows where `title_en IS NULL` using Gemini 3.1 Flash Lite (`thinking_level=low`). Runs as Step 2b in `run_pipeline.py` after the social scrapers.

## Don't reference `test_ai.py`

`test_ai.py` is a legacy prototype script — do not use it as a reference. It uses a stale prompt with old topic codes (`POL_UNIFICATION`, `POL_DOMESTIC`) and old sentiment values (`escalatory`/`conciliatory`) that no longer match the DB schema or the real pipeline in `ai_pipeline.py`.
