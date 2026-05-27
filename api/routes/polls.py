"""Poll tracker endpoints (Phase 2d).

Surfaces the `polls` + `poll_results` tables built by the Tier 1 side-
extract (`ai_pipeline.py`), the Step 3c poll-only pass, the NCCU
backfill (`seed_nccu_polls.py`), and manual analyst entries.

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

  3. **`question_key` is analyst-assigned at approval, not AI-extracted**
     — the AI's free-text question wording lives in
     `polls.pending_results_json` until the reviewer picks (or creates)
     a canonical key per question. On approve, the server materialises
     `poll_results` rows from that blob and NULLs the column.
"""
import json
import re
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import require_admin
from api.database import db_conn


# These mirror the documented enums in db/schema.sql. Not enforced as
# CHECK constraints there, but validated at the API edge so analyst typos
# don't quietly enter the canonical question vocabulary.
_VALID_FAMILIES    = {'identity', 'unification', 'approval', 'attitude', 'vote_intent', 'issue'}
_VALID_SCALE_TYPES = {'approve_disapprove', 'support_oppose', 'five_point',
                      'six_point', 'choice', 'numeric'}
_VALID_POLLSTER_BIAS   = {'academic', 'green', 'green_leaning', 'centrist',
                          'blue_leaning', 'blue', 'state_official'}
_VALID_POLLSTER_STATUS = {'active', 'historical', 'ad_hoc', 'unknown'}

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# question_key slug: lowercase alphanumerics + underscores. The seed roster
# follows `family_pollster_scaletypehint` (e.g. `identity_nccu_3pt`,
# `approval_lai_overall`) — analysts free to extend but the slug must be
# safe to embed in URL path segments and SQL parameter names.
_QUESTION_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")

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
        poll = dict(row)
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

    return {"pollsters": [dict(r) for r in rows]}


# ============================================================
# POST /pollsters — create a new pollster (admin)
# ============================================================
# When the AI's pollster_hint doesn't resolve to any seeded pollster, the
# review queue lets the analyst create the new row inline rather than
# falling back to the `unknown` bucket and dropping the attribution. Same
# control vocabulary as the schema.sql seed (bias / status enums).

class PollsterCreate(BaseModel):
    slug:         str
    name_en:      str
    name_zh:      Optional[str] = None
    bias:         str
    status:       Optional[str] = 'active'
    cadence:      Optional[str] = None
    methodology:  Optional[str] = None
    notes:        Optional[str] = None
    homepage_url: Optional[str] = None


