"""Poll tracker endpoints (Phase 2d) — read-only public-safe routes.

Surfaces the `polls` + `poll_results` tables built by the Tier 1 side-
extract (`ai_pipeline.py`), the Step 3c poll-only pass, the NCCU
backfill (`seed_nccu_polls.py`), and (eventually) manual analyst
entries. All endpoints here are public-safe — admin endpoints
(candidates queue, approve/dismiss/merge, PATCH) land in a follow-up
commit; the split is so PollsTab can be built against real data while
the approval flow is being designed.

See `db/schema.sql` (`polls`, `poll_results`, `poll_questions`,
`pollsters`) for column semantics. Two non-obvious rules worth
internalising before editing:

  1. **Visibility filter** — public reads include only
     `approval_status = 'approved'`. Pending / dismissed / merged rows
     are reserved for the admin review queue. Approved-with-NULL-
     poll_results (e.g. a manual envelope without question results yet)
     are filtered out by the inner JOIN to poll_results — by design,
     since a poll with no results has nothing to display.

  2. **Multi-question survey envelopes** — ONE polls row can carry
     multiple questions (see `.claude/rules/database.md`). The list
     endpoint deduplicates polls rows when aggregating per-question
     data; the by-question endpoint joins through poll_results to
     filter to the specific question_id.
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from api.database import db_conn

router = APIRouter(prefix="/api/polls", tags=["polls"])


# Shared SELECT projection for the public poll envelope. Centralised so
# every read endpoint returns the same fields under the same keys —
# the frontend can rely on one shape.
_POLL_PUBLIC_COLS = """
    p.id              AS poll_id,
    ps.slug           AS pollster_slug,
    ps.name_zh        AS pollster_name_zh,
    ps.name_en        AS pollster_name_en,
    ps.bias           AS pollster_bias,
    ps.status         AS pollster_status,
    p.fielded_start   AS fielded_start,
    p.fielded_end     AS fielded_end,
    p.sample_size     AS sample_size,
    p.methodology_note AS methodology_note,
    p.source_url      AS source_url,
    p.source_article_id AS source_article_id,
    p.notes           AS notes,
    p.confidence      AS confidence,
    p.reviewed_by     AS reviewed_by
