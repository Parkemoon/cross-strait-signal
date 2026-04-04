from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from api.database import get_db

router = APIRouter(prefix="/api/notes", tags=["notes"])


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


@router.post("/")
def create_note(note: NoteCreate):
    """Add analyst commentary to an article."""
    conn = get_db()
    cursor = conn.execute("""
        INSERT INTO analyst_notes (article_id, note_text, sentiment_override, topic_override)
        VALUES (?, ?, ?, ?)
    """, (note.article_id, note.note_text, note.sentiment_override, note.topic_override))

    # Apply overrides directly to ai_analysis if provided
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
    note_id = cursor.lastrowid
    conn.close()
    return {"id": note_id, "status": "created"}


@router.get("/article/{article_id}")
def get_notes_for_article(article_id: int):
    """Get all analyst notes for an article."""
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM analyst_notes WHERE article_id = ? ORDER BY created_at DESC
    """, (article_id,)).fetchall()
    conn.close()
    return {"notes": [dict(r) for r in rows]}


@router.put("/{note_id}")
def update_note(note_id: int, note: NoteUpdate):
    """Update an existing note."""
    conn = get_db()
    
    # Get article_id for this note
    row = conn.execute(
        "SELECT article_id FROM analyst_notes WHERE id = ?", (note_id,)
    ).fetchone()

    updates = []
    params = []
    if note.note_text is not None:
        updates.append("note_text = ?")
        params.append(note.note_text)
    if note.sentiment_override is not None:
        updates.append("sentiment_override = ?")
        params.append(note.sentiment_override)
    if note.topic_override is not None:
        updates.append("topic_override = ?")
        params.append(note.topic_override)
    if note.score_override is not None:
            conn.execute(
                "UPDATE ai_analysis SET sentiment_score = ? WHERE article_id = ?",
                (note.score_override, article_id)
            )

    updates.append("updated_at = ?")
    params.append(datetime.now(timezone.utc).isoformat())
    params.append(note_id)

    conn.execute(f"UPDATE analyst_notes SET {', '.join(updates)} WHERE id = ?", params)

    # Apply overrides to ai_analysis if provided
    if row:
        article_id = row['article_id']
        if note.sentiment_override:
            conn.execute(
                "UPDATE ai_analysis SET sentiment = ? WHERE article_id = ?",
                (note.sentiment_override, article_id)
            )
        if note.topic_override:
            conn.execute(
                "UPDATE ai_analysis SET topic_primary = ? WHERE article_id = ?",
                (note.topic_override, article_id)
            )

    conn.commit()
    conn.close()
    return {"id": note_id, "status": "updated"}


@router.delete("/{note_id}")
def delete_note(note_id: int):
    """Delete a note."""
    conn = get_db()
    conn.execute("DELETE FROM analyst_notes WHERE id = ?", (note_id,))
    conn.commit()
    conn.close()
    return {"id": note_id, "status": "deleted"}