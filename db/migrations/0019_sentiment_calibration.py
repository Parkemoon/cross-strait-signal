"""Add sentiment calibration columns to ai_analysis:
- sentiment_score_raw: original uncalibrated LLM float score (preserved permanently)
- sentiment_baseline: Empirical-Bayes expected score for (source, topic_primary)
- sentiment_excess: residual tone deviation (sentiment_score - sentiment_baseline)
"""

_ALTERS = [
    "ALTER TABLE ai_analysis ADD COLUMN sentiment_score_raw REAL",
    "ALTER TABLE ai_analysis ADD COLUMN sentiment_baseline REAL",
    "ALTER TABLE ai_analysis ADD COLUMN sentiment_excess REAL",
]


def migrate(conn):
    import sqlite3

    for stmt in _ALTERS:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
