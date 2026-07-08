from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from api.database import db_conn
from api.auth import require_admin

router = APIRouter(prefix="/api/notes", tags=["notes"])

# Notes are write-only today: the admin UI's ArticleCard posts commentary +
# optional AI overrides, and nothing reads them back (analytics queries go
# straight to the DB). The PUT/DELETE/GET routes that used to live here had no
# UI and the GET returned internal analyst commentary without auth — trimmed
# 2026-07-08 (CODE_REVIEW_2026-07-03 §5). Re-add read/edit routes only
# together with a UI that uses them.


class NoteCreate(BaseModel):
    article_id: int
    note_text: str
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
