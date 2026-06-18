"""Lightweight per-call Gemini token-usage logger.

Appends one JSON line per Gemini API call so cost can be attributed by
pipeline stage (tier1 / tier2 / exercise_only / poll_only / social) and
turned into a real figure. Append-only JSONL — no DB table, no schema
migration, so it's safe to run directly on prod.

Path is set by the GEMINI_USAGE_LOG env var (default
/var/log/gemini-usage.jsonl). The logger swallows ALL errors and never
raises — instrumentation must never break the pipeline.

Aggregate with scripts/usage_report.py.
"""
import os
import json
from datetime import datetime, timezone

USAGE_LOG_PATH = os.environ.get("GEMINI_USAGE_LOG", "/var/log/gemini-usage.jsonl")


def log_usage(stage, model, response, article_id=None):
    """Record token usage for one generate_content call.

    `response` is the google-genai response object; its `usage_metadata`
    carries prompt / cached / thoughts (thinking) / candidates (output) /
    total token counts. Missing fields are stored as null."""
    try:
        um = getattr(response, "usage_metadata", None)
        if um is None:
            return
        rec = {
            "ts":         datetime.now(timezone.utc).isoformat(),
            "stage":      stage,
            "model":      model,
            "article_id": article_id,
            "prompt":     getattr(um, "prompt_token_count", None),
            "cached":     getattr(um, "cached_content_token_count", None),
            "thoughts":   getattr(um, "thoughts_token_count", None),
            "output":     getattr(um, "candidates_token_count", None),
            "total":      getattr(um, "total_token_count", None),
        }
        with open(USAGE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        # Instrumentation must never break the pipeline.
        pass
