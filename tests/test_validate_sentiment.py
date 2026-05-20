"""Unit tests for the sentiment consistency validator.

_validate_sentiment is called after every Tier 1 and Tier 2 extraction and
routes mismatches into the human review queue. Regressions here would silently
let inconsistent AI output slip through to the public feed.
"""
import sys
import types

# The ai_pipeline module imports the Gemini SDK and reads GEMINI_API_KEY at
# import time. We're only testing one pure function from it, so stub the
# SDK + key before import.
_google = types.ModuleType("google")
_genai = types.ModuleType("google.genai")
_genai.Client = lambda **kwargs: None  # _validate_sentiment never touches the client
_google.genai = _genai
sys.modules.setdefault("google", _google)
sys.modules.setdefault("google.genai", _genai)

import os
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")

from scraper.processors.ai_pipeline import _validate_sentiment  # noqa: E402


def test_hostile_with_strong_negative_score_is_consistent():
    assert _validate_sentiment("hostile", -0.7, "PRC framed Taiwan hostilely.") == []


def test_hostile_with_neutral_score_is_flagged():
    problems = _validate_sentiment("hostile", -0.1, "reason text")
    assert len(problems) == 1
    assert "label=hostile" in problems[0]


def test_hostile_with_positive_score_is_flagged():
    problems = _validate_sentiment("hostile", 0.4, "reason text")
    assert len(problems) == 1


def test_cooperative_with_strong_positive_score_is_consistent():
    assert _validate_sentiment("cooperative", 0.6, "Ma framed PRC positively.") == []


def test_cooperative_with_neutral_score_is_flagged():
    problems = _validate_sentiment("cooperative", 0.1, "reason text")
    assert len(problems) == 1
    assert "label=cooperative" in problems[0]


def test_neutral_within_band_is_consistent():
    assert _validate_sentiment("neutral", 0.0, "") == []
    assert _validate_sentiment("neutral", 0.2, "") == []
    assert _validate_sentiment("neutral", -0.25, "") == []


def test_neutral_outside_band_is_flagged():
    problems = _validate_sentiment("neutral", -0.5, "")
    assert len(problems) == 1
    assert "label=neutral" in problems[0]


def test_directional_label_requires_reasoning():
    """Hostile/cooperative labels with empty reasoning is the second flag path."""
    problems = _validate_sentiment("hostile", -0.7, "")
    assert any("sentiment_reasoning is empty" in p for p in problems)


def test_directional_label_with_whitespace_only_reasoning_is_flagged():
    problems = _validate_sentiment("cooperative", 0.5, "   ")
    assert any("sentiment_reasoning is empty" in p for p in problems)


def test_neutral_with_empty_reasoning_is_not_flagged():
    """Neutral sentiment legitimately has empty reasoning (no framing to explain)."""
    assert _validate_sentiment("neutral", 0.1, "") == []


def test_mixed_label_does_not_trigger_band_check():
    """Mixed is allowed to have any score — no band assertion fires."""
    assert _validate_sentiment("mixed", -0.5, "both sides") == []
    assert _validate_sentiment("mixed", 0.5, "both sides") == []
