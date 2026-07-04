from fastapi import APIRouter, Query, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from api.database import db_conn
from api.auth import require_admin

router = APIRouter(prefix="/api/notes", tags=["notes"])


# Columns on analyst_notes that PUT /notes/{id} is allowed to update. Anything
# outside this set is rejected by the API even if a future Pydantic field gets
# accidentally exposed as a column name.
_NOTE_UPDATE_COLUMNS = {"note_text", "sentiment_override", "topic_override", "score_override"}


class NoteCreate(BaseModel):
    article_id: int
    note_text: str
    sentiment_override: Optional[str] = None
    topic_override: Optional[str] = None
    score_override: Optional[float] = None


class NoteUpdate(BaseModel):
    note_text: Optional[str] = None
    sentiment_override: Optional[str] = None
    topic_override: Optional[str] = None
    score_override: Optional[float] = None


@router.post("/", dependencies=[Depends(require_admin)])
def create_note(note: NoteCreate):
    """Add analyst commentary to an article."""
    with db_conn() as conn:
        cursor = conn.execute("""
            INSERT INTO analyst_notes (article_id, note_text, sentiment_override, topic_override, score_override)
            VALUES (?, ?, ?, ?, ?)
        """, (note.article_id, note.note_text, note.sentiment_override,
              note.topic_override, note.score_override))

        if note.sentiment_override:
            conn.execute(
                "UPDATE ai_analysis SET sentiment = ? WHERE article_id = ?",
                (note.sentiment_override, note.article_id)
            )
        if note.topic_override:
            conn.execute(
                "UPDATE ai_analysis SET topic_primary = ? WHERE article_id = ?",
                (note.topic_override, note.article_id)
            )
        if note.score_override is not None:
            conn.execute(
                "UPDATE ai_analysis SET sentiment_score = ? WHERE article_id = ?",
                (note.score_override, note.article_id)
            )

        conn.commit()
        return {"id": cursor.lastrowid, "status": "created"}


@router.get("/article/{article_id}")
def get_notes_for_article(article_id: int):
    """Get all analyst notes for an article."""
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM analyst_notes WHERE article_id = ? ORDER BY created_at DESC",
            (article_id,)
        ).fetchall()
        return {"notes": [dict(r) for r in rows]}


@router.put("/{note_id}", dependencies=[Depends(require_admin)])
def update_note(note_id: int, note: NoteUpdate):
    """Update an existing note."""
    with db_conn() as conn:
        row = conn.execute(
            "SELECT article_id FROM analyst_notes WHERE id = ?", (note_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Note not found")
        article_id = row["article_id"]

        # Build SET clause from whitelisted columns only.
        candidate_updates = {
            "note_text": note.note_text,
            "sentiment_override": note.sentiment_override,
            "topic_override": note.topic_override,
            "score_override": note.score_override,
        }
        updates = {
            col: val for col, val in candidate_updates.items()
            if val is not None and col in _NOTE_UPDATE_COLUMNS
        }
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()

        set_clause = ", ".join(f"{col} = ?" for col in updates)
        conn.execute(
            f"UPDATE analyst_notes SET {set_clause} WHERE id = ?",
            (*updates.values(), note_id),
        )

        if note.sentiment_override:
            conn.execute(
                "UPDATE ai_analysis SET sentiment = ? WHERE article_id = ?",
                (note.sentiment_override, article_id),
            )
        if note.topic_override:
            conn.execute(
                "UPDATE ai_analysis SET topic_primary = ? WHERE article_id = ?",
                (note.topic_override, article_id),
            )
        if note.score_override is not None:
            conn.execute(
                "UPDATE ai_analysis SET sentiment_score = ? WHERE article_id = ?",
                (note.score_override, article_id),
            )

        conn.commit()
        return {"id": note_id, "status": "updated"}


@router.delete("/{note_id}", dependencies=[Depends(require_admin)])
def delete_note(note_id: int):
    """Delete a note."""
    with db_conn() as conn:
        conn.execute("DELETE FROM analyst_notes WHERE id = ?", (note_id,))
        conn.commit()
        return {"id": note_id, "status": "deleted"}
