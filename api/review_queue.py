"""Shared editorial review-queue state machine (code-review §4.3).

military_exercises, polls, diplomacy_statements and key_figure_statements
all gate AI-extracted candidates behind the same analyst state machine:

    pending → approved | dismissed
    pending|approved → merged   (merged_into_id must point at an approved row)

These primitives implement the transitions ONCE — existence/state guards,
reviewed_at / reviewed_by stamping, uniform response dicts. Queue-specific
behaviour stays in the route modules, layered AROUND these calls (military's
canonical auto-merge, polls' pending_results_json handling and richness
guards, dismiss side effects): those genuinely differ per queue, and
flattening them into one parametrised mega-factory would obscure rather than
simplify. Candidates/PATCH endpoints likewise stay per-queue — their grouping
keys, projections and validation are domain shape, not duplication.

Conventions:
- `table` / `label` are trusted literals owned by the route module, never
  user input (they are interpolated into SQL).
- reviewed_by stamps as COALESCE(?, reviewed_by) — passing None preserves
  whatever is already on the row.
- `extra_set` is a trusted SQL fragment appended to the UPDATE's SET list
  (e.g. ", pending_results_json = NULL" for polls).
- Primitives do NOT commit; the caller owns the transaction so it can layer
  further updates (auto-merges, side effects) atomically.
"""
from fastapi import HTTPException

# States a row may be in when it gets folded into another row. Dismissed and
# already-merged rows are excluded on purpose — their state carries editorial
# intent an analyst signed off on, and silently flipping it would erase that.
MERGEABLE_SOURCE_STATES = ('pending', 'approved')


def get_status(conn, table, label, row_id):
    """Return the row's approval_status, or 404 if the row doesn't exist."""
    row = conn.execute(
        f"SELECT approval_status FROM {table} WHERE id = ?", (row_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"{label} {row_id} not found")
    return row["approval_status"]


def approve_row(conn, table, label, row_id, reviewed_by=None):
    """pending (or any) → approved. 404 if missing."""
    get_status(conn, table, label, row_id)
    conn.execute(f"""
        UPDATE {table}
        SET approval_status = 'approved',
            reviewed_at = datetime('now'),
            reviewed_by = COALESCE(?, reviewed_by)
        WHERE id = ?
    """, (reviewed_by, row_id))
    return {"status": "approved", "id": row_id}


def dismiss_row(conn, table, label, row_id, reviewed_by=None, extra_set=""):
    """→ dismissed. 404 if missing."""
    get_status(conn, table, label, row_id)
    conn.execute(f"""
        UPDATE {table}
        SET approval_status = 'dismissed',
            reviewed_at = datetime('now'),
            reviewed_by = COALESCE(?, reviewed_by){extra_set}
        WHERE id = ?
    """, (reviewed_by, row_id))
    return {"status": "dismissed", "id": row_id}


def merge_row(conn, table, label, row_id, target_id, reviewed_by=None,
              extra_set=""):
    """Fold `row_id` into `target_id` (status='merged', merged_into_id set).

    Guards: no self-merge; source must exist and be pending/approved; target
    must exist and be 'approved' so the merge chain can't dangle into a
    dismissed-or-already-merged target (which would hide the merged row from
    every read endpoint).
    """
    if target_id == row_id:
        raise HTTPException(400, f"cannot merge a {label} into itself")
    src_status = get_status(conn, table, label, row_id)
    if src_status not in MERGEABLE_SOURCE_STATES:
        raise HTTPException(
            400,
            f"{label} {row_id} is {src_status!r}, must be one of "
            f"{'/'.join(MERGEABLE_SOURCE_STATES)} to merge",
        )
    tgt = conn.execute(
        f"SELECT approval_status FROM {table} WHERE id = ?", (target_id,)
    ).fetchone()
    if not tgt:
        raise HTTPException(404, f"target {target_id} not found")
    if tgt["approval_status"] != "approved":
        raise HTTPException(
            400,
            f"merge target {target_id} is {tgt['approval_status']!r}, "
            "must be 'approved'",
        )
    conn.execute(f"""
        UPDATE {table}
        SET approval_status = 'merged',
            merged_into_id = ?,
            reviewed_at = datetime('now'),
            reviewed_by = COALESCE(?, reviewed_by){extra_set}
        WHERE id = ?
    """, (target_id, reviewed_by, row_id))
    return {"status": "merged", "id": row_id, "merged_into_id": target_id}
