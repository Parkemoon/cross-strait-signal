from fastapi import APIRouter, Query
from typing import Optional
from api.database import get_db

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("/")
def list_articles(
    entity: Optional[str] = Query(None, description="Filter by entity name"),
    topic: Optional[str] = Query(None, description="Filter by topic code, e.g. MIL_EXERCISE"),
    sentiment: Optional[str] = Query(None, description="destabilising, stabilising, neutral, ambiguous"),
    source_country: Optional[str] = Query(None, description="PRC or TW"),
    urgency: Optional[str] = Query(None, description="flash, priority, routine"),
    escalation_only: bool = Query(False, description="Only show escalation signals"),
    search: Optional[str] = Query(None, description="Search in titles and content"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
    
):
    """List articles with their AI analysis. Supports filtering and search."""
    conn = get_db()

    # Build the query dynamically based on filters
    where_clauses = []
    params = []

    # Always exclude hidden articles
    where_clauses.append("a.is_hidden = 0")

    if entity:
        where_clauses.append("EXISTS (SELECT 1 FROM entities e WHERE e.article_id = a.id AND (e.entity_name_en LIKE ? OR e.entity_name LIKE ?))")
        params.extend([f"%{entity}%", f"%{entity}%"])

    if topic:
        where_clauses.append("ai.topic_primary = ?")
        params.append(topic)

    if sentiment:
        where_clauses.append("ai.sentiment = ?")
        params.append(sentiment)

    if source_country:
        where_clauses.append("s.country = ?")
        params.append(source_country)

    if urgency:
        where_clauses.append("ai.urgency = ?")
        params.append(urgency)

    if escalation_only:
        where_clauses.append("ai.is_escalation_signal = 1")

    if search:
        where_clauses.append("(a.title_original LIKE ? OR a.title_en LIKE ? OR ai.summary_en LIKE ?)")
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    # Count total results
    count_sql = f"""
        SELECT COUNT(*)
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        JOIN sources s ON a.source_id = s.id
        {where_sql}
    """
    total = conn.execute(count_sql, params).fetchone()[0]

    # Fetch page of results
    offset = (page - 1) * page_size
    query_sql = f"""
        SELECT
            a.id,
            a.url,
            a.title_original,
            a.title_en,
            a.language,
            a.published_at,
            a.content_original,
            ai.topic_primary,
            ai.topic_secondary,
            ai.sentiment,
            ai.sentiment_score,
            ai.urgency,
            ai.summary_en,
            ai.key_quote,
            ai.key_quote_en,
            ai.is_new_formulation,
            ai.is_escalation_signal,
            ai.escalation_note,
            ai.confidence,
            s.name as source_name,
            s.name_zh as source_name_zh,
            s.country as source_country,
            s.source_type
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        JOIN sources s ON a.source_id = s.id
        {where_sql}
        ORDER BY a.published_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([page_size, offset])
    rows = conn.execute(query_sql, params).fetchall()

    # Convert to list of dicts
    articles = []
    for row in rows:
        article = dict(row)

        # Get entities for this article
        entities = conn.execute("""
            SELECT entity_name, entity_name_en, entity_type, entity_role, location_name
            FROM entities WHERE article_id = ?
        """, (article['id'],)).fetchall()
        article['entities'] = [dict(e) for e in entities]

        articles.append(article)

    conn.close()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "articles": articles
    }

@router.get("/{article_id}/cluster")
def get_article_cluster(article_id: int):
    """Get all articles in the same event cluster as this article."""
    conn = get_db()

    # Get the cluster ID for this article
    row = conn.execute(
        "SELECT event_cluster_id FROM articles WHERE id = ?",
        (article_id,)
    ).fetchone()

    if not row or not row['event_cluster_id']:
        conn.close()
        return {"cluster": []}

    cluster_id = row['event_cluster_id']

    # Get all articles in the same cluster
    rows = conn.execute("""
        SELECT
            a.id, a.title_original, a.title_en, a.url, a.published_at,
            ai.sentiment, ai.sentiment_score, ai.summary_en, ai.topic_primary,
            s.name as source_name, s.country as source_country, s.bias
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        JOIN sources s ON a.source_id = s.id
        WHERE a.event_cluster_id = ?
          AND a.id != ?
        ORDER BY a.published_at ASC
    """, (cluster_id, article_id)).fetchall()

    conn.close()
    return {"cluster": [dict(r) for r in rows]}

@router.get("/{article_id}")
def get_article(article_id: int):
    """Get a single article with full analysis details."""
    conn = get_db()

    row = conn.execute("""
        SELECT
            a.*,
            ai.topic_primary, ai.topic_secondary, ai.sentiment, ai.sentiment_score,
            ai.urgency, ai.summary_en, ai.summary_zh, ai.key_quote, ai.key_quote_en,
            ai.is_new_formulation, ai.is_escalation_signal, ai.escalation_note,
            ai.confidence, ai.model_used,
            s.name as source_name, s.name_zh as source_name_zh,
            s.country as source_country, s.source_type
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        JOIN sources s ON a.source_id = s.id
        WHERE a.id = ?
    """, (article_id,)).fetchone()

    if not row:
        conn.close()
        return {"error": "Article not found"}

    article = dict(row)

    # Get entities
    entities = conn.execute("""
        SELECT entity_name, entity_name_en, entity_type, entity_role, location_name
        FROM entities WHERE article_id = ?
    """, (article_id,)).fetchall()
    article['entities'] = [dict(e) for e in entities]

    # Get matched keywords
    keywords = conn.execute("""
        SELECT keyword, keyword_category
        FROM keywords_matched WHERE article_id = ?
    """, (article_id,)).fetchall()
    article['keywords'] = [dict(k) for k in keywords]

    conn.close()
    return article


@router.patch("/{article_id}/hide")
def hide_article(article_id: int):
    """Soft delete — hide article from dashboard without removing from database."""
    conn = get_db()
    conn.execute("UPDATE articles SET is_hidden = 1 WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()
    return {"status": "hidden", "article_id": article_id}


@router.patch("/{article_id}/signal")
def mark_as_signal(article_id: int):
    """Manually mark an article as an escalation signal."""
    conn = get_db()
    conn.execute("""
        UPDATE ai_analysis SET is_escalation_signal = 1
        WHERE article_id = ?
    """, (article_id,))
    conn.commit()
    conn.close()
    return {"status": "signalled", "article_id": article_id}