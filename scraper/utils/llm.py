"""Shared Gemini client bootstrap + response parsing (CODE_REVIEW_2026-07-03 §4.9).

The client construction (env check + genai.Client) was copied in five
places and the JSON response parsing in six, with two divergent
fence-stripping algorithms. One implementation of each now.
"""
import json
import os

_client = None


def get_gemini_client():
    """Module-singleton google.genai Client. Raises with the standard hint
    when GEMINI_API_KEY is missing (callers import at module level, so a
    missing key still fails fast at import time like it always did)."""
    global _client
    if _client is None:
        from google import genai
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is not set. "
                "Add it to .env in the project root (see CLAUDE.md > Environment)."
            )
        _client = genai.Client(api_key=key)
    return _client


def parse_llm_json(text, envelope_key=None):
    """json.loads with the code-fence fallback every Gemini JSON-mode call
    needs (the model occasionally wraps output in ```json fences despite
    response_mime_type). Raises json.JSONDecodeError on garbage — callers
    decide whether that tombstones, retries, or returns empty.

    With envelope_key, unwraps {"<key>": [...]} and tolerates the model
    returning the bare JSON array instead of the envelope (a known
    flash-lite quirk on the side-extract prompts)."""
    text = (text or '').strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1] if '\n' in text else ''
        text = text.rsplit('```', 1)[0].strip()
    parsed = json.loads(text)
    if envelope_key is None:
        return parsed
    if isinstance(parsed, list):
        return parsed
    return (parsed or {}).get(envelope_key, []) or []
