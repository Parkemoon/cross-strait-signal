"""Name registry admin queue — /api/names/*.

The registry (table name_registry, shared/name_registry.py) holds the
English form the site uses for each Chinese personal name. Rows arrive
from the seed (glossary + canonical files, approved), the Step-3f lookup
worker (Wikidata auto-approved when clean, otherwise pending) and this
queue. Approving here is what lets a name feed the resolver and the
prompt-time glossary block, so every route is admin-only.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import require_admin
from api.database import db_conn
from shared.name_style import style_name

router = APIRouter(prefix="/api/names", tags=["names"])

_COLS = ("id, zh_trad, zh_simp, en, side, source, status, qid, evidence_url, evidence_note, role_hint, "
         "candidates_json, mentions, first_article_id, confidence, created_at, reviewed_at, reviewed_by")


def _shape(r):
    import json
    d = dict(r)
    try:
        d["candidates"] = json.loads(d.pop("candidates_json") or "[]")
    except ValueError:
        d["candidates"] = []
    return d


@router.get("/candidates", dependencies=[Depends(require_admin)])
def candidates(limit: int = Query(200, ge=1, le=1000)):
    """Pending rows, most-mentioned first, with their candidate forms."""
    with db_conn() as conn:
        rows = conn.execute(
            f"SELECT {_COLS} FROM name_registry WHERE status = 'pending' ORDER BY mentions DESC, created_at ASC LIMIT ?",
            (limit,)).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM name_registry WHERE status = 'pending'").fetchone()[0]
    return {"total": total, "candidates": [_shape(r) for r in rows]}


@router.get("/candidates/count", dependencies=[Depends(require_admin)])
def candidates_count():
    with db_conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM name_registry WHERE status = 'pending'").fetchone()[0]
    return {"pending": n}


@router.get("/list", dependencies=[Depends(require_admin)])
def list_names(status: str = Query("approved"), q: Optional[str] = None, limit: int = Query(200, ge=1, le=2000)):
    """Browse the registry (approved by default); q matches either script or the English form."""
    if status not in ("pending", "approved", "rejected"):
        raise HTTPException(400, "status must be pending, approved or rejected")
    sql = f"SELECT {_COLS} FROM name_registry WHERE status = ?"
    params = [status]
    if q:
        sql += " AND (zh_trad LIKE ? OR zh_simp LIKE ? OR en LIKE ?)"
        params += [f"%{q}%"] * 3
    sql += " ORDER BY reviewed_at DESC, created_at DESC LIMIT ?"
    params.append(limit)
    with db_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"names": [_shape(r) for r in rows]}


class Decision(BaseModel):
    en: Optional[str] = None
    side: Optional[str] = None
    reviewed_by: Optional[str] = None


def _get(conn, row_id):
    row = conn.execute(f"SELECT {_COLS} FROM name_registry WHERE id = ?", (row_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"name {row_id} not found")
    return row


@router.post("/{row_id}/approve", dependencies=[Depends(require_admin)])
def approve(row_id: int, body: Decision):
    """Approve with the stored proposal, or with an edited English form
    (which marks the row analyst-sourced). An empty form cannot be approved."""
    with db_conn() as conn:
        row = _get(conn, row_id)
        en = (body.en or row["en"] or "").strip()
        if not en:
            raise HTTPException(400, "an English form is required to approve")
        if body.side and body.side not in ("TW", "PRC", "OTHER"):
            raise HTTPException(400, "side must be TW, PRC or OTHER")
        en = style_name(row["zh_trad"], en, body.side or row["side"], row["role_hint"])   # house style (shared/name_style.py)
        if "," in en:
            raise HTTPException(400, "not a single person's name (comma) — edit it or reject the row")
        source = "analyst" if en != (row["en"] or "") else row["source"]
        conn.execute("""
            UPDATE name_registry SET en = ?, side = COALESCE(?, side), source = ?, status = 'approved',
                   reviewed_at = datetime('now'), reviewed_by = COALESCE(?, reviewed_by)
            WHERE id = ?""", (en, body.side, source, body.reviewed_by, row_id))
        conn.commit()
    return {"status": "approved", "id": row_id, "en": en}


@router.post("/{row_id}/reject", dependencies=[Depends(require_admin)])
def reject(row_id: int, body: Optional[Decision] = None):
    """Reject: the name stays recorded so it is never looked up again, but
    feeds nothing."""
    with db_conn() as conn:
        _get(conn, row_id)
        conn.execute("""
            UPDATE name_registry SET status = 'rejected', reviewed_at = datetime('now'),
                   reviewed_by = COALESCE(?, reviewed_by) WHERE id = ?""",
                     ((body.reviewed_by if body else None), row_id))
        conn.commit()
    return {"status": "rejected", "id": row_id}


@router.patch("/{row_id}", dependencies=[Depends(require_admin)])
def patch(row_id: int, body: Decision):
    """Edit the English form or side of any row (approved rows included);
    an edited form is analyst-sourced. Status is unchanged."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "empty patch")
    with db_conn() as conn:
        row = _get(conn, row_id)
        en = (fields.get("en") if "en" in fields else row["en"]) or None
        side = fields.get("side", row["side"])
        if side and side not in ("TW", "PRC", "OTHER"):
            raise HTTPException(400, "side must be TW, PRC or OTHER")
        if en:
            en = style_name(row["zh_trad"], en, side, row["role_hint"])
        source = "analyst" if en != row["en"] else row["source"]
        conn.execute("UPDATE name_registry SET en = ?, side = ?, source = ?, reviewed_by = COALESCE(?, reviewed_by) WHERE id = ?",
                     (en, side, source, body.reviewed_by, row_id))
        conn.commit()
        return _shape(_get(conn, row_id))
