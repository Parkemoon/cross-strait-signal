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

## Poll extraction

Tier 1 side-extracts public-opinion polls (TW identity / unification / approval / vote intent) into the `polls` table as `approval_status='pending'`. Same editorial-gate pattern as `military_exercises`. The prompt requires four signals before extracting — named pollster, fielded date, sample size, and at least one numeric option — so passing references to historical poll numbers don't pollute the queue.

Two design quirks worth knowing:

- **`pollster_hint` is free text.** The AI copies the organisation name verbatim from the article. `_resolve_pollster_id` then maps it to a `pollster_id` via a three-layer match (exact → name contains hint → hint contains name) against a lookup of slug/name_zh/name_en, falling back to the seeded `unknown` pollster when nothing matches. The roster is loaded once per pipeline run. There's also a layer-0 glossary fallback: if the hint contains a `_MASTER_GLOSSARY` key, the glossary's English value is added as a second lookup candidate. This is what makes MAC's short forms (`陸委會`, `陆委会`) resolve correctly even though they aren't contiguous substrings of the formal `大陸委員會` — the glossary already canonicalises them to "Mainland Affairs Council (MAC)", and the existing layer-2 substring match catches `Mainland Affairs Council` inside that string. Free alias resolution for any pollster whose Chinese variants are already in the glossary; no separate alias table needed.
- **`pending_results_json` stages the questions until approval.** `poll_results.question_id` is a NOT NULL FK to `poll_questions`, but `question_key` is analyst-assigned (never AI-extracted) so long-tail miscategorisation can't corrupt cross-pollster trend charts. To bridge the gap, the extracted `{questions:[{question_text_zh, question_text_en, family_hint, options:[{label_zh, label_en, percentage, option_order}]}]}` is held in `polls.pending_results_json` while the row is `pending`. On approve, the review queue picks a `question_key` per question and the server materialises `poll_results` rows from the JSON then NULLs the column.

The extraction validates that `fielded_start` matches `YYYY-MM-DD`, drops options whose percentage isn't a 0–100 float, and drops questions left with no usable options. Date anchoring follows the same rule as military exercises — partial dates resolve against the article's published year.

Three prompt-level rules to know about when tuning extraction quality:

- **Multi-question extraction is mandatory.** The prompt asks for ALL distinct questions in a poll write-up (TVBS PDFs especially carry 4–6 questions in one survey wave) and allows the model to synthesise a short `question_text_zh` when the article presents only a topic header + option breakdown. An earlier "false negatives strongly preferred" framing caused cherry-picking — usually the headline question got dropped in favour of a subgroup factoid. If you're touching the Tier 1 or Step 3c poll prompt, keep both the "extract ALL distinct questions" instruction and the worked multi-question example; the subgroup-cross-tab skip rule is what prevents false positives, not the cherry-pick framing.
- **Aggregate-vs-intensity rule** — for ANY binary-with-intensity scale (satisfied/dissatisfied, trust/distrust, favourable/unfavourable, agree/disagree, good/bad — i.e. a question collapsing to two directional positions plus no-opinion), the prompt instructs the model to ALWAYS extract the 3-option aggregate form (positive / negative / no-opinion). When the article reports both top-line aggregate and parenthetical intensity breakdown, use the aggregate verbatim. When the article reports ONLY the breakdown, compute the aggregate by summing the two positive intensities and the two negative intensities — consistency across waves outranks preserving journalistic detail. EXCEPTION (preserve all options): multi-option position scales like the 統獨 7-step scale, statement-list questions where each option is a distinct claim being rated, multi-candidate vote-intent, and ranking questions — these have more than two underlying positions. **Note the "agree/disagree" inclusion:** an earlier draft of this rule treated agree/disagree as a "true Likert" exception, but the structural pattern is identical to the others (very/somewhat agree, very/somewhat disagree, no opinion) and a re-extraction test on 2026-05 surfaced the inconsistency. The 2026-05 My-Formosa wave was the canonical incident: 11 questions stored disaggregated, breaking trend charts under their existing question_keys; fixed by reaggregating + this prompt rule.
- **`_POLLSTER_DIRECT_SOURCES` auto-populates `source_url`.** When the article's `source` is in this constant (`{TVBS Poll Center, My-Formosa, ETtoday Polls}`), `_insert_poll_row` sets `polls.source_url = article.url` because the article *is* the pollster's own release page — saves the analyst a manual paste in the review queue. Add a source to this set when a new pollster homepage gets scraped directly (rather than reached via news coverage).

A second pass (**Step 3c** in `run_pipeline.py`, `process_poll_only_articles`) runs a stripped poll-only prompt against TW-side articles the keyword pre-filter rejected, restricted to titles containing 民調 or 民意調查. This catches Lai-approval / vote-intention / identity polls whose write-ups lack a cross-strait keyword angle — the keyword filter correctly rejects them for the main feed, but the polling tracker needs them. Title-only trigger is high-precision: articles whose title carries 民調 are almost always primarily about a poll. The pass is idempotent (skips articles that already have a `polls` row), capped at 30 per run over a 14-day window, and shares the `_insert_poll_row` helper with the main loop so validation stays consistent. The prompt explicitly skips party primary-selection polls (初選民調) and polls of non-TW/PRC publics, the two noise classes the title trigger most often catches.

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