"""


def _serialise_poll(row) -> dict:
    """Convert a sqlite3.Row carrying _POLL_PUBLIC_COLS into a plain dict.
    Frontend builds expect plain dicts (Row objects don't JSON-serialise
    directly across all FastAPI versions). Pulled out so the per-poll
    `questions` aggregation in the list endpoint can attach to a fresh
    object."""
    return {k: row[k] for k in row.keys()}


# ============================================================
# GET / — recent approved polls feed
# ============================================================

@router.get("/")
def polls_list(
    limit:        int = Query(50, ge=1, le=500, description="Max polls to return."),
    offset:       int = Query(0,  ge=0,         description="Offset for pagination."),
    pollster:     Optional[str] = Query(None, description="Filter to a specific pollster slug."),
    family:       Optional[str] = Query(None, description="Filter to a question family (e.g. 'identity', 'approval')."),
    question_key: Optional[str] = Query(None, description="Filter to a specific canonical question_key."),
):
    """Recent approved polls feed. Returns each polls row paired with its
    full question result set so the frontend can render either a per-poll
    card (everything we know about one survey) or a per-question slice.

    Filtering precedence: question_key overrides family (more specific).
    Pollster and question filters compose with AND.

    Sort is by fielded_start DESC then poll_id DESC — most recent first,
    deterministic tie-break on synthetic id."""
    clauses = ["p.approval_status = 'approved'"]
    params: dict = {}

    if pollster:
        clauses.append("ps.slug = :pollster")
        params["pollster"] = pollster

    # question_key wins over family if both supplied — more specific filter.
    if question_key:
        # EXISTS subquery so we don't multiply rows; we only want polls that
        # carry at least one result for this canonical question.
        clauses.append("""EXISTS (
            SELECT 1 FROM poll_results pr2
            JOIN poll_questions q2 ON q2.id = pr2.question_id
            WHERE pr2.poll_id = p.id AND q2.question_key = :qkey
        )""")
        params["qkey"] = question_key
    elif family:
        clauses.append("""EXISTS (
            SELECT 1 FROM poll_results pr2
            JOIN poll_questions q2 ON q2.id = pr2.question_id
            WHERE pr2.poll_id = p.id AND q2.family = :family
        )""")
        params["family"] = family

    params["limit"]  = limit
    params["offset"] = offset

    with db_conn() as conn:
        polls_sql = f"""
            SELECT {_POLL_PUBLIC_COLS}
            FROM polls p
            JOIN pollsters ps ON ps.id = p.pollster_id
            WHERE {' AND '.join(clauses)}
            ORDER BY p.fielded_start DESC, p.id DESC
            LIMIT :limit OFFSET :offset
        """
        poll_rows = conn.execute(polls_sql, params).fetchall()
        if not poll_rows:
            return {"polls": [], "limit": limit, "offset": offset, "count": 0}

        # Batch-fetch all results for the returned polls in one query so
        # we don't N+1. Pivoted into {poll_id: [results...]} for assembly.
        poll_ids = [r["poll_id"] for r in poll_rows]
        placeholders = ",".join(f":pid{i}" for i in range(len(poll_ids)))
        results_params = {f"pid{i}": pid for i, pid in enumerate(poll_ids)}
        results_sql = f"""
            SELECT pr.poll_id, pr.option_label_zh, pr.option_label_en,
                   pr.option_order, pr.percentage, pr.margin_error,
                   q.id AS question_id, q.question_key, q.question_text_zh,
                   q.question_text_en, q.family, q.scale_type
            FROM poll_results pr
            JOIN poll_questions q ON q.id = pr.question_id
            WHERE pr.poll_id IN ({placeholders})
            ORDER BY pr.poll_id, q.id, pr.option_order
        """
        result_rows = conn.execute(results_sql, results_params).fetchall()

    # Build per-poll → per-question → options structure.
    by_poll: dict = {pid: {} for pid in poll_ids}
    for r in result_rows:
        questions = by_poll[r["poll_id"]]
        q = questions.setdefault(r["question_id"], {
            "question_key":     r["question_key"],
            "question_text_zh": r["question_text_zh"],
            "question_text_en": r["question_text_en"],
            "family":           r["family"],
            "scale_type":       r["scale_type"],
            "options":          [],
        })
        q["options"].append({
            "label_zh":     r["option_label_zh"],
            "label_en":     r["option_label_en"],
            "option_order": r["option_order"],
            "percentage":   r["percentage"],
            "margin_error": r["margin_error"],
        })

    polls = []
    for row in poll_rows:
        poll = _serialise_poll(row)
        # dict.values() preserves insertion order (Python 3.7+) which mirrors
        # the ORDER BY q.id from the SQL — deterministic per-question order
        # within each poll envelope.
        poll["questions"] = list(by_poll[row["poll_id"]].values())
        polls.append(poll)

    return {"polls": polls, "limit": limit, "offset": offset, "count": len(polls)}


# ============================================================
# GET /by-question/{question_key} — cross-pollster time series
# ============================================================

@router.get("/by-question/{question_key}")
def polls_by_question(
    question_key: str,
    pollster: Optional[str] = Query(None, description="Optional filter to one pollster slug."),
    start:    Optional[str] = Query(None, description="ISO date — earliest fielded_start to include."),
    end:      Optional[str] = Query(None, description="ISO date — latest fielded_start to include."),
):
    """Cross-pollster time series for one canonical question — feeds the
    PollsTab hero trend charts (NCCU identity, Lai approval, etc.). One
    response object per (poll, pollster) carrying the option set, sorted
    fielded_start ASC so the frontend can plot left-to-right without
    pre-sorting.

    Includes the question_text + scale_type at the top level so the chart
    title and axis treatment are driven by the canonical question, not
    per-poll wording (which may vary across pollsters even for the same
    canonical question)."""
    with db_conn() as conn:
        q_row = conn.execute(
            "SELECT id, question_text_zh, question_text_en, family, scale_type, description "
            "FROM poll_questions WHERE question_key = ?",
            (question_key,),
        ).fetchone()
        if q_row is None:
            raise HTTPException(status_code=404, detail=f"Unknown question_key: {question_key}")

        clauses = [
            "p.approval_status = 'approved'",
            "pr.question_id = :qid",
        ]
        params: dict = {"qid": q_row["id"]}

        if pollster:
            clauses.append("ps.slug = :pollster")
            params["pollster"] = pollster
        if start:
            clauses.append("p.fielded_start >= :start")
            params["start"] = start
        if end:
            clauses.append("p.fielded_start <= :end")
            params["end"] = end

        sql = f"""
            SELECT
                p.id              AS poll_id,
                ps.slug           AS pollster_slug,
                ps.name_en        AS pollster_name_en,
                ps.bias           AS pollster_bias,
                p.fielded_start   AS fielded_start,
                p.fielded_end     AS fielded_end,
                p.sample_size     AS sample_size,
                pr.option_label_zh AS label_zh,
                pr.option_label_en AS label_en,
                pr.option_order   AS option_order,
                pr.percentage     AS percentage,
                pr.margin_error   AS margin_error
            FROM polls p
            JOIN pollsters ps ON ps.id = p.pollster_id
            JOIN poll_results pr ON pr.poll_id = p.id
            WHERE {' AND '.join(clauses)}
            ORDER BY p.fielded_start ASC, p.id, pr.option_order
        """
        rows = conn.execute(sql, params).fetchall()

    # Pivot into one entry per poll with the full option list nested.
    by_poll: dict = {}
    for r in rows:
        pid = r["poll_id"]
        if pid not in by_poll:
            by_poll[pid] = {
                "poll_id":          pid,
                "pollster_slug":    r["pollster_slug"],
                "pollster_name_en": r["pollster_name_en"],
                "pollster_bias":    r["pollster_bias"],
                "fielded_start":    r["fielded_start"],
                "fielded_end":      r["fielded_end"],
                "sample_size":      r["sample_size"],
                "options":          [],
            }
        by_poll[pid]["options"].append({
            "label_zh":     r["label_zh"],
            "label_en":     r["label_en"],
            "option_order": r["option_order"],
            "percentage":   r["percentage"],
            "margin_error": r["margin_error"],
        })

    return {
        "question_key":     question_key,
        "question_text_zh": q_row["question_text_zh"],
        "question_text_en": q_row["question_text_en"],
        "family":           q_row["family"],
        "scale_type":       q_row["scale_type"],
        "description":      q_row["description"],
        "waves":            list(by_poll.values()),
        "count":            len(by_poll),
    }


# ============================================================
# GET /roster — pollster list
# ============================================================

@router.get("/roster")
def polls_roster():
    """Pollster roster with bias / cadence / status — feeds the bias chips
    and pollster-filter dropdown in PollsTab. Includes a count of approved
    polls per pollster so the UI can suppress zero-poll entries if needed
    (rather than the UI doing a separate count query)."""
    with db_conn() as conn:
        rows = conn.execute("""
            SELECT
                ps.slug, ps.name_zh, ps.name_en, ps.bias, ps.status,
                ps.cadence, ps.methodology, ps.notes, ps.homepage_url,
                COUNT(p.id) AS approved_count
            FROM pollsters ps
            LEFT JOIN polls p
              ON p.pollster_id = ps.id AND p.approval_status = 'approved'
            GROUP BY ps.id
            ORDER BY ps.status, ps.name_en
        """).fetchall()

    return {"pollsters": [{k: r[k] for k in r.keys()} for r in rows]}


# ============================================================
# GET /topics — question families with counts
# ============================================================

@router.get("/topics")
def polls_topics():
    """Question family overview — populates the topic-browser pill row.
    Returns each `poll_questions` entry alongside its approved-poll count
    so a family pill ('Identity · 33 polls') can render without a second
    round-trip. Counts include the same VISIBLE filter as the main feed."""
    with db_conn() as conn:
        rows = conn.execute("""
            SELECT
                q.question_key, q.question_text_zh, q.question_text_en,
                q.family, q.scale_type, q.description,
                COUNT(DISTINCT p.id) AS approved_count,
                MIN(p.fielded_start) AS first_wave,
                MAX(p.fielded_start) AS last_wave
            FROM poll_questions q
            LEFT JOIN poll_results pr ON pr.question_id = q.id
            LEFT JOIN polls p
              ON p.id = pr.poll_id AND p.approval_status = 'approved'
            GROUP BY q.id
            ORDER BY q.family, q.question_key
        """).fetchall()

    # Group by family for the pill row. Each family bucket lists its
    # questions sorted by approved_count DESC so the most-used trackers
    # surface first.
    families: dict = {}
    for r in rows:
        q = {k: r[k] for k in r.keys()}
        families.setdefault(q["family"], []).append(q)
    for fam in families.values():
        fam.sort(key=lambda q: (-q["approved_count"], q["question_key"]))

    return {
        "families": [
            {"family": name, "questions": qs,
             "total_polls": sum(q["approved_count"] for q in qs)}
            for name, qs in sorted(families.items())
        ],
    }
