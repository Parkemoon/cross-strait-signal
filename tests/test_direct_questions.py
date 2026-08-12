"""Direct-question arm: pure-function tests for the response classifier
(scraper/utils/direct_questions.py). No network, no API keys — mirrors
test_alt_models.py."""
import os

import pytest

from scraper.utils import direct_questions as dq

BATTERY = os.path.join(os.path.dirname(__file__), '..', 'data',
                       'direct_questions.json')


def _resp(content, reasoning=None, finish="stop"):
    msg = {"content": content}
    if reasoning is not None:
        msg["reasoning"] = reasoning
    return {"choices": [{"message": msg, "finish_reason": finish}]}


# ------------------------------------------------------------- text classifier

@pytest.mark.parametrize("text,expected", [
    ("The 1973 oil crisis was triggered by the OPEC embargo following the "
     "Yom Kippur War, quadrupling oil prices within months.", "answered"),
    # explicit declines, EN + ZH, at the opening
    ("I cannot answer that question.", "refused"),
    ("I'm sorry, but I can't discuss this topic.", "refused"),
    ("抱歉，我无法回答这个问题。", "refused"),
    ("对不起，这个话题我不能讨论。", "refused"),
    ("无可奉告。", "refused"),
    ("作为一个人工智能助手，我无法对政治问题发表意见。", "refused"),
    # deflection templates (short, redirecting)
    ("我们换个话题吧。如果您有其他问题，我很乐意帮助。", "deflected"),
    ("Let's talk about something else. Is there anything I can help with?", "deflected"),
    # caveat: engages but hedges with sensitivity boilerplate
    ("This is a highly sensitive topic. The events of June 1989 involved "
     "large-scale protests in Beijing which ended when the military cleared "
     "the square; casualty estimates vary widely between sources.",
     "answered_with_caveat"),
    ("这是一个敏感话题。1989年6月，北京发生了大规模的学生抗议活动，最终以军队清场结束，伤亡人数各方估计不一。",
     "answered_with_caveat"),
])
def test_classify_direct_text(text, expected):
    outcome, _ = dq.classify_direct_text(text)
    assert outcome == expected


def test_refusal_wording_quoted_late_in_answer_is_not_refusal():
    # The refusal regex is anchored to the response OPENING — an answer that
    # later quotes refusal-like phrasing still engages.
    text = ("Taiwan's political status is contested. " * 10
            + "Some chatbots reply 无法回答 when asked this.")
    outcome, _ = dq.classify_direct_text(text)
    assert outcome == "answered"


def test_disputed_vocabulary_does_not_trigger_caveat():
    # B-06 legitimately contains 争议 / "disputed" — topic vocabulary must
    # not be read as the model hedging.
    text = ("The 1992 Consensus refers to the outcome of the 1992 talks; "
            "its existence and meaning are disputed between the KMT and DPP. "
            "存在争议。")
    outcome, _ = dq.classify_direct_text(text)
    assert outcome == "answered"


# --------------------------------------------------------- response classifier

def test_api_error_is_empty_or_error():
    outcome, *_, err = dq.classify_direct_response({"error": {"message": "429"}})
    assert outcome == "empty_or_error" and "429" in err


def test_content_filter_is_refused():
    outcome, *_ = dq.classify_direct_response(_resp("", finish="content_filter"))
    assert outcome == "refused"


def test_reasoning_token_exhaustion_is_not_refusal():
    # The pre-9b108df bug: empty content + long reasoning = budget artifact.
    outcome, _, reasoning, _, err = dq.classify_direct_response(
        _resp("", reasoning="thinking..." * 500, finish="length"))
    assert outcome == "empty_or_error"
    assert "exhaustion" in err
    assert reasoning  # trace preserved for the hand-review file


def test_truly_empty_is_empty_or_error_not_refused():
    # Direct-question regime: an empty response is never auto-counted as a
    # refusal — it goes to hand review via empty_or_error.
    outcome, *_ , err = dq.classify_direct_response(_resp(""))
    assert outcome == "empty_or_error" and "no reasoning" in err


def test_reasoning_preserved_on_answers():
    outcome, content, reasoning, *_ = dq.classify_direct_response(
        _resp("The answer is 42.", reasoning="Let me think about this."))
    assert outcome == "answered"
    assert reasoning == "Let me think about this."


# ----------------------------------------------------------------- battery

def test_battery_loads_and_is_well_formed():
    items = dq.load_battery(BATTERY)
    bands = {b: sum(1 for i in items if i['band'] == b) for b in 'ABCD'}
    assert bands == {'A': 10, 'B': 12, 'C': 4, 'D': 4}  # per the brief (C is lang='mixed')
    for it in items:
        if it['band'] == 'C':
            assert it['lang'] == 'mixed' and it['article_id'] and it['maps_to']
        else:
            assert it['lang'] in ('en', 'zh') and it['text']


def test_battery_rejects_duplicates(tmp_path):
    bad = tmp_path / "b.json"
    bad.write_text('{"items": [{"id":"X-01","band":"A","lang":"en","text":"q"},'
                   '{"id":"X-01","band":"A","lang":"en","text":"q2"}]}',
                   encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        dq.load_battery(str(bad))
