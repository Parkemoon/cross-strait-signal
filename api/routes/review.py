from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone
from scraper.utils.db import get_connection

router = APIRouter()


class ReviewDecision(BaseModel):
    resolution: str          # 'confirmed', 'overridden', 'dismissed'
    sentiment_override: str | None = None
    topic_override: str | None = None
    escalation_override: bool | None = None
    note: str | None = None


@router.get("/review/queue")
def get_review_queue():
    """Return all articles flagged for human review."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT 
            a.id as article_id,
            a.title_original,
            a.title_en,
            a.url,
            a.published_at,
            s.name as source_name,
            s.country as source_country,
            s.bias,
            ai.id as analysis_id,
            ai.topic_primary,
            ai.sentiment,
            ai.sentiment_score,
            ai.urgency,
            ai.summary_en,
            ai.is_escalation_signal,
            ai.escalation_note,
            ai.confidence,
            ai.needs_human_review,
            ai.review_reason,
            ai.model_used
        FROM articles a
        JOIN sources s ON a.source_id = s.id
        JOIN ai_analysis ai ON a.id = ai.article_id
        WHERE ai.needs_human_review = 1
          AND ai.review_resolved = 0
        ORDER BY a.published_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/review/{analysis_id}/resolve")
def resolve_review(analysis_id: int, decision: ReviewDecision):
    """Resolve a human review flag."""
    conn = get_connection()

    analysis = conn.execute(
        "SELECT * FROM ai_analysis WHERE id = ?", (analysis_id,)
    ).fetchone()

    if not analysis:
        conn.close()
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Apply any overrides
    if decision.sentiment_override:
        conn.execute(
            "UPDATE ai_analysis SET sentiment = ? WHERE id = ?",
            (decision.sentiment_override, analysis_id)
        )

    if decision.topic_override:
        conn.execute(
            "UPDATE ai_analysis SET topic_primary = ? WHERE id = ?",
            (decision.topic_override, analysis_id)
        )

    if decision.escalation_override is not None:
        conn.execute(
            "UPDATE ai_analysis SET is_escalation_signal = ? WHERE id = ?",
            (decision.escalation_override, analysis_id)
        )

    # Mark as resolved
    conn.execute("""
        UPDATE ai_analysis 
        SET review_resolved = 1,
            reviewed_at = ?
        WHERE id = ?
    """, (datetime.now(timezone.utc).isoformat(), analysis_id))

    # Save note to analyst_notes if provided
    if decision.note:
        article_id = dict(analysis)['article_id']
        conn.execute("""
            INSERT INTO analyst_notes (article_id, note_text, sentiment_override, topic_override)
            VALUES (?, ?, ?, ?)
        """, (
            article_id,
            decision.note,
            decision.sentiment_override,
            decision.topic_override
        ))

    conn.commit()
    conn.close()
    return {"status": "resolved", "resolution": decision.resolution}


@router.get("/review/stats")
def get_review_stats():
    """Summary stats for the review queue."""
    conn = get_connection()
    pending = conn.execute(
        "SELECT COUNT(*) FROM ai_analysis WHERE needs_human_review = 1 AND review_resolved = 0"
    ).fetchone()[0]
    resolved = conn.execute(
        "SELECT COUNT(*) FROM ai_analysis WHERE needs_human_review = 1 AND review_resolved = 1"
    ).fetchone()[0]
    conn.close()
    return {"pending": pending, "resolved": resolved}