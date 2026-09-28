from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from api.database import db_conn
from api.auth import require_admin

router = APIRouter(tags=["review"])

SENTIMENTS = ("hostile", "cooperative", "neutral", "mixed")
# The Tier-1 topic enum, duplicated from scraper/processors/ai_pipeline.py
# (_TOPIC_ENUM) because importing that module builds a Gemini client.
# tests/test_review_resolve.py asserts the two lists stay identical.
TOPICS = (
    "MIL_EXERCISE", "MIL_MOVEMENT", "MIL_HARDWARE", "MIL_POLICY", "DIP_STATEMENT",
    "DIP_VISIT", "DIP_SANCTIONS", "PARTY_VISIT", "ECON_TRADE", "ECON_INVEST",
    "POL_DOMESTIC_TW", "POL_DOMESTIC_PRC", "POL_TONGDU", "INFO_WARFARE", "LEGAL_GREY",
    "TRANSPORT", "INT_ORG", "HUMANITARIAN", "US_PRC", "US_TAIWAN", "HK_MAC", "CULTURE",
    "CYBER", "ARMS_SALES", "SPORT", "ENERGY", "SCI_TECH", "NOT_RELEVANT",
)


class ReviewDecision(BaseModel):
    # Anything but these three used to fall through to the approve branch, so
    # a typo like 'dismiss' published the article.
    resolution: Literal["confirmed", "overridden", "dismissed"]
    sentiment_override: Literal[SENTIMENTS] | None = None
    score_override: float | None = Field(default=None, ge=-1.0, le=1.0)
    topic_override: Literal[TOPICS] | None = None
    escalation_override: bool | None = None
    note: str | None = None


def _score_problem(label, score):
    """Why `score` can't stand beside `label`, or None when it can.

    Same boundaries as the frontend's bandColour (±0.3 is neutral), because
    the card colour, the gauges and the trend all read the score, not the
    label. 'mixed' carries any score.
    """
    if label == "mixed":
        return None
    if score is None:
        return f"a {label} label needs a score"
    if label == "hostile" and not score < -0.3:
        return f"score {score:+.2f} is not hostile (needs to be below -0.3)"
    if label == "cooperative" and not score > 0.3:
        return f"score {score:+.2f} is not cooperative (needs to be above +0.3)"
    if label == "neutral" and abs(score) > 0.3:
        return f"score {score:+.2f} is not neutral (needs to be within ±0.3)"
    return None


@router.get("/review/queue")
def get_review_queue():
    """Return all articles flagged for human review."""
    with db_conn() as conn:
        rows = conn.execute("""
            SELECT
                a.id as article_id,
                a.title_original,
                a.title_en,
                a.title_en_override,
                a.summary_en_override,
                a.key_quote_override,
                a.url,
                a.published_at,
                s.name as source_name,
                s.place as source_place,
                s.bias,
                ai.id as analysis_id,
                ai.topic_primary,
                ai.sentiment,
                ai.sentiment_score,
                ai.urgency,
                ai.summary_en,
                ai.key_quote,
                ai.key_quote_en,
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
        return [dict(r) for r in rows]


@router.post("/review/{analysis_id}/resolve", dependencies=[Depends(require_admin)])
def resolve_review(analysis_id: int, decision: ReviewDecision):
    """Resolve a human review flag."""
    with db_conn() as conn:
        analysis = conn.execute(
            "SELECT * FROM ai_analysis WHERE id = ?", (analysis_id,)
        ).fetchone()

        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")

        # A label override used to leave the model's score in place, so a
        # hostile -> cooperative override still coloured and averaged as
        # hostile. When the desk touches the label or the score, the pair it
        # leaves behind has to agree. (The admin UI sends the model's label
        # back on every override, so compare against the stored values.)
        label = decision.sentiment_override or analysis["sentiment"]
        score = analysis["sentiment_score"]
        if decision.score_override is not None:
            score = decision.score_override
        if label != analysis["sentiment"] or score != analysis["sentiment_score"]:
            problem = _score_problem(label, score)
            if problem:
                raise HTTPException(status_code=422, detail=f"Sentiment override: {problem}")

        if decision.sentiment_override:
            conn.execute(
                "UPDATE ai_analysis SET sentiment = ? WHERE id = ?",
                (decision.sentiment_override, analysis_id)
            )

        if decision.score_override is not None:
            conn.execute(
                "UPDATE ai_analysis SET sentiment_score = ? WHERE id = ?",
                (decision.score_override, analysis_id)
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

        article_id = dict(analysis)['article_id']

        if decision.resolution == "dismissed":
            conn.execute("UPDATE articles SET is_hidden = 1 WHERE id = ?", (article_id,))
        else:
            # Confirm or override: auto-approve so article becomes visible on public feed
            conn.execute("UPDATE articles SET analyst_approved = 1 WHERE id = ?", (article_id,))

        conn.execute("""
            UPDATE ai_analysis
            SET review_resolved = 1,
                reviewed_at = ?
            WHERE id = ?
        """, (datetime.now(timezone.utc).isoformat(), analysis_id))

        if decision.note:
            conn.execute("""
                INSERT INTO analyst_notes (article_id, note_text, sentiment_override,
                                           topic_override, score_override)
                VALUES (?, ?, ?, ?, ?)
            """, (
                article_id,
                decision.note,
                decision.sentiment_override,
                decision.topic_override,
                decision.score_override,
            ))

        conn.commit()
        return {"status": "resolved", "resolution": decision.resolution}


@router.get("/review/stats")
def get_review_stats():
    """Summary stats for the review queue and pending approval count."""
    with db_conn() as conn:
        pending = conn.execute(
            "SELECT COUNT(*) FROM ai_analysis WHERE needs_human_review = 1 AND review_resolved = 0"
        ).fetchone()[0]
        resolved = conn.execute(
            "SELECT COUNT(*) FROM ai_analysis WHERE needs_human_review = 1 AND review_resolved = 1"
        ).fetchone()[0]
        pending_approval = conn.execute(
            """SELECT COUNT(*) FROM articles a
               JOIN ai_analysis ai ON a.id = ai.article_id
               WHERE a.analyst_approved = 0 AND a.is_hidden = 0
                 AND (ai.needs_human_review = 0 OR ai.review_resolved = 1)"""
        ).fetchone()[0]
        return {"pending": pending, "resolved": resolved, "pending_approval": pending_approval}
