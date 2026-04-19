import math
from fastapi import APIRouter, Query
from typing import Optional
from pydantic import BaseModel
from api.database import get_db


def _sanitize_floats(d: dict) -> dict:
    """Replace inf/nan float values with None so they serialise as JSON null."""
    for key, val in d.items():
        if isinstance(val, float) and not math.isfinite(val):
            d[key] = None
    return d

router = APIRouter(prefix="/api/articles", tags=["articles"])


class TranslationUpdate(BaseModel):
    title_en_override: Optional[str] = None
    summary_en_override: Optional[str] = None
    key_quote_override: Optional[str] = None


class EntityNameUpdate(BaseModel):
    entity_name_en: str


@router.get("/")
def list_articles(
    entity: Optional[str] = Query(None, description="Filter by entity name"),
    topic: Optional[str] = Query(None, description="Filter by topic code, e.g. MIL_EXERCISE"),
    sentiment: Optional[str] = Query(None, description="hostile, cooperative, neutral, mixed"),
    source_place: Optional[str] = Query(None, description="PRC or TW"),
    source_name: Optional[str] = Query(None, description="Filter by source name prefix, e.g. LTN"),
    bias: Optional[str] = Query(None, description="Filter by source bias, e.g. green, blue"),
    urgency: Optional[str] = Query(None, description="flash, priority, routine"),
    escalation_only: bool = Query(False, description="Only show escalation signals"),
    search: Optional[str] = Query(None, description="Search in titles and content"),
    include_pending: bool = Query(False, description="Admin: include unapproved articles"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """List articles with their AI analysis. Supports filtering and search."""
    conn = get_db()

    # Build the query dynamically based on filters
    where_clauses = []
    params = []

    # Always exclude hidden articles and articles pending AI review
    where_clauses.append("a.is_hidden = 0")
    where_clauses.append("(ai.needs_human_review = 0 OR ai.review_resolved = 1)")
    # Public feed requires analyst approval; admin passes include_pending=true to see all
    if not include_pending:
        where_clauses.append("a.analyst_approved = 1")

    if entity:
        where_clauses.append("EXISTS (SELECT 1 FROM entities e WHERE e.article_id = a.id AND (e.entity_name_en LIKE ? OR e.entity_name LIKE ?))")
        params.extend([f"%{entity}%", f"%{entity}%"])

    if topic:
        where_clauses.append("ai.topic_primary = ?")
        params.append(topic)

    if sentiment:
        where_clauses.append("ai.sentiment = ?")
        params.append(sentiment)

    if source_place:
        if source_place == "intl":
            where_clauses.append("s.place NOT IN ('PRC', 'TW', 'HK', 'MO')")
        elif source_place == "hk":
            where_clauses.append("s.place IN ('HK', 'MO')")
        else:
            where_clauses.append("s.place = ?")
            params.append(source_place)

    if source_name:
        where_clauses.append("s.name LIKE ?")
        params.append(f"{source_name}%")

    if bias:
        where_clauses.append("s.bias = ?")
        params.append(bias)

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
            a.title_en_override,
            a.language,
            a.published_at,
            a.content_original,
            a.analyst_approved,
            ai.topic_primary,
            ai.topic_secondary,
            ai.sentiment,
            ai.sentiment_score,
            ai.urgency,
            ai.summary_en,
            a.summary_en_override,
            ai.key_quote,
            ai.key_quote_en,
            a.key_quote_override,
            ai.is_new_formulation,
            ai.is_escalation_signal,
            ai.escalation_note,
            ai.confidence,
            a.event_cluster_id,
            a.cluster_size,
            s.name as source_name,
            s.name_zh as source_name_zh,
            s.place as source_place,
            s.source_type,
            s.bias
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        JOIN sources s ON a.source_id = s.id
        {where_sql}
        ORDER BY {"a.analyst_approved ASC, " if include_pending else ""}a.published_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([page_size, offset])
    rows = conn.execute(query_sql, params).fetchall()

    # Convert to list of dicts
    articles = []
    for row in rows:
        article = _sanitize_floats(dict(row))

        # Get entities for this article
        entities = conn.execute("""
            SELECT id, entity_name, entity_name_en, entity_type, entity_role, location_name
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
            s.name as source_name, s.place as source_place, s.bias
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
            s.place as source_place, s.source_type
        FROM articles a
        JOIN ai_analysis ai ON a.id = ai.article_id
        JOIN sources s ON a.source_id = s.id
        WHERE a.id = ?
    """, (article_id,)).fetchone()

    if not row:
        conn.close()
        return {"error": "Article not found"}

    article = _sanitize_floats(dict(row))

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


@router.post("/{article_id}/hide")
def hide_article(article_id: int):
    conn = get_db()
    conn.execute(
        "UPDATE articles SET is_hidden = 1 WHERE id = ?",
        (article_id,)
    )
    # Also clear escalation signal so it's removed from Priority Signals
    conn.execute(
        "UPDATE ai_analysis SET is_escalation_signal = 0 WHERE article_id = ?",
        (article_id,)
    )
    conn.commit()
    conn.close()
    return {"status": "hidden"}


@router.post("/{article_id}/approve")
def approve_article(article_id: int):
    """Mark an article as analyst-approved, making it visible on the public feed."""
    conn = get_db()
    conn.execute("UPDATE articles SET analyst_approved = 1 WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()
    return {"status": "approved", "article_id": article_id}


@router.patch("/{article_id}/translation")
def update_article_translation(article_id: int, body: TranslationUpdate):
    """Override AI-generated headline, summary, and/or key quote translation."""
    conn = get_db()
    updates = {}
    if body.title_en_override is not None:
        updates["title_en_override"] = body.title_en_override
    if body.summary_en_override is not None:
        updates["summary_en_override"] = body.summary_en_override
    if body.key_quote_override is not None:
        updates["key_quote_override"] = body.key_quote_override
    if updates:
        set_clause = ", ".join(f"{col} = ?" for col in updates)
        conn.execute(
            f"UPDATE articles SET {set_clause} WHERE id = ?",
            (*updates.values(), article_id)
        )
        conn.commit()
    conn.close()
    return {"status": "updated", "article_id": article_id, "fields": list(updates.keys())}


@router.patch("/{article_id}/entities/{entity_id}")
def update_entity_name(article_id: int, entity_id: int, body: EntityNameUpdate):
    """Correct the English name of an extracted entity."""
    conn = get_db()
    conn.execute(
        "UPDATE entities SET entity_name_en = ? WHERE id = ? AND article_id = ?",
        (body.entity_name_en.strip(), entity_id, article_id)
    )
    conn.commit()
    conn.close()
    return {"status": "updated", "entity_id": entity_id, "entity_name_en": body.entity_name_en.strip()}


@router.patch("/{article_id}/signal")
def toggle_signal(article_id: int):
    """Toggle escalation signal flag on an article."""
    conn = get_db()
    row = conn.execute(
        "SELECT is_escalation_signal FROM ai_analysis WHERE article_id = ?",
        (article_id,)
    ).fetchone()
    new_value = 0 if (row and row["is_escalation_signal"]) else 1
    conn.execute(
        "UPDATE ai_analysis SET is_escalation_signal = ? WHERE article_id = ?",
        (new_value, article_id)
    )
    conn.commit()
    conn.close()
    return {"is_escalation_signal": new_value, "article_id": article_id}