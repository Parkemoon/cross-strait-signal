"""Alt-model comparison experiment (Chinese LLMs) — admin-only reads.

Serves alt_model_analysis rows written by scripts/sweep_alt_models.py.
Everything here is require_admin (raising): there is no public subset of
this feature, and the public build never calls it. NOT an editorial
queue — read-only presentation of experiment results; refusals are
findings ('refused' outcome), never errors.
"""
from fastapi import APIRouter, Depends

from api.auth import require_admin
from api.database import db_conn

router = APIRouter(prefix="/api/alt-models", tags=["alt-models"])

# NOTE: connections are opened with `with db_conn()` INSIDE each endpoint —
# the canonical pattern (see .claude/rules/database.md). A Depends()-injected
# sqlite connection is a thread bug: FastAPI may run the dependency generator
# and the endpoint on different threadpool threads, and sqlite3's
# check_same_thread then 500s intermittently (bit us in prod 2026-08-07).


_ROW_FIELDS = """id, article_id, model, arm, outcome, topic_primary, topic_secondary,
    sentiment, sentiment_score, sentiment_reasoning, urgency, summary_en,
    is_escalation_signal, finish_reason, refusal_text, error_text,
    provider_used, total_tokens, latency_ms, created_at"""


@router.get("/article/{article_id}", dependencies=[Depends(require_admin)])
def article_alt_analyses(article_id: int):
    """All alt-model rows for one article (raw_response deliberately
    excluded — it is large; inspect via sqlite3 if needed)."""
    with db_conn() as conn:
        rows = conn.execute(
            f"SELECT {_ROW_FIELDS} FROM alt_model_analysis WHERE article_id = ? "
            "ORDER BY model, arm", (article_id,)).fetchall()
        return {"article_id": article_id, "rows": [dict(r) for r in rows]}


@router.get("/summary", dependencies=[Depends(require_admin)])
def summary():
    """Per-(model, arm) aggregates vs the stored production analysis.
    topic_agreement/score_delta are over 'ok' rows only; sanitised-but-
    answered output shows up here, not in the outcome counts."""
    with db_conn() as conn:
        return _summary_body(conn)


def _summary_body(conn):
    out = []
    for g in conn.execute(
            """SELECT model, arm, COUNT(*) total,
                  SUM(outcome = 'ok') ok,
                  SUM(outcome = 'refused') refused,
                  SUM(outcome = 'parse_error') parse_error,
                  SUM(outcome = 'api_error') api_error
               FROM alt_model_analysis GROUP BY model, arm
               ORDER BY model, arm"""):
        agg = conn.execute(
            """SELECT AVG(x.topic_primary = ai.topic_primary) topic_agree,
                      AVG(ABS(COALESCE(x.sentiment_score, 0) - COALESCE(ai.sentiment_score, 0))) score_delta,
                      AVG(COALESCE(x.sentiment_score, 0) - COALESCE(ai.sentiment_score, 0)) score_bias
               FROM alt_model_analysis x
               JOIN ai_analysis ai ON ai.article_id = x.article_id
               WHERE x.model = ? AND x.arm = ? AND x.outcome = 'ok'""",
            (g["model"], g["arm"])).fetchone()
        refusals_by_topic = {
            r["topic_primary"]: r["n"] for r in conn.execute(
                """SELECT ai.topic_primary, COUNT(*) n
                   FROM alt_model_analysis x
                   JOIN ai_analysis ai ON ai.article_id = x.article_id
                   WHERE x.model = ? AND x.arm = ? AND x.outcome = 'refused'
                   GROUP BY ai.topic_primary ORDER BY n DESC""",
                (g["model"], g["arm"]))}
        out.append({
            "model": g["model"], "arm": g["arm"], "total": g["total"],
            "by_outcome": {"ok": g["ok"], "refused": g["refused"],
                           "parse_error": g["parse_error"], "api_error": g["api_error"]},
            "topic_agreement": agg["topic_agree"],
            "mean_abs_score_delta": agg["score_delta"],
            "mean_score_bias": agg["score_bias"],
            "refusals_by_topic": refusals_by_topic,
        })
    return {"groups": out}


@router.get("/refusals", dependencies=[Depends(require_admin)])
def refusals(model: str = None, arm: str = None, limit: int = 50):
    """Browse refused rows with article context — what gets censored."""
    limit = max(1, min(limit, 200))
    where, params = ["x.outcome = 'refused'"], []
    if model:
        where.append("x.model = ?")
        params.append(model)
    if arm:
        where.append("x.arm = ?")
        params.append(arm)
    with db_conn() as conn:
        rows = conn.execute(
            f"""SELECT x.id, x.article_id, x.model, x.arm, x.finish_reason,
                   x.refusal_text, x.created_at,
                   a.title_en, a.title_original, s.name AS source_name,
                   ai.topic_primary, ai.sentiment_score AS gemini_score
                FROM alt_model_analysis x
                JOIN articles a ON a.id = x.article_id
                JOIN sources s ON s.id = a.source_id
                JOIN ai_analysis ai ON ai.article_id = x.article_id
                WHERE {' AND '.join(where)}
                ORDER BY x.created_at DESC LIMIT ?""",
            params + [limit]).fetchall()
        return {"rows": [dict(r) for r in rows]}
