"""One-shot backfill: extract military_exercises from existing MIL_EXERCISE
articles, leaving the rest of their analysis untouched.

Use case: after deploying the Tier 1 prompt change in ai_pipeline.py that
adds the `military_exercises` JSON field, existing articles already
classified as MIL_EXERCISE won't have any exercise candidates extracted
(they were processed before the prompt change). Re-running the full Tier
1 pass on those articles would risk duplicating key_figure_statements
and resetting analyst-touched fields on ai_analysis.

This script targets just the exercise-extraction step:
    1. Pull MIL_EXERCISE articles within the last --days window with no
       military_exercises row yet.
    2. Send a stripped-down JSON-mode Gemini prompt asking ONLY for
       military_exercises.
    3. Apply the same canonicalisation + CJK guard + bbox sanity check
       used in ai_pipeline.py, insert as pending rows.

Idempotent — articles that already have any military_exercises row are
skipped (by design, even merged/dismissed rows count as "seen"). Re-run
freely.

    python scripts/backfill_military_exercises.py --days 120 --limit 200
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv
load_dotenv()


from scraper.utils.db import get_connection
from scraper.utils.llm import get_gemini_client, parse_llm_json
from scraper.processors.ai_pipeline import (
    _CANONICAL_ENTITIES,
    _NAMED_EXERCISES,
    _build_exercise_canonical_key,
    _exercise_canonical_en,
    _geocode_from_label,
    generate_dynamic_glossary,
)

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from shared.exercise_keys import (
    VALID_PERFORMERS as _VALID_PERFORMERS,
    VALID_EXERCISE_KINDS as _VALID_EXERCISE_KINDS,
    COORD_BBOX as _COORD_BBOX,
)

_client = get_gemini_client()

_EXTRACT_PROMPT = """You are extracting military exercises from a news article.
Return ONLY valid JSON of the shape:

{
  "military_exercises": [
    {
      "name_zh": "exercise name in original language, or null if unnamed",
      "name_en": "exercise name in English, or null if unnamed",
      "performer_side": "PRC | ROC | US | JP | MULTI",
      "participants": ["ISO codes — only when performer_side is MULTI"],
      "exercise_kind": "live_fire | readiness_drill | joint_patrol | named_exercise | cyber | amphibious | other",
      "start_date": "YYYY-MM-DD or null",
      "end_date": "YYYY-MM-DD or null",
      "location_label": "human-readable location",
      "latitude": "decimal degrees, null unless confidently parseable",
      "longitude": "decimal degrees, null unless confidently parseable",
      "description_en": "1-2 sentence English summary (English only)",
      "description_zh": "verbatim snippet from article",
      "confidence": 0.85
    }
  ]
}

Extract any military exercise mentioned in the article — both named
exercises (""" + _NAMED_EXERCISES + """) AND unnamed drills explicitly described
(live-fire / readiness / patrols / amphibious / cyber). Map actor →
performer_side: PLA/解放軍/東部戰區 → PRC; MND/國防部/國軍/漢光 → ROC;
INDOPACOM/USN/USAF → US; JSDF/海上自衛隊 → JP; two-or-more sides → MULTI
with `participants`.

LOCATION HANDLING — `location_label` is REQUIRED whenever the article
mentions ANY place reference for the exercise: a named base, range,
harbour, county, body of water, region, or compass-quadrant ("eastern
Taiwan waters", "Bashi Channel", "Kaohsiung offshore", "砲測中心北岸陣地 /
artillery testing centre north-bank position", "Jiupeng base 九鵬基地",
"Kinmen", "Hualien airbase", "near Senkaku"). Translate Chinese place
names to English; preserve the original in description_zh. The bar for
location_label is LOW — if you can identify a place in the article, fill
it. `latitude` and `longitude` are SEPARATE: only emit numeric coords
when confidently resolvable (named base with established centroid, named
waters, or explicit coords) — otherwise both null. False-negatives-
preferred applies to lat/lng only, NOT to location_label.

DATE ANCHORING — `start_date` and `end_date` default to the article's
PUBLISHED year (given below). "Today", "this week", "on 22 May", or any
month/day without a year → use the PUBLISHED year. Only use a different
year when the article explicitly cites one. Do NOT anchor dates to your
training-data baseline.

description_en MUST be English. Return {"military_exercises": []} if no
exercise is mentioned. Use British spelling.
"""


def _canonical_lookup(name_zh: str | None, name_en: str | None) -> tuple[str | None, str | None]:
    """Mirrors the canonicalisation logic in ai_pipeline.py's exercise insert.
    Now exact-match-only via the shared _exercise_canonical_en helper —
    see that function for why substring matching was wrong."""
    canonical_en = _exercise_canonical_en(name_zh, name_en)
    return canonical_en, _build_exercise_canonical_key(canonical_en)


def _sanitise_coords(lat, lng, fallback_label=None):
    try:
        lat = float(lat) if lat is not None else None
        lng = float(lng) if lng is not None else None
    except (TypeError, ValueError):
        lat, lng = None, None
    lat_min, lat_max, lon_min, lon_max = _COORD_BBOX
    if lat is not None and not (lat_min <= lat <= lat_max):
        lat = None
    if lng is not None and not (lon_min <= lng <= lon_max):
        lng = None
    if lat is None or lng is None:
        lat, lng = None, None
    # Curated lookup fallback — fill coords from the location_label when the
    # AI declined to supply them, so the map gets populated for known bases.
    if lat is None and fallback_label:
        lat, lng = _geocode_from_label(fallback_label)
    return lat, lng


def extract(article):
    """Call Gemini and return the military_exercises list (empty if none)."""
    glossary = generate_dynamic_glossary(
        article['content_original'] or '',
        article['title_original'] or '',
    )
    prompt = f"""{_EXTRACT_PROMPT}

