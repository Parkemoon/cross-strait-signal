"""Shared Gemini client bootstrap + response parsing,
and the two model ids every Gemini call site uses.

The client construction (env check + genai.Client) was copied in five
places and the JSON response parsing in six, with two divergent
fence-stripping algorithms. One implementation of each now.
"""
import json
import os

# Every Gemini call takes its model from here, so a model change is one
# edit. TIER1_MODEL: Tier 1 and the cheap side passes (exercise, diplomacy,
# visits, social translation, name lookup). TIER2_MODEL: the Tier-2
# escalation review, the poll-only pass and the off-axis audit.
# tests/test_gemini_params.py fails on a literal model id anywhere else.
TIER1_MODEL = "gemini-3.1-flash-lite"
TIER2_MODEL = "gemini-3.8-flash"

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


def nullable(schema_type):
    """`{"anyOf": [{"type": T}, {"type": "null"}]}` — the nullable-field
    shape Gemini's response_json_schema accepts; shared by every
    side-extract schema so the spelling lives in one place."""
    return {"anyOf": [{"type": schema_type}, {"type": "null"}]}


def _strip_fences(text):
    """The model occasionally wraps output in ```json fences despite
    response_mime_type; drop them."""
    text = (text or '').strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1] if '\n' in text else ''
        text = text.rsplit('```', 1)[0].strip()
    return text


def parse_llm_json(text, envelope_key=None):
    """json.loads with the code-fence fallback every Gemini JSON-mode call
    needs. Raises json.JSONDecodeError on garbage — callers decide whether
    that tombstones, retries, or returns empty.

    With envelope_key, unwraps {"<key>": [...]} and tolerates the model
    returning the bare JSON array instead of the envelope (a known
    flash-lite quirk on the side-extract prompts)."""
    parsed = json.loads(_strip_fences(text))
    if envelope_key is None:
        return parsed
    if isinstance(parsed, list):
        return parsed
    return (parsed or {}).get(envelope_key, []) or []


def parse_llm_object(text):
    """parse_llm_json for an answer that must be ONE JSON object (the
    pipeline's Tier-1 and Tier-2 article analyses). Recovers the two
    wrappings flash-lite puts around a complete object, both seen on
    Tier-1 batch answers: a stray closing brace after it (json's "Extra
    data"; 52 articles were tombstoned for it, 2026-04 to 2026-10) and a
    one-item list around it (5, 2026-10-10 to 10-12). A truncated answer
    still raises json.JSONDecodeError, anything else that is not an object
    raises ValueError, so the caller's tombstone-or-retry choice holds.

    The alt-model sweeps keep the strict parse_llm_json: their
    parse_error counts are a measured outcome."""
    text = _strip_fences(text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        if e.msg != 'Extra data':
            raise
        parsed = json.JSONDecoder().raw_decode(text)[0]
    if isinstance(parsed, list) and len(parsed) == 1:
        parsed = parsed[0]
    if not isinstance(parsed, dict):
        raise ValueError(f"expected one JSON object, got {type(parsed).__name__}")
    return parsed