@router.post("/pollsters", dependencies=[Depends(require_admin)])
def create_pollster(body: PollsterCreate):
    """Insert a new pollster row. 409 on slug conflict — analyst can pick
    the existing one from the dropdown instead. Validators mirror the
    enums documented in db/schema.sql so a typo doesn't quietly enter the
    canonical roster."""
    slug = body.slug.strip()
    if not _QUESTION_KEY_RE.match(slug):
        raise HTTPException(400, f"slug {slug!r} must match {_QUESTION_KEY_RE.pattern}")
    if body.bias not in _VALID_POLLSTER_BIAS:
        raise HTTPException(400, f"invalid bias {body.bias!r} (allowed: {sorted(_VALID_POLLSTER_BIAS)})")
    status = (body.status or 'active').strip()
    if status not in _VALID_POLLSTER_STATUS:
        raise HTTPException(400, f"invalid status {status!r} (allowed: {sorted(_VALID_POLLSTER_STATUS)})")
    name_en = body.name_en.strip()
    if not name_en:
        raise HTTPException(400, "name_en is required")

    with db_conn() as conn:
        existing = conn.execute("SELECT id FROM pollsters WHERE slug = ?", (slug,)).fetchone()
        if existing:
            raise HTTPException(409, f"pollster {slug!r} already exists")

        cur = conn.execute("""
            INSERT INTO pollsters
                (slug, name_zh, name_en, bias, status, cadence, methodology, notes, homepage_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (slug, (body.name_zh or '').strip() or None, name_en, body.bias, status,
              (body.cadence or '').strip() or None,
              (body.methodology or '').strip() or None,
              (body.notes or '').strip() or None,
              (body.homepage_url or '').strip() or None))
        conn.commit()
        return {"id": cur.lastrowid, "slug": slug}


# ============================================================
# GET /topics — question families with counts
# ============================================================

@router.get("/questions")
def polls_questions():
    """Flat catalogue of every `poll_questions` row — the dropdown source
    for the manual-entry modal. Cheap, public read; distinct from
    `/topics` (grouped by family with approved counts) and `/candidates`
    (admin, returns the catalogue inlined alongside pending poll
    envelopes). Keep this endpoint dependency-free so the manual-entry
    modal doesn't need admin auth just to populate a picker."""
    with db_conn() as conn:
        rows = conn.execute("""
            SELECT question_key, question_text_zh, question_text_en,
                   family, scale_type, description
            FROM poll_questions
            ORDER BY family, question_key
        """).fetchall()
    return {"question_keys": [dict(r) for r in rows]}


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
        q = dict(r)
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


# ============================================================
# Admin / review helpers
# ============================================================

def _validate_iso_date(value: str, field_name: str) -> str:
    """Reject anything that isn't a real YYYY-MM-DD calendar date.
    Matches the same guard `military.py` uses on PATCH so polls behave
    consistently when analysts edit dates by hand."""
    if not _ISO_DATE_RE.match(value):
        raise HTTPException(400, f"{field_name} must be YYYY-MM-DD, got {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, f"{field_name} is not a real calendar date: {value!r}")
    return value


def _validate_date_range(start: Optional[str], end: Optional[str]):
    """Reject a fielded_end strictly before fielded_start. Both arguments
    must already be valid ISO dates (caller runs `_validate_iso_date`
    first). Either may be None — same-day polls leave fielded_end NULL.
    Trend charts pivot on `fielded_end || fielded_start`, so a reversed
    range plots the wave at the wrong x-axis point."""
    if not start or not end:
        return
    if date.fromisoformat(end) < date.fromisoformat(start):
        raise HTTPException(
            400, f"fielded_end {end!r} is before fielded_start {start!r}",
        )


def _resolve_pollster_id(conn, slug: Optional[str]) -> Optional[int]:
    """Map a pollster slug to its FK id. None when slug is None.
    400s on empty string (an analyst-driven write must commit to a
    pollster — silent fallback to `unknown` is reserved for the AI
    ingest path). 404s on a set-but-unknown slug."""
    if slug is None:
        return None
    cleaned = slug.strip().lower()
    if not cleaned:
        raise HTTPException(400, "pollster_slug cannot be empty")
    row = conn.execute(
        "SELECT id FROM pollsters WHERE slug = ?", (cleaned,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"unknown pollster slug: {slug!r}")
    return row["id"]


def _resolve_question_id(conn, spec: dict) -> int:
    """Resolve one entry of an approve / create payload's `questions[]`
    array to a `poll_questions.id`. If the spec's `question_key` already
    exists we use it; otherwise we INSERT a new poll_questions row,
    which requires the spec to also carry text_zh / text_en / family /
    scale_type. Mirrors how analysts mentally pick "match existing
    question" vs "this is a new canonical question" in the review UI."""
    key = (spec.get("question_key") or "").strip().lower()
    if not key:
        raise HTTPException(400, "questions[].question_key is required")
    if not _QUESTION_KEY_RE.match(key):
        raise HTTPException(
            400,
            f"question_key {key!r} must be lowercase alphanumerics + underscores",
        )
    existing = conn.execute(
        "SELECT id FROM poll_questions WHERE question_key = ?", (key,)
    ).fetchone()
    if existing:
        return existing["id"]

    # New key — analyst is creating a canonical question. Demand the full
    # metadata so we never end up with a sparse poll_questions row that
    # later trend charts can't render a title for.
    text_zh    = (spec.get("text_zh") or "").strip()
    text_en    = (spec.get("text_en") or "").strip()
    family     = (spec.get("family") or "").strip().lower()
    scale_type = (spec.get("scale_type") or "").strip().lower()
    desc       = (spec.get("description") or "").strip() or None
    missing = [k for k, v in [("text_zh", text_zh), ("text_en", text_en),
                              ("family", family), ("scale_type", scale_type)] if not v]
    if missing:
        raise HTTPException(
            400,
            f"creating question_key {key!r} requires fields: {', '.join(missing)}",
        )
    if family not in _VALID_FAMILIES:
        raise HTTPException(400, f"invalid family {family!r} (allowed: {sorted(_VALID_FAMILIES)})")
    if scale_type not in _VALID_SCALE_TYPES:
        raise HTTPException(400, f"invalid scale_type {scale_type!r} (allowed: {sorted(_VALID_SCALE_TYPES)})")

    cur = conn.execute(
        """INSERT INTO poll_questions
           (question_key, question_text_zh, question_text_en, family, scale_type, description)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (key, text_zh, text_en, family, scale_type, desc),
    )
    return cur.lastrowid


def _validated_option(opt: dict, question_label: str, idx: int) -> tuple:
    """Coerce one option dict to (label_zh, label_en, percentage) with the
    same rules `_insert_manual_results` enforces — label non-empty, pct
    numeric and in 0–100. Used by both the materialise (AI-extracted) and
    manual-entry paths so a single contract gates poll_results writes.

    `question_label` is just for error messages — pass the question_key
    when materialising, the array index from manual entry otherwise."""
    pct = opt.get("percentage")
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        raise HTTPException(
            400,
            f"{question_label} option {idx}: percentage must be numeric, "
            f"got {opt.get('percentage')!r}",
        )
    if not (0.0 <= pct <= 100.0):
        raise HTTPException(
            400, f"{question_label} option {idx}: percentage {pct} outside 0–100",
        )
    label_zh = (opt.get("label_zh") or "").strip()
    label_en = (opt.get("label_en") or "").strip()
    if not label_zh and not label_en:
        raise HTTPException(
            400, f"{question_label} option {idx}: needs at least one of label_zh / label_en",
        )
    return label_zh or label_en, label_en or label_zh, pct


def _materialise_pending_results(conn, poll_id: int,
                                 pending: dict, question_ids: List[int]):
    """Convert a `pending_results_json` blob to actual `poll_results`
    rows under the resolved question_ids. Caller guarantees the lengths
    line up — we re-check defensively because a malformed blob in the DB
    would otherwise raise IndexError opaque to the analyst."""
    questions = pending.get("questions") or []
    if len(questions) != len(question_ids):
        raise HTTPException(
            500,
            f"pending_results_json carries {len(questions)} questions but {len(question_ids)} "
            "resolved keys — refusing to materialise mismatched data",
        )
    for q, qid in zip(questions, question_ids):
        for i, opt in enumerate(q.get("options") or []):
            label_zh, label_en, pct = _validated_option(
                opt, f"question_id={qid}", i,
            )
            conn.execute(
                """INSERT INTO poll_results
                   (poll_id, question_id, option_label_zh, option_label_en,
                    option_order, percentage)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    poll_id, qid, label_zh, label_en,
                    opt.get("option_order", i), pct,
                ),
            )


def _insert_manual_results(conn, poll_id: int, questions_spec: List[dict],
                           question_ids: List[int]):
    """Variant of the materialise step used by the manual-entry path —
    options come directly from the analyst payload rather than from a
    pending_results_json blob. Shares `_validated_option` with the
    materialise path so both write to poll_results under the same
    contract."""
    for q, qid in zip(questions_spec, question_ids):
        opts = q.get("options") or []
        if not opts:
            raise HTTPException(400, f"question {q.get('question_key')!r} has no options")
        for i, opt in enumerate(opts):
            label_zh, label_en, pct = _validated_option(
                opt, f"question {q.get('question_key')!r}", i,
            )
            conn.execute(
                """INSERT INTO poll_results
                   (poll_id, question_id, option_label_zh, option_label_en,
                    option_order, percentage)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    poll_id, qid, label_zh, label_en,
                    opt.get("option_order", i), pct,
                ),
            )


# ============================================================
# GET /candidates — pending review queue (admin)
# ============================================================

@router.get("/candidates", dependencies=[Depends(require_admin)])
def poll_candidates():
    """Pending polls awaiting analyst review. Returns one row per pending
    poll envelope with `pending_results_json` already deserialised, the
    pollster joined in, and a thumbnail of the source article (when AI-
    extracted) so the analyst can audit the extraction without a second
    round-trip. Also includes the full `poll_questions` catalogue keyed
    by `question_key` so the review UI can populate its dropdown without
    a separate /topics call."""
    with db_conn() as conn:
        rows = conn.execute("""
            SELECT
                p.id              AS poll_id,
                p.fielded_start, p.fielded_end, p.sample_size,
                p.methodology_note, p.source_url, p.source_article_id,
                p.confidence, p.notes, p.pending_results_json,
                p.created_at      AS candidate_created_at,
                ps.slug           AS pollster_slug,
                ps.name_zh        AS pollster_name_zh,
                ps.name_en        AS pollster_name_en,
                ps.bias           AS pollster_bias,
                ps.status         AS pollster_status,
                a.url             AS article_url,
                a.title_original  AS article_title,
                COALESCE(a.title_en_override, a.title_en) AS article_title_en,
                a.published_at    AS article_published_at,
                s.name            AS article_source_name,
                s.bias            AS article_source_bias
            FROM polls p
            JOIN pollsters ps ON ps.id = p.pollster_id
            LEFT JOIN articles a ON a.id = p.source_article_id
            LEFT JOIN sources s ON s.id = a.source_id
            WHERE p.approval_status = 'pending'
            ORDER BY p.created_at DESC, p.id DESC
        """).fetchall()

        question_rows = conn.execute("""
            SELECT question_key, question_text_zh, question_text_en,
                   family, scale_type, description
            FROM poll_questions
            ORDER BY family, question_key
        """).fetchall()

    candidates = []
    for r in rows:
        d = dict(r)
        raw = d.pop("pending_results_json", None)
        try:
            pending = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            pending = None
        d["pending_questions"] = (pending or {}).get("questions") or []
        d["article"] = {
            "id":           d.pop("source_article_id", None),
            "url":          d.pop("article_url", None),
            "title":        d.pop("article_title", None),
            "title_en":     d.pop("article_title_en", None),
            "published_at": d.pop("article_published_at", None),
            "source_name":  d.pop("article_source_name", None),
            "source_bias": d.pop("article_source_bias", None),
        }
        candidates.append(d)

    return {
        "candidates":    candidates,
        "total_pending": len(candidates),
        "question_keys": [dict(q) for q in question_rows],
    }


# ============================================================
# POST /{id}/approve — materialise results + auto-merge siblings
# ============================================================

class QuestionResolution(BaseModel):
    # The slug an analyst picks (or creates) per question, in the same
    # order as the entries in `polls.pending_results_json.questions[]`.
    # When skip=True, question_key is ignored and that pending question
    # is dropped from materialisation — used for subgroup breakdowns or
    # single-statistic factoids the analyst doesn't want as their own
    # canonical question (cross-tab voter-of-X subgroups, % undecided
    # cited in isolation, etc.).
    question_key: str = ""
    skip:         bool = False
    # Fields below only required when question_key does not yet exist.
    text_zh:      Optional[str] = None
    text_en:      Optional[str] = None
    family:       Optional[str] = None
    scale_type:   Optional[str] = None
    description:  Optional[str] = None


class PollApprove(BaseModel):
    questions:        List[QuestionResolution]
    # Optional envelope overrides — analyst can correct AI mis-resolution
    # (e.g. pollster_hint that landed on `unknown`, sample_size typo) at
    # the moment of approval rather than via a follow-up PATCH.
    pollster_slug:    Optional[str] = None
    fielded_start:    Optional[str] = None
    fielded_end:      Optional[str] = None
    sample_size:      Optional[int] = None
    methodology_note: Optional[str] = None
    source_url:       Optional[str] = None
    notes:            Optional[str] = None
    reviewed_by:      Optional[str] = None


@router.post("/{poll_id}/approve", dependencies=[Depends(require_admin)])
def approve_poll(poll_id: int, body: PollApprove):
    """Approve a pending poll. Materialises `pending_results_json` into
    `poll_results` under the analyst-assigned question_keys, then
    auto-merges sibling pending rows that match `(pollster_id,
    fielded_start)` — same canonical-merge pattern as
    `military_exercises`.

    Two-pass duplicate handling:
      1. If an APPROVED row already exists for `(pollster_id,
         fielded_start)`, the candidate being approved is merged INTO it
         rather than approved — avoids creating a second envelope for
         the same survey wave. Response `status='merged_into_existing'`.
      2. Otherwise, the candidate is approved and OTHER pending rows
         with the same `(pollster_id, fielded_start)` are folded into
         it. Their `pending_results_json` is NULLed (the data lives on
         the survivor's poll_results now).

    Richness guard: refuses the approve (409) if any pending peer on the
    same key carries MORE extracted questions than this row. Without
    this, approving a 1-question news-rehash before the full release
    page silently NULLs the richer peer's pending_results_json in step
    2 — happened to the 2026-05 My-Formosa wave, where a 1-question UDN
    rehash swallowed the 15-question release."""
    with db_conn() as conn:
        row = conn.execute(
            "SELECT pollster_id, fielded_start, fielded_end, "
            "pending_results_json, approval_status "
            "FROM polls WHERE id = ?",
            (poll_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, f"poll {poll_id} not found")
        if row["approval_status"] != "pending":
            raise HTTPException(
                400,
                f"poll {poll_id} is {row['approval_status']!r}, expected 'pending'",
            )

        # Apply envelope overrides first so the (pollster_id, fielded_start)
        # twin lookup uses the analyst's corrected values, not the AI-
        # extracted ones.
        new_pollster_id = (
            _resolve_pollster_id(conn, body.pollster_slug)
            if body.pollster_slug is not None
            else row["pollster_id"]
        )
        new_fielded_start = row["fielded_start"]
        if body.fielded_start is not None:
            new_fielded_start = _validate_iso_date(body.fielded_start.strip(), "fielded_start")

        # 1. Already-approved twin? Merge into it.
        twin = conn.execute("""
            SELECT id FROM polls
            WHERE approval_status = 'approved'
              AND pollster_id = :pollster_id
              AND fielded_start = :fielded_start
              AND id != :id
            ORDER BY id ASC LIMIT 1
        """, {"pollster_id": new_pollster_id,
              "fielded_start": new_fielded_start,
              "id": poll_id}).fetchone()
        if twin:
            conn.execute("""
                UPDATE polls
                SET approval_status = 'merged',
                    merged_into_id  = ?,
                    pending_results_json = NULL,
                    reviewed_at     = datetime('now'),
                    reviewed_by     = COALESCE(?, reviewed_by)
                WHERE id = ?
            """, (twin["id"], body.reviewed_by, poll_id))
            conn.commit()
            return {
                "status":         "merged_into_existing",
                "id":             poll_id,
                "duplicate_of":   twin["id"],
                "auto_merged":    0,
            }

        # 2. Standard approve path.
        pending = None
        if row["pending_results_json"]:
            try:
                pending = json.loads(row["pending_results_json"])
            except (TypeError, ValueError):
                raise HTTPException(500, f"poll {poll_id} pending_results_json is corrupt")
        if not pending or not (pending.get("questions") or []):
            raise HTTPException(
                400,
                f"poll {poll_id} has no pending_results_json to materialise — "
                "use the manual-entry endpoint to add results from scratch",
            )

        # Richness guard: refuse to approve if a pending peer on the same
        # (pollster_id, fielded_start) carries more extracted questions.
        # The auto-merge in step 3 would NULL the richer peer's
        # pending_results_json, losing question coverage forever.
        this_q_count = len(pending["questions"])
        peers = conn.execute("""
            SELECT id, pending_results_json
            FROM polls
            WHERE approval_status = 'pending'
              AND pollster_id     = :pollster_id
              AND fielded_start   = :fielded_start
              AND id              != :id
              AND pending_results_json IS NOT NULL
        """, {"pollster_id":   new_pollster_id,
              "fielded_start": new_fielded_start,
              "id":            poll_id}).fetchall()
        richer = []
        for peer in peers:
            try:
                peer_data = json.loads(peer["pending_results_json"])
            except (TypeError, ValueError):
                continue
            peer_q = len(peer_data.get("questions") or [])
            if peer_q > this_q_count:
                richer.append((peer["id"], peer_q))
        if richer:
            details = ", ".join(f"poll {pid} ({pq} questions)" for pid, pq in richer)
            raise HTTPException(
                409,
                f"poll {poll_id} has {this_q_count} pending question(s) but "
                f"richer pending peer(s) exist on the same key: {details}. "
                "Approving this row would NULL the richer extraction in the "
                "auto-merge step. Approve the richer peer instead — this row "
                "will be folded into it.",
            )

        expected = len(pending["questions"])
        if len(body.questions) != expected:
            raise HTTPException(
                400,
                f"expected {expected} question resolutions to match the pending blob, "
                f"got {len(body.questions)}",
            )

        # Drop skipped resolutions and the parallel pending entries.
        # Approving a poll where every question is skipped would
        # materialise zero results — analyst meant to dismiss instead.
        keep_idx = [i for i, q in enumerate(body.questions) if not q.skip]
        if not keep_idx:
            raise HTTPException(
                400,
                "every question is marked skip — use dismiss instead",
            )
        kept_questions = [body.questions[i] for i in keep_idx]
        kept_pending   = {"questions": [pending["questions"][i] for i in keep_idx]}

        # Resolve / create poll_questions rows up front so a halfway-through
        # failure can't leave half the results inserted with the other half
        # un-resolved.
        question_ids = [
            _resolve_question_id(conn, q.model_dump()) for q in kept_questions
        ]

        # Apply remaining envelope overrides. reviewed_at is set via raw
        # SQL datetime('now') so the timestamp matches the conn's clock,
        # not the Python process's — appended to set_clauses directly.
        set_fields = {
            "approval_status":      "approved",
            "pollster_id":          new_pollster_id,
            "fielded_start":        new_fielded_start,
            "pending_results_json": None,
            "reviewed_by":          body.reviewed_by,
        }
        if body.fielded_end is not None:
            v = body.fielded_end.strip()
            set_fields["fielded_end"] = _validate_iso_date(v, "fielded_end") if v else None
        if body.sample_size is not None:
            set_fields["sample_size"] = int(body.sample_size)
        if body.methodology_note is not None:
            v = body.methodology_note.strip()
            set_fields["methodology_note"] = v or None
        if body.source_url is not None:
            v = body.source_url.strip()
            set_fields["source_url"] = v or None
        if body.notes is not None:
            v = body.notes.strip()
            set_fields["notes"] = v or None

        # Date-range guard runs after BOTH overrides are resolved — using
        # the row's existing fielded_end when the analyst didn't override.
        _validate_date_range(
            new_fielded_start,
            set_fields.get("fielded_end", row["fielded_end"]),
        )

        # Column whitelist for the f-string interpolation below; matches
        # the keys assembled into set_fields above. Keeps the SQL build
        # injection-proof even if a future edit accidentally derives a
        # key from user input.
        _ALLOWED = {"approval_status", "pollster_id", "fielded_start",
                    "fielded_end", "sample_size", "methodology_note",
                    "source_url", "notes", "pending_results_json",
                    "reviewed_by"}
        bad = set(set_fields) - _ALLOWED
        if bad:
            raise HTTPException(500, f"unexpected approve update keys: {sorted(bad)}")

        set_clauses = [f"{k} = :{k}" for k in set_fields] + ["reviewed_at = datetime('now')"]
        params = {**set_fields, "id": poll_id}
        conn.execute(
            f"UPDATE polls SET {', '.join(set_clauses)} WHERE id = :id", params,
        )

        _materialise_pending_results(conn, poll_id, kept_pending, question_ids)

        # 3. Pending-row auto-merge: same pollster + same fielded_start.
        cur = conn.execute("""
            UPDATE polls
            SET approval_status      = 'merged',
                merged_into_id       = :target,
                pending_results_json = NULL,
                reviewed_at          = datetime('now'),
                reviewed_by          = COALESCE(:reviewed_by, reviewed_by)
            WHERE approval_status = 'pending'
              AND pollster_id     = :pollster_id
              AND fielded_start   = :fielded_start
              AND id              != :target
        """, {
            "target":        poll_id,
            "pollster_id":   new_pollster_id,
            "fielded_start": new_fielded_start,
            "reviewed_by":   body.reviewed_by,
        })
        auto_merged = cur.rowcount
        conn.commit()

    return {
        "status":       "approved",
        "id":           poll_id,
        "question_ids": question_ids,
        "auto_merged":  auto_merged,
    }


# ============================================================
# POST /{id}/dismiss
# ============================================================

@router.post("/{poll_id}/dismiss", dependencies=[Depends(require_admin)])
def dismiss_poll(poll_id: int, reviewed_by: Optional[str] = Query(None)):
    """Mark a pending poll as dismissed. NULLs `pending_results_json`
    since the AI's extraction is being discarded — keeping it would just
    bloat the row indefinitely."""
    with db_conn() as conn:
        cur = conn.execute("""
            UPDATE polls
            SET approval_status      = 'dismissed',
                pending_results_json = NULL,
                reviewed_at          = datetime('now'),
                reviewed_by          = COALESCE(?, reviewed_by)
            WHERE id = ?
        """, (reviewed_by, poll_id))
        if cur.rowcount == 0:
            raise HTTPException(404, f"poll {poll_id} not found")
        conn.commit()
    return {"status": "dismissed", "id": poll_id}


# ============================================================
# POST /{id}/merge — explicit duplicate flag
# ============================================================

class PollMerge(BaseModel):
    target_id:   int
    reviewed_by: Optional[str] = None


@router.post("/{poll_id}/merge", dependencies=[Depends(require_admin)])
def merge_poll(poll_id: int, body: PollMerge):
    """Mark `poll_id` as a duplicate of `target_id`. The target must be
    `approved` so the merge chain can't dangle into a dismissed-or-
    already-merged target (which would hide the merged row entirely
    from every read endpoint). Same constraint `military.py`
    enforces."""
    if body.target_id == poll_id:
        raise HTTPException(400, "cannot merge a poll into itself")
    with db_conn() as conn:
        source = conn.execute(
            "SELECT approval_status FROM polls WHERE id = ?", (poll_id,)
        ).fetchone()
        if not source:
            raise HTTPException(404, f"poll {poll_id} not found")
        # Source must be in a state where merging makes sense — dismissed
        # or already-merged rows shouldn't be silently flipped to merged
        # (their state carries editorial intent the analyst signed off on).
        if source["approval_status"] not in ("pending", "approved"):
            raise HTTPException(
                400,
                f"poll {poll_id} is {source['approval_status']!r}, "
                "must be 'pending' or 'approved' to merge",
            )

        target = conn.execute(
            "SELECT id, approval_status FROM polls WHERE id = ?", (body.target_id,)
        ).fetchone()
        if not target:
            raise HTTPException(404, f"target {body.target_id} not found")
        if target["approval_status"] != "approved":
            raise HTTPException(
                400,
                f"merge target {body.target_id} is {target['approval_status']!r}, "
                "must be 'approved'",
            )
        conn.execute("""
            UPDATE polls
            SET approval_status      = 'merged',
                merged_into_id       = ?,
                pending_results_json = NULL,
                reviewed_at          = datetime('now'),
                reviewed_by          = COALESCE(?, reviewed_by)
            WHERE id = ?
        """, (body.target_id, body.reviewed_by, poll_id))
        conn.commit()
    return {"status": "merged", "id": poll_id, "merged_into_id": body.target_id}


# ============================================================
# PATCH /{id} — analyst edits to envelope-level fields
# ============================================================

class PollPatch(BaseModel):
    # All optional; only provided fields are written. Question-level
    # results are NOT editable here — analysts who need to fix a
    # percentage typo should dismiss + re-enter via the manual POST.
    # Empty strings for text fields are normalised to NULL.
    pollster_slug:    Optional[str] = None
    fielded_start:    Optional[str] = None
    fielded_end:      Optional[str] = None
    sample_size:      Optional[int] = None
    methodology_note: Optional[str] = None
    source_url:       Optional[str] = None
    notes:            Optional[str] = None


@router.patch("/{poll_id}", dependencies=[Depends(require_admin)])
def patch_poll(poll_id: int, patch: PollPatch):
    """Edit envelope-level fields on a poll (any status). Question
    wording / option percentages are NOT editable here — those live on
    `poll_results` and changing them after publication would corrupt
    cached trend charts. Use dismiss + manual re-entry if results
    themselves need correcting."""
    data = patch.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(400, "no fields to update")

    # Resolve pollster slug → id (404s on unknown slug).
    with db_conn() as conn:
        if "pollster_slug" in data:
            slug = data.pop("pollster_slug")
            if slug is None or not str(slug).strip():
                raise HTTPException(400, "pollster_slug cannot be cleared")
            data["pollster_id"] = _resolve_pollster_id(conn, slug)

        for date_field in ("fielded_start", "fielded_end"):
            if date_field in data and isinstance(data[date_field], str) and data[date_field].strip():
                _validate_iso_date(data[date_field].strip(), date_field)

        # Empty strings → NULL for nullable text fields. fielded_start is
        # NOT NULL in the schema, so we refuse to NULL it.
        if "fielded_start" in data and isinstance(data["fielded_start"], str) and not data["fielded_start"].strip():
            raise HTTPException(400, "fielded_start cannot be cleared (NOT NULL)")
        for k in ("fielded_end", "methodology_note", "source_url", "notes"):
            if k in data and isinstance(data[k], str) and data[k].strip() == "":
                data[k] = None

        existing = conn.execute(
            "SELECT fielded_start, fielded_end FROM polls WHERE id = ?", (poll_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(404, f"poll {poll_id} not found")

        # Date-range guard runs against the post-PATCH state — the value
        # the analyst supplied OR the row's existing one if untouched.
        _validate_date_range(
            data.get("fielded_start", existing["fielded_start"]),
            data.get("fielded_end",   existing["fielded_end"]),
        )

        # Column whitelist — `data` keys are derived from PollPatch field
        # names plus the pollster_slug→pollster_id rewrite above, but the
        # explicit set keeps the f-string interpolation injection-proof.
        _ALLOWED = {"pollster_id", "fielded_start", "fielded_end",
                    "sample_size", "methodology_note", "source_url", "notes"}
        bad = set(data) - _ALLOWED
        if bad:
            raise HTTPException(500, f"unexpected patch fields: {sorted(bad)}")

        set_clause = ", ".join(f"{k} = :{k}" for k in data)
        params = {**data, "id": poll_id}
        conn.execute(f"UPDATE polls SET {set_clause} WHERE id = :id", params)
        conn.commit()

    return {"status": "patched", "id": poll_id, "updated_fields": list(data.keys())}


# ============================================================
# POST / — manual entry (analyst-driven; not part of the AI pipeline)
# ============================================================

class ManualQuestion(BaseModel):
    # Same shape as QuestionResolution on approve, but each question
    # ALSO carries its option set directly (no `pending_results_json`
    # staging — manual entry skips the pending state).
    question_key: str
    text_zh:      Optional[str] = None
    text_en:      Optional[str] = None
    family:       Optional[str] = None
    scale_type:   Optional[str] = None
    description:  Optional[str] = None
    options:      List[dict]


class PollCreate(BaseModel):
    pollster_slug:    str
    fielded_start:    str
    fielded_end:      Optional[str] = None
    sample_size:      Optional[int] = None
    methodology_note: Optional[str] = None
    source_url:       Optional[str] = None
    notes:            Optional[str] = None
    reviewed_by:      Optional[str] = None
    questions:        List[ManualQuestion]


@router.post("/", dependencies=[Depends(require_admin)])
def create_poll(body: PollCreate):
    """Manual analyst entry — fallback for polls spotted outside the AI
    pipeline (analyst found a TVBS PDF the scraper missed, etc.). Skips
    the pending state entirely: row lands as `approved` with
    `poll_results` written in the same transaction. Provenance reads as
    `source_article_id IS NULL AND reviewed_by IS NOT NULL AND
    reviewed_by NOT LIKE 'backfill:%'` — the third category documented
    in `.claude/rules/database.md`.

    Also runs the same `(pollster_id, fielded_start)` twin check the
    approve path uses — refuses to create a second envelope for an
    already-approved survey wave."""
    if not body.questions:
        raise HTTPException(400, "questions[] cannot be empty")
    start = _validate_iso_date(body.fielded_start.strip(), "fielded_start")
    end = None
    if body.fielded_end:
        end = _validate_iso_date(body.fielded_end.strip(), "fielded_end")
    _validate_date_range(start, end)

    with db_conn() as conn:
        pollster_id = _resolve_pollster_id(conn, body.pollster_slug)

        twin = conn.execute("""
            SELECT id FROM polls
            WHERE approval_status = 'approved'
              AND pollster_id = ? AND fielded_start = ?
            LIMIT 1
        """, (pollster_id, body.fielded_start.strip())).fetchone()
        if twin:
            raise HTTPException(
                409,
                f"poll {twin['id']} already approved for pollster {body.pollster_slug!r} "
                f"on {body.fielded_start} — PATCH that one instead, or dismiss it first",
            )

        question_ids = [
            _resolve_question_id(conn, q.model_dump()) for q in body.questions
        ]

        cur = conn.execute("""
            INSERT INTO polls
                (pollster_id, fielded_start, fielded_end, sample_size,
                 methodology_note, source_url, notes, reviewed_by,
                 approval_status, reviewed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'approved', datetime('now'))
        """, (
            pollster_id,
            body.fielded_start.strip(),
            (body.fielded_end or "").strip() or None,
            body.sample_size,
            (body.methodology_note or "").strip() or None,
            (body.source_url or "").strip() or None,
            (body.notes or "").strip() or None,
            (body.reviewed_by or "").strip() or None,
        ))
        poll_id = cur.lastrowid

        _insert_manual_results(
            conn, poll_id, [q.model_dump() for q in body.questions], question_ids,
        )
        conn.commit()

    return {"status": "created", "id": poll_id, "question_ids": question_ids}
