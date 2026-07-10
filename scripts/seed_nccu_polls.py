"""Seed historical NCCU ESC trend data into `polls` + `poll_results`.

Reads `scraper/processors/nccu_esc_seed.json` and upserts one polls row
per (pollster=nccu_esc, year) wave with approval_status='approved' and
the per-option percentages materialised straight into poll_results.

Skips the editorial review queue deliberately — NCCU ESC is the curated
gold-standard long series, the question_keys are seeded canonical, and
the data is transcribed from NCCU's own labelled trend chart with
per-year sum cross-validation. The review queue exists for AI-extracted
ambiguity, not authoritative ingest. Same pattern as
seed_taiwanese_in_prc_curated.py.

Idempotent — re-running upserts on (pollster_id, fielded_start) for polls
and on (poll_id, question_id, option_label_zh) for poll_results. Run
after edits to the JSON file (e.g. when NCCU publishes a new wave).

The JSON's `series[]` entries with empty `waves` (e.g. the unification
series, deferred pending a cleaner data source) are skipped silently
with an info-level log line — the script remains useful for any series
that's been transcribed without erroring on those that haven't.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scraper.utils.db import get_connection

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

JSON_PATH = os.path.join(
    os.path.dirname(__file__), '..',
    'scraper', 'processors', 'nccu_esc_seed.json',
)

POLLSTER_SLUG = 'nccu_esc'

# Standard envelope text on each backfilled poll. Identifies the row as
# script-seeded (vs analyst-entered or AI-extracted) so future audits can
# discriminate. The annual-aggregate note is the load-bearing caveat —
# fielded_start/fielded_end span the full calendar year by design, since
# NCCU merges biannual waves before publishing the trend point.
SEEDED_BY = 'backfill:seed_nccu_polls'

# Survey-level — same across all questions asked in a given wave. NCCU's
# Trend in Core Political Attitudes surveys ask multiple questions per
# fielded wave (identity + unification + party ID + …), so one polls row
# carries multiple poll_results joined via different question_ids. The
# methodology_note must describe the SURVEY, not any one question; the
# canonical question wording lives on poll_questions.question_text.
SURVEY_METHODOLOGY = (
    "Pollster: NCCU Election Study Center (政大選研中心). "
    "Mode: landline + mobile CATI, weighted by raking on sex / age / "
    "education / geography against Ministry of the Interior demographic "
    "data. Per NCCU: data points are annual aggregates of biannual waves "
    "(Jan–Jun and Jul–Dec merged), so fielded_start/end span the full "
    "calendar year. "
    "Source: Core Political Attitudes Trend Chart, Election Study Center, "
    "National Chengchi University."
)
NOTES_TEMPLATE = (
    "NCCU ESC annual aggregate ({sample_size} interviews). Transcribed "
    "from NCCU's labelled trend chart with per-year sum-to-100% cross-"
    "validation; sample size from the NCCU methodology PDF table."
)


def _resolve_pollster_id(conn) -> int:
    row = conn.execute(
        "SELECT id FROM pollsters WHERE slug = ?", (POLLSTER_SLUG,)
    ).fetchone()
    if row is None:
        raise RuntimeError(
            f"Pollster '{POLLSTER_SLUG}' not in roster — run schema migration first."
        )
    return row['id']


def _resolve_question_id(conn, question_key: str) -> int:
    row = conn.execute(
        "SELECT id FROM poll_questions WHERE question_key = ?", (question_key,)
    ).fetchone()
    if row is None:
        raise RuntimeError(
            f"Question key '{question_key}' not in poll_questions — "
            "run schema migration first (canonical keys are seeded there)."
        )
    return row['id']


def _upsert_poll(conn, pollster_id, fielded_start, fielded_end, sample_size,
                 methodology_note, notes) -> int:
    """Look up the existing poll for (pollster_id, fielded_start); update
    it in place if present, insert otherwise. Returns the poll_id.

    Why manual upsert: the polls table has no UNIQUE constraint on
    (pollster_id, fielded_start) — that uniqueness only applies to the
    seed-backfill use case, not to AI extractions where two outlets
    covering the same poll legitimately produce separate pending rows
    until analyst merge. Encoding it as a constraint would break the AI
    extraction flow."""
    row = conn.execute(
        "SELECT id FROM polls WHERE pollster_id = ? AND fielded_start = ? "
        "AND reviewed_by = ?",
        (pollster_id, fielded_start, SEEDED_BY),
    ).fetchone()
    if row is not None:
        conn.execute("""
            UPDATE polls SET
                fielded_end       = ?,
                sample_size       = ?,
                methodology_note  = ?,
                notes             = ?,
                approval_status   = 'approved',
                reviewed_at       = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (fielded_end, sample_size, methodology_note, notes, row['id']))
        return row['id']
    cur = conn.execute("""
        INSERT INTO polls
            (pollster_id, fielded_start, fielded_end, sample_size,
             methodology_note, notes, approval_status, reviewed_by, reviewed_at)
        VALUES (?, ?, ?, ?, ?, ?, 'approved', ?, CURRENT_TIMESTAMP)
    """, (pollster_id, fielded_start, fielded_end, sample_size,
          methodology_note, notes, SEEDED_BY))
    return cur.lastrowid


