"""Unit tests for the directional keyword pre-filter.

This filter is the claim behind the ~80% AI-cost reduction — every false
positive sends a non-cross-strait article to Gemini, every false negative
drops a real signal. The directional logic is the load-bearing part.
"""
from scraper.processors.keyword_filter import check_relevance


def test_prc_source_mentioning_taiwan_is_relevant():
    is_relevant, _, kws = check_relevance(
        title="国台办回应赖清德言论",
        content="国台办发言人就民进党当局赖清德相关言论作出回应。",
        source_place="PRC",
    )
    assert is_relevant is True
    assert any("台湾" in k or "赖清德" in k or "民进党" in k for k in kws)


def test_prc_source_about_us_is_not_relevant_to_cross_strait():
    is_relevant, _, _ = check_relevance(
        title="美国就业数据公布",
        content="美国劳工部公布最新就业数据，市场反应平淡。",
        source_place="PRC",
    )
    assert is_relevant is False


def test_tw_source_mentioning_prc_is_relevant():
    is_relevant, _, kws = check_relevance(
        title="共軍在台海實彈演習",
        content="解放軍東部戰區於台海周邊舉行實彈演習。",
        source_place="TW",
    )
    assert is_relevant is True
    assert any(k in ("共軍", "解放軍", "東部戰區") for k in kws)


def test_tw_source_about_local_weather_is_not_relevant():
    is_relevant, _, _ = check_relevance(
        title="北部今日多雲",
        content="氣象局表示北部地區今日多雲偶陣雨。",
        source_place="TW",
    )
    assert is_relevant is False


def test_tw_source_mentioning_taiwan_only_is_not_relevant():
    """Critical: an article about Taiwan published BY Taiwan that doesn't
    mention the PRC/mainland should NOT pass the filter."""
    is_relevant, _, _ = check_relevance(
        title="立法院通過教育預算",
        content="立法院今日三讀通過明年度教育預算案。",
        source_place="TW",
    )
    assert is_relevant is False


def test_singapore_source_uses_prc_anchor_list():
    """SG sources (e.g. Zaobao) are treated like PRC for filter direction."""
    is_relevant, _, _ = check_relevance(
        title="兩岸關係趨緩",
        content="專家分析台海局勢近期出現緩和跡象。",
        source_place="SG",
    )
    assert is_relevant is True


def test_unknown_source_falls_back_to_both_directions():
    """Without source_place, the filter is more permissive."""
    is_relevant, _, _ = check_relevance(
        title="Cross-strait dialogue resumes",
        content="Officials from both sides of the strait met today.",
        source_place=None,
    )
    assert is_relevant is True


def test_only_title_and_first_2000_chars_are_checked():
    """The filter should NOT scan an article's tail; navigation cruft past
    char 2000 must not unstick irrelevant articles."""
    # Pad with irrelevant content, then drop "taiwan" past the 2000-char cutoff.
    padding = "weather report. " * 200  # ~3200 chars
    is_relevant, _, _ = check_relevance(
        title="local sports update",
        content=padding + " taiwan strait military exercise",
        source_place="PRC",
    )
    assert is_relevant is False
