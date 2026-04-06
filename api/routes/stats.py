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

    # Sentiment by source country
    sentiment_by_country = conn.execute("""
        SELECT s.country, AVG(ai.sentiment_score) as avg_score
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        JOIN sources s ON a.source_id = s.id
        WHERE a.published_at >= datetime('now', ?)
        GROUP BY s.country
    """, (f'-{days} days',)).fetchall()

    # Sentiment by political bias (Taiwan camps)
    sentiment_by_bias = conn.execute("""
        SELECT s.bias, AVG(ai.sentiment_score) as avg_score, COUNT(*) as count
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        JOIN sources s ON a.source_id = s.id
        WHERE a.published_at >= datetime('now', ?)
          AND s.bias IN ('green', 'green_leaning', 'blue')
        GROUP BY s.bias
    """, (f'-{days} days',)).fetchall()

    # Escalation signals — full article data for interactive cards
    escalation_rows = conn.execute("""
        SELECT a.id, a.url, a.title_original, a.title_en, a.language,
               a.published_at, a.content_original,
               ai.topic_primary, ai.topic_secondary, ai.sentiment, ai.sentiment_score,
               ai.urgency, ai.summary_en, ai.key_quote, ai.key_quote_en,
               ai.is_new_formulation, ai.is_escalation_signal, ai.escalation_note,
               ai.confidence,
               s.name as source_name, s.name_zh as source_name_zh,
               s.country as source_country, s.source_type
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        JOIN sources s ON a.source_id = s.id
        WHERE ai.is_escalation_signal = 1
          AND a.is_hidden = 0
          AND a.published_at >= datetime('now', '-1 day')
        ORDER BY a.published_at DESC
    """).fetchall()

    escalations = []
    for row in escalation_rows:
        article = dict(row)
        entities = conn.execute("""
            SELECT entity_name, entity_name_en, entity_type, entity_role, location_name
            FROM entities WHERE article_id = ?
        """, (article['id'],)).fetchall()
        article['entities'] = [dict(e) for e in entities]
        escalations.append(article)

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
        "escalation_signals": escalations,
        "top_entities": [dict(e) for e in top_entities],
        "sentiment_trend": [dict(s) for s in sentiment_trend],
        "sentiment_by_country": [dict(r) for r in sentiment_by_country],
        "sentiment_by_bias": [dict(r) for r in sentiment_by_bias],
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