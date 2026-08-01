"""Alt-model comparison experiment: pure-function tests for the OpenRouter
client (scraper/utils/openrouter.py). No network, no API keys."""
import json

import pytest

from scraper.utils import openrouter as orx


# ---------------------------------------------------------------- request body

def test_body_pins_providers_no_fallbacks():
    body = orx.build_request_body("deepseek/deepseek-v4-flash", "PROMPT", "neutral")
    assert body["provider"]["only"] == orx.ARMS["deepseek/deepseek-v4-flash"]["neutral"]
    assert body["provider"]["allow_fallbacks"] is False
    assert body["messages"] == [{"role": "user", "content": "PROMPT"}]
    assert body["temperature"] == 0.1
    assert body["max_tokens"] == 8000
    assert body["usage"] == {"include": True}


def test_body_reasoning_model_gets_bigger_token_budget():
    body = orx.build_request_body("moonshotai/kimi-k3", "PROMPT", "neutral")
    assert body["max_tokens"] == orx.MAX_TOKENS["moonshotai/kimi-k3"] == 24000


def test_body_data_collection_deny_neutral_only():
    neutral = orx.build_request_body("moonshotai/kimi-k3", "p", "neutral")
    originator = orx.build_request_body("moonshotai/kimi-k3", "p", "originator")
    assert neutral["provider"]["data_collection"] == "deny"
    assert "data_collection" not in originator["provider"]
    assert originator["provider"]["only"] == ["Moonshot AI"]


def test_body_unknown_arm_raises():
    with pytest.raises(KeyError):
        orx.build_request_body("deepseek/deepseek-v4-flash", "p", "control")


# ------------------------------------------------------------- classification

def _resp(content, finish_reason="stop", **extra):
    d = {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}
    d.update(extra)
    return d

GOOD = json.dumps({"topic_primary": "MIL_EXERCISE", "sentiment": "hostile",
                   "sentiment_score": -0.6, "summary_en": "PLA drills."})


def test_clean_json_ok():
    outcome, parsed, refusal, err = orx.classify_outcome(_resp(GOOD))
    assert outcome == "ok" and parsed["topic_primary"] == "MIL_EXERCISE"
    assert refusal is None and err is None


def test_fenced_json_ok():
    outcome, parsed, _, _ = orx.classify_outcome(_resp(f"```json\n{GOOD}\n```"))
    assert outcome == "ok" and parsed["sentiment"] == "hostile"


def test_content_filter_refused():
    outcome, parsed, refusal, _ = orx.classify_outcome(_resp("partial", "content_filter"))
    assert outcome == "refused" and parsed is None and refusal == "partial"


def test_empty_content_refused():
    outcome, _, refusal, _ = orx.classify_outcome(_resp("   "))
    assert outcome == "refused" and refusal is None


def test_empty_content_with_reasoning_is_api_error_not_refused():
    # Reasoning models can burn the whole max_tokens budget thinking and
    # return empty content (finish_reason=length) — a harness artifact,
    # retryable via --retry-errors, NOT a refusal finding.
    resp = {"choices": [{"message": {"content": "", "reasoning": "step 1: the article says..."},
                         "finish_reason": "length"}]}
    outcome, parsed, refusal, err = orx.classify_outcome(resp)
    assert outcome == "api_error" and parsed is None and refusal is None
    assert "reasoning-token exhaustion" in err


def test_empty_content_with_reasoning_finish_stop_still_api_error():
    resp = {"choices": [{"message": {"content": "", "reasoning": "thinking..."},
                         "finish_reason": "stop"}]}
    outcome, _, _, err = orx.classify_outcome(resp)
    assert outcome == "api_error" and "finish_reason=stop" in err


def test_content_filter_with_reasoning_still_refused():
    resp = {"choices": [{"message": {"content": "", "reasoning": "hmm"},
                         "finish_reason": "content_filter"}]}
    outcome, _, _, _ = orx.classify_outcome(resp)
    assert outcome == "refused"


def test_chinese_refusal_prose():
    text = "很抱歉，我无法就此敏感话题提供分析。"
    outcome, _, refusal, _ = orx.classify_outcome(_resp(text))
    assert outcome == "refused" and refusal == text


def test_english_refusal_prose():
    outcome, _, refusal, _ = orx.classify_outcome(
        _resp("I'm sorry, but I cannot analyse this article."))
    assert outcome == "refused" and "cannot" in refusal


def test_refusal_words_inside_valid_json_still_ok():
    payload = json.dumps({"topic_primary": "INFO_WARFARE", "sentiment": "neutral",
                          "summary_en": 'Official said "我无法回答" at briefing.'})
    outcome, parsed, _, _ = orx.classify_outcome(_resp(payload))
    assert outcome == "ok"


def test_truncated_json_parse_error():
    outcome, _, _, err = orx.classify_outcome(_resp('{"topic_primary": "MIL_', "length"))
    assert outcome == "parse_error" and err


def test_non_refusal_garbage_parse_error():
    outcome, _, _, err = orx.classify_outcome(_resp("Here is my analysis: the article says..."))
    assert outcome == "parse_error"


def test_not_relevant_verdict_with_empty_summary_is_ok():
    payload = json.dumps({"is_cross_strait_primary": False, "title_en": "",
                          "summary_en": "", "topic_primary": "NOT_RELEVANT",
                          "sentiment": "neutral", "sentiment_score": 0.0})
    outcome, parsed, _, _ = orx.classify_outcome(_resp(payload))
    assert outcome == "ok" and parsed["topic_primary"] == "NOT_RELEVANT"


def test_missing_required_keys_parse_error():
    outcome, _, _, err = orx.classify_outcome(
        _resp(json.dumps({"sentiment": "neutral", "summary_en": "x"})))
    assert outcome == "parse_error" and "topic_primary" in err


def test_top_level_error_api_error():
    outcome, _, _, err = orx.classify_outcome(
        {"error": {"message": "No allowed providers", "code": 404}})
    assert outcome == "api_error" and "No allowed providers" in err


def test_no_choices_api_error():
    outcome, _, _, err = orx.classify_outcome({"choices": []})
    assert outcome == "api_error"


# ------------------------------------------------------------------ usage log

def test_usage_adapter_maps_openai_shape(tmp_path, monkeypatch):
    log = tmp_path / "usage.jsonl"
    monkeypatch.setattr(orx, "USAGE_LOG_PATH", str(log))
    orx.log_openrouter_usage("alt_tier1", "deepseek/deepseek-v4-flash",
                             {"usage": {"prompt_tokens": 9000, "completion_tokens": 800,
                                        "total_tokens": 9800}},
                             article_id=42)
    rec = json.loads(log.read_text().strip())
    assert rec["stage"] == "alt_tier1"
    assert rec["prompt"] == 9000 and rec["output"] == 800 and rec["total"] == 9800
    assert rec["article_id"] == 42 and rec["cached"] is None


def test_usage_adapter_no_usage_writes_nothing(tmp_path, monkeypatch):
    log = tmp_path / "usage.jsonl"
    monkeypatch.setattr(orx, "USAGE_LOG_PATH", str(log))
    orx.log_openrouter_usage("alt_tier1", "m", {"error": {"message": "x"}})
    assert not log.exists()
