from fastapi import APIRouter, Query
from api.database import get_db

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/")
def dashboard_stats(days: int = Query(7, description="Rolling window in days")):
    """Dashboard summary statistics."""
    conn = get_db()

    # Total articles
    total = conn.execute("""
        SELECT COUNT(*) FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        WHERE a.published_at >= datetime('now', ?)
    """, (f'-{days} days',)).fetchone()[0]

    # Articles by topic
    topics = conn.execute("""
        SELECT ai.topic_primary, COUNT(*) as count
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        WHERE a.published_at >= datetime('now', ?)
        GROUP BY ai.topic_primary
        ORDER BY count DESC
    """, (f'-{days} days',)).fetchall()

    # Articles by sentiment
    sentiments = conn.execute("""
        SELECT ai.sentiment, COUNT(*) as count
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        WHERE a.published_at >= datetime('now', ?)
        GROUP BY ai.sentiment
        ORDER BY count DESC
    """, (f'-{days} days',)).fetchall()

    # Articles by source
    sources = conn.execute("""
        SELECT s.name, s.country, COUNT(*) as count
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        JOIN sources s ON a.source_id = s.id
        WHERE a.published_at >= datetime('now', ?)
        GROUP BY s.id
        ORDER BY count DESC
    """, (f'-{days} days',)).fetchall()

    # Average sentiment score (the "temperature gauge")
    avg_sentiment = conn.execute("""
        SELECT AVG(ai.sentiment_score) as avg_score
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        WHERE a.published_at >= datetime('now', ?)
    """, (f'-{days} days',)).fetchone()

    # Escalation signals
    escalations = conn.execute("""
        SELECT a.id, a.title_original, a.title_en, ai.summary_en,
               ai.escalation_note, a.published_at, s.name as source_name
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        JOIN sources s ON a.source_id = s.id
        WHERE ai.is_escalation_signal = 1
          AND a.published_at >= datetime('now', ?)
        ORDER BY a.published_at DESC
    """, (f'-{days} days',)).fetchall()

    # Top entities
    top_entities = conn.execute("""
        SELECT e.entity_name_en, e.entity_type, COUNT(*) as mentions
        FROM entities e
        JOIN articles a ON e.article_id = a.id
        WHERE a.published_at >= datetime('now', ?)
        GROUP BY e.entity_name_en
        ORDER BY mentions DESC
        LIMIT 15
    """, (f'-{days} days',)).fetchall()

    # Daily sentiment trend
    sentiment_trend = conn.execute("""
        SELECT date(a.published_at) as date, AVG(ai.sentiment_score) as avg_score,
               COUNT(*) as article_count
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        WHERE a.published_at >= datetime('now', ?)
        GROUP BY date(a.published_at)
        ORDER BY date
    """, (f'-{days} days',)).fetchall()

    conn.close()

    return {
        "period_days": days,
        "total_articles": total,
        "avg_sentiment_score": avg_sentiment[0] if avg_sentiment[0] else 0,
        "topics": [dict(t) for t in topics],
        "sentiments": [dict(s) for s in sentiments],
        "sources": [dict(s) for s in sources],
        "escalation_signals": [dict(e) for e in escalations],
        "top_entities": [dict(e) for e in top_entities],
        "sentiment_trend": [dict(s) for s in sentiment_trend],
    }


@router.get("/entities")
def entity_search(
    entity_type: str = Query(None, description="person, military_unit, location, organisation"),
    days: int = Query(30)
):
    """Search and rank entities by mention count."""
    conn = get_db()

    where_clause = "WHERE a.published_at >= datetime('now', ?)"
    params = [f'-{days} days']

    if entity_type:
        where_clause += " AND e.entity_type = ?"
        params.append(entity_type)

    rows = conn.execute(f"""
        SELECT e.entity_name, e.entity_name_en, e.entity_type, COUNT(*) as mentions
        FROM entities e
        JOIN articles a ON e.article_id = a.id
        {where_clause}
        GROUP BY e.entity_name_en
        ORDER BY mentions DESC
        LIMIT 30
    """, params).fetchall()

    conn.close()
    return {"entities": [dict(r) for r in rows]}