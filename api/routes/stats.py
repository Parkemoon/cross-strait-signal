import json
import os

from fastapi import APIRouter, Query
from api.database import get_db

router = APIRouter(prefix="/api/stats", tags=["stats"])

_KEY_FIGURES_PATH = os.path.join(os.path.dirname(__file__), "../../scraper/processors/key_figures.json")
try:
    with open(_KEY_FIGURES_PATH, encoding="utf-8") as _f:
        _KEY_FIGURES = json.load(_f)
except Exception:
    _KEY_FIGURES = []


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


@router.get("/key-figures")
def key_figures():
    """Latest analyst-approved statement per curated key figure."""
    conn = get_db()

    rows = conn.execute("""
        SELECT kfs.figure_id, kfs.id AS statement_id,
               kfs.statement_text, kfs.statement_kind,
               a.id AS article_id, a.url AS article_url, a.published_at,
               s.name AS source_name, s.bias AS source_bias,
               ai.topic_primary
        FROM key_figure_statements kfs
        JOIN articles a ON kfs.article_id = a.id
        JOIN sources s ON s.id = a.source_id
        JOIN ai_analysis ai ON ai.article_id = a.id
        WHERE kfs.approval_status = 'approved'
        ORDER BY a.published_at DESC
    """).fetchall()

    conn.close()

    # Latest per figure (rows already ordered by published_at DESC)
    latest_by_figure = {}
    for row in rows:
        fid = row["figure_id"]
        if fid not in latest_by_figure:
            latest_by_figure[fid] = dict(row)

    results = []
    for figure in _KEY_FIGURES:
        fid = figure["id"]
        row = latest_by_figure.get(fid)
        latest = {
            "statement_id": row["statement_id"],
            "article_id": row["article_id"],
            "article_url": row["article_url"],
            "published_at": row["published_at"],
            "source_name": row["source_name"],
            "source_bias": row["source_bias"],
            "topic_primary": row["topic_primary"],
            "display_text": row["statement_text"],
            "display_kind": row["statement_kind"],
        } if row else None
        results.append({
            "id": fid,
            "name_en": figure["name_en"],
            "name_zh": figure["name_zh"],
            "role": figure["role"],
            "side": figure["side"],
            "party": figure.get("party"),
            "portrait": figure["portrait"],
            "attribution": figure.get("attribution"),
            "latest": latest,
        })

    return {"figures": results}


@router.get("/key-figures/candidates")
def key_figure_candidates():
    """Pending statements awaiting analyst approval, grouped by figure_id."""
    conn = get_db()

    rows = conn.execute("""
        SELECT kfs.id, kfs.figure_id, kfs.speaker_raw,
               kfs.statement_text, kfs.statement_zh,
               kfs.statement_kind, kfs.confidence, kfs.created_at,
               a.id AS article_id, a.url AS article_url, a.published_at,
               s.name AS source_name, s.bias AS source_bias
        FROM key_figure_statements kfs
        JOIN articles a ON kfs.article_id = a.id
        JOIN sources s ON s.id = a.source_id
        WHERE kfs.approval_status = 'pending'
        ORDER BY a.published_at DESC
    """).fetchall()

    conn.close()

    by_figure = {}
    for row in rows:
        fid = row["figure_id"]
        if fid not in by_figure:
            by_figure[fid] = []
        by_figure[fid].append(dict(row))

    return {"candidates": by_figure}


@router.post("/key-figures/statements/{statement_id}/approve")
def approve_statement(statement_id: int):
    """Mark a key figure statement as approved for display."""
    conn = get_db()
    conn.execute("""
        UPDATE key_figure_statements
        SET approval_status = 'approved', reviewed_at = datetime('now')
        WHERE id = ?
    """, (statement_id,))
    conn.commit()
    conn.close()
    return {"status": "approved", "id": statement_id}


@router.post("/key-figures/statements/{statement_id}/dismiss")
def dismiss_statement(statement_id: int):
    """Mark a key figure statement as dismissed."""
    conn = get_db()
    conn.execute("""
        UPDATE key_figure_statements
        SET approval_status = 'dismissed', reviewed_at = datetime('now')
        WHERE id = ?
    """, (statement_id,))
    conn.commit()
    conn.close()
    return {"status": "dismissed", "id": statement_id}