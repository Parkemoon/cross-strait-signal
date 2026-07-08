"""Exercise-tracker canonicalisation + validation shared by the AI ingest
path (scraper/processors/ai_pipeline.py, scripts/backfill_military_exercises.py)
and the API editorial routes (api/routes/military.py).

These used to be hand-synced copies in each package with "keep in sync"
comments — any tweak forked the canonical-key space and silently broke
same-exercise auto-grouping (approve's auto-merge joins pending rows on
canonical_name, so the write path and the PATCH recompute MUST agree).
"""
import re

VALID_PERFORMERS = {'PRC', 'ROC', 'US', 'JP', 'MULTI'}
VALID_EXERCISE_KINDS = {'live_fire', 'readiness_drill', 'joint_patrol',
                        'named_exercise', 'cyber', 'amphibious', 'other'}

# Indo-Pacific sanity bbox: lat_min, lat_max, lon_min, lon_max. The AI
# ingest path silently nulls out-of-bbox coords (row survives to review,
# minus the map marker); the analyst PATCH path 400s instead — at the
# editorial layer we'd rather argue than discard.
COORD_BBOX = (8.0, 35.0, 105.0, 135.0)

# Collapse name variants the AI produces for the same activity. Three layers:
#   1. "Exercise No. 42" → "42" so "Han Kuang Exercise No. 42" matches
#      "Han Kuang 42 Exercise".
#   2. Strip trailing interchangeable nouns (drill/exercise/training/
#      wargame) — applied iteratively so chains like "Exercise Wargame"
#      collapse fully.
#   3. Lowercase + hyphenate.
# Parenthesised clauses are deliberately preserved — they often carry
# subtype info (CPX vs live-fire) that the merge logic must NOT collapse.
EXERCISE_NO_RE = re.compile(r'\bExercise\s+No\.?\s+(\d+)\b', re.IGNORECASE)
EXERCISE_SUFFIX_RE = re.compile(
    r'(\s+(drills?|exercises?|trainings?|wargames?))+$', re.IGNORECASE
)


def build_exercise_canonical_key(name_en):
    """Lower-hyphenated canonical form used for grouping and auto-merge."""
    if not name_en:
        return None
    s = EXERCISE_NO_RE.sub(r'\1', name_en.strip())
    s = re.sub(r'\s{2,}', ' ', s)
    s = EXERCISE_SUFFIX_RE.sub('', s).strip()
    key = s.lower().replace(' ', '-').replace('_', '-')
    return key or None
