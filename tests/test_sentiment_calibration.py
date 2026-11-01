"""Tests for shared/sentiment_calibration.py and pipeline/override integration."""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.routes.review import _score_problem  # noqa: E402
from shared.sentiment_band import sentiment_band  # noqa: E402
from shared.sentiment_calibration import (  # noqa: E402
    calibrate_sentiment_score,
    clamp_to_band,
    lookup_source_topic_baseline,
    raw_fits_band,
    refresh_article_sentiment_excess,
)

SCHEMA = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")


def test_calibrated_scores_always_satisfy_band_and_review_checks():
    cases = [
        ("hostile", -0.4, 0.9),
        ("hostile", -0.9, -1.0),
        ("cooperative", 0.4, -0.9),
        ("cooperative", 0.9, 1.0),
        ("neutral", 0.0, 0.9),
        ("neutral", -0.2, -0.9),
        ("mixed", -0.5, 0.4),
    ]
    for label, raw, cont in cases:
        res = calibrate_sentiment_score(
            raw_score=raw,
            sentiment_label=label,
            source_name="LTN Cross-Strait",
            source_bias="green",
            topic_primary="MIL_EXERCISE",
            continuous_pred=cont,
        )
        assert res is not None
        assert _score_problem(label, res.sentiment_score) is None
        if label in ("hostile", "cooperative", "neutral"):
            assert sentiment_band(res.sentiment_score) == label
        assert res.sentiment_score_raw == round(raw, 2)
        assert res.sentiment_excess == round(
            res.sentiment_score - res.sentiment_baseline, 3
        )


def test_out_of_band_raw_llm_score_is_left_unclamped_for_review_flag():
    assert not raw_fits_band(-0.1, "hostile")
    res = calibrate_sentiment_score(
        raw_score=-0.1,
        sentiment_label="hostile",
        source_name="LTN Cross-Strait",
        source_bias="green",
        topic_primary="MIL_EXERCISE",
        continuous_pred=-0.8,
    )
    assert res.sentiment_score == -0.1
    assert _score_problem("hostile", res.sentiment_score) is not None


def test_source_topic_baseline_reflects_structural_stance():
    # Xinhua on UNITED_FRONT_INTEG should have a positive baseline;
    # LTN on MIL_EXERCISE should have a negative baseline.
    b_xh = lookup_source_topic_baseline(
        "Xinhua Cross-Strait", "UNITED_FRONT_INTEG", "state_official"
    )
    b_ltn = lookup_source_topic_baseline(
        "LTN Politics", "MIL_EXERCISE", "green"
    )
    assert b_xh > 0.2
    assert b_ltn < -0.2
    assert clamp_to_band(-0.31, "hostile") <= -0.32


def test_refresh_article_sentiment_excess_after_override():
    conn = sqlite3.connect(":memory:")
    with open(SCHEMA, encoding="utf-8") as f:
        conn.executescript(f.read())
    src_id = conn.execute(
        "INSERT INTO sources (name, url, source_type, place, language, bias) "
        "VALUES ('LTN Politics', 'https://ltn.example', 'independent_media', 'TW', 'zh-tw', 'green')"
    ).lastrowid
    art_id = conn.execute(
        "INSERT INTO articles (source_id, url, title_original, content_original, language) "
        "VALUES (?, 'https://ltn.example/1', '測試', '內文', 'zh-tw')",
        (src_id,),
    ).lastrowid
    conn.execute(
        "INSERT INTO ai_analysis (article_id, topic_primary, sentiment, sentiment_score, "
        "sentiment_score_raw, summary_en) VALUES (?, 'MIL_EXERCISE', 'hostile', -0.75, -0.7, 'Test.')",
        (art_id,),
    )
    refresh_article_sentiment_excess(conn, art_id)
    row = conn.execute(
        "SELECT sentiment_baseline, sentiment_excess FROM ai_analysis WHERE article_id = ?",
        (art_id,),
    ).fetchone()
    assert row[0] is not None
    assert row[1] == round(-0.75 - row[0], 3)