{glossary}

SOURCE: {article['source_name']}
LANGUAGE: {article['language']}
PUBLISHED: {article['published_at'] or 'unknown'}
TITLE: {article['title_original']}

FULL TEXT:
{(article['content_original'] or '')[:5000]}"""

    resp = _client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "max_output_tokens": 4000,
            "temperature": 0.1,
            "thinking_config": {"thinking_level": "medium"},
        },
    )
    try:
        return parse_llm_json(resp.text, envelope_key='military_exercises')
    except json.JSONDecodeError:
        print(f"  [warn] non-JSON response for article {article['id']}: {resp.text[:120]}")
        return []


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days",  type=int, default=120, help="Look-back window in days.")
    p.add_argument("--limit", type=int, default=200, help="Max articles to process.")
    p.add_argument("--dry-run", action="store_true", help="Print without writing.")
    args = p.parse_args()

    conn = get_connection()
    articles = conn.execute("""
        SELECT a.id, a.title_original, a.content_original, a.language,
               a.published_at,
               s.name AS source_name
        FROM articles a
        JOIN ai_analysis ai ON ai.article_id = a.id
        JOIN sources s ON s.id = a.source_id
        WHERE ai.topic_primary = 'MIL_EXERCISE'
          AND a.published_at >= datetime('now', ?)
          AND NOT EXISTS (
              SELECT 1 FROM military_exercises me WHERE me.article_id = a.id
          )
        ORDER BY a.published_at DESC
        LIMIT ?
    """, (f'-{args.days} days', args.limit)).fetchall()

    print(f"Found {len(articles)} MIL_EXERCISE articles with no exercise rows yet.")
    if not articles:
        return

    total_inserted = 0
    for i, article in enumerate(articles, 1):
        try:
            exercises = extract(article)
        except Exception as e:
            print(f"  [{i}/{len(articles)}] article {article['id']}: extract failed — {e}")
            continue

        if not exercises:
            print(f"  [{i}/{len(articles)}] article {article['id']}: 0 exercises")
            continue

        for ex in exercises:
            performer = (ex.get('performer_side') or '').upper().strip()
            if performer not in _VALID_PERFORMERS:
                continue

            name_zh_raw = (ex.get('name_zh') or '').strip() or None
            name_en_raw = (ex.get('name_en') or '').strip() or None
            canonical_en, canonical_key = _canonical_lookup(name_zh_raw, name_en_raw)

            desc_en = (ex.get('description_en') or '').strip()
            if desc_en:
                cjk_ratio = sum(1 for c in desc_en if '一' <= c <= '鿿') / len(desc_en)
                if cjk_ratio > 0.15:
                    desc_en = None

            location_label = (ex.get('location_label') or '').strip() or None
            lat, lng = _sanitise_coords(ex.get('latitude'), ex.get('longitude'),
                                        fallback_label=location_label)

            participants = ex.get('participants') if performer == 'MULTI' else None
            participants_json = (json.dumps(participants) if isinstance(participants, list)
                                 and participants else None)

            kind = (ex.get('exercise_kind') or 'other').strip()
            if kind not in _VALID_EXERCISE_KINDS:
                kind = 'other'

            if args.dry_run:
                print(f"    DRY-RUN insert: article={article['id']} perf={performer} "
                      f"name={canonical_en!r} kind={kind} dates={ex.get('start_date')}→{ex.get('end_date')}")
                continue

            conn.execute("""
                INSERT INTO military_exercises
                (article_id, canonical_name, name_en, name_zh, name_raw,
                 performer, participants_json, exercise_kind,
                 start_date, end_date, location_label, latitude, longitude,
                 description_en, description_zh, confidence, approval_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """, (
                article['id'], canonical_key, canonical_en, name_zh_raw,
                name_en_raw or name_zh_raw, performer, participants_json, kind,
                ex.get('start_date'), ex.get('end_date'),
                location_label,
                lat, lng, desc_en,
                (ex.get('description_zh') or '').strip() or None,
                ex.get('confidence', 0.7),
            ))
            total_inserted += 1
        if not args.dry_run:
            conn.commit()
        print(f"  [{i}/{len(articles)}] article {article['id']}: {len(exercises)} exercises")

    print(f"\nDone. Inserted {total_inserted} pending exercise candidates from "
          f"{len(articles)} articles.")


if __name__ == "__main__":
    main()