def _seed_series(conn, pollster_id, series) -> int:
    """Process one series block (identity_nccu_3pt or unification_nccu_6pt).
    Returns the count of poll_results rows written. Series with empty
    `waves` array (deferred series) return 0 silently."""
    qkey = series['question_key']
    waves = series.get('waves') or []
    if not waves:
        print(f"  [{qkey}] no waves to seed — skipping "
              f"({series.get('deferred_reason', 'no reason given')[:80]}...)")
        return 0

    question_id = _resolve_question_id(conn, qkey)
    options = series['options']

    written = 0
    for wave in waves:
        year = int(wave['year'])
        fielded_start = f"{year}-01-01"
        # NCCU publishes twice yearly: a June interim carrying only the
        # Jan–Jun waves, then the December final merging the full year.
        # Interim waves are flagged in the JSON so fielded_end doesn't
        # claim coverage the data doesn't have; when the final lands,
        # drop the flag and update the numbers — the upsert on
        # (pollster_id, fielded_start) overwrites the same row.
        interim = bool(wave.get('interim'))
        fielded_end = f"{year}-06-30" if interim else f"{year}-12-31"
        sample_size = int(wave['sample_size'])
        notes = NOTES_TEMPLATE.format(sample_size=f"{sample_size:,}")
        if interim:
            notes += (" June interim release (Jan–Jun waves only); "
                      "superseded by the December final.")

        poll_id = _upsert_poll(
            conn, pollster_id, fielded_start, fielded_end, sample_size,
            SURVEY_METHODOLOGY, notes,
        )

        percentages = wave['percentages']
        if len(percentages) != len(options):
            raise ValueError(
                f"{qkey} {year}: {len(percentages)} percentages but "
                f"{len(options)} options defined — JSON mismatch."
            )

        for opt, pct in zip(options, percentages):
            conn.execute("""
                INSERT INTO poll_results
                    (poll_id, question_id, option_label_zh, option_label_en,
                     option_order, percentage)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(poll_id, question_id, option_order) DO UPDATE SET
                    option_label_zh = excluded.option_label_zh,
                    option_label_en = excluded.option_label_en,
                    percentage      = excluded.percentage
            """, (poll_id, question_id, opt['label_zh'], opt['label_en'],
                  int(opt['order']), float(pct)))
            written += 1

    print(f"  [{qkey}] seeded {len(waves)} polls, {written} poll_results rows")
    return written


def main():
    with open(JSON_PATH, encoding='utf-8') as f:
        data = json.load(f)

    conn = get_connection()
    try:
        pollster_id = _resolve_pollster_id(conn)
        total = 0
        for series in data.get('series', []):
            total += _seed_series(conn, pollster_id, series)
        conn.commit()
        print(f"Done. {total} poll_results rows written/updated.")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
