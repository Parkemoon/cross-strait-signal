"""api/routes/review.py — resolving a Tier-3 review flag.

Resolution and overrides are validated (any unknown resolution used to
publish the article), and a sentiment override has to leave a label and a
score that agree, because the card colour, the gauges and the trend read
the score."""
import contextlib
import os
import sqlite3
import sys
import types

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.routes import review  # noqa: E402
from api.routes.review import ReviewDecision, resolve_review  # noqa: E402

SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema.sql')


@pytest.fixture
def db(monkeypatch):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    with open(SCHEMA, encoding='utf-8') as f:
        conn.executescript(f.read())
    src = conn.execute(
        "INSERT INTO sources (name, url, source_type, place, language, bias) "
        "VALUES ('LTN', 'https://ltn.example', 'independent_media', 'TW', 'zh-tw', 'green')").lastrowid

    def add(sentiment, score):
        aid = conn.execute(
            "INSERT INTO articles (source_id, url, title_original, content_original, language, "
            "published_at, ai_processed, analyst_approved) VALUES (?, ?, 't', 'c', 'zh-tw', "
            "'2026-09-28T01:00:00', 1, 0)", (src, f"https://x.example/{sentiment}{score}")).lastrowid
        return conn.execute(
            "INSERT INTO ai_analysis (article_id, topic_primary, sentiment, sentiment_score, summary_en, "
            "needs_human_review, review_resolved) VALUES (?, 'DIP_STATEMENT', ?, ?, 's', 1, 0)",
            (aid, sentiment, score)).lastrowid

    conn.commit()

    @contextlib.contextmanager
    def fake_conn():
        yield conn

    monkeypatch.setattr(review, 'db_conn', fake_conn)
    return types.SimpleNamespace(conn=conn, add=add)


def _state(conn, analysis_id):
    return conn.execute(
        "SELECT ai.sentiment, ai.sentiment_score, ai.topic_primary, ai.review_resolved, "
        "a.analyst_approved, a.is_hidden FROM ai_analysis ai JOIN articles a ON a.id = ai.article_id "
        "WHERE ai.id = ?", (analysis_id,)).fetchone()


@pytest.mark.parametrize("body", [
    {"resolution": "dismiss"},
    {"resolution": "reject"},
    {"resolution": "overridden", "sentiment_override": "angry"},
    {"resolution": "overridden", "topic_override": "MIL_EXERCISES"},
    {"resolution": "overridden", "score_override": 1.5},
])
def test_invalid_decisions_are_rejected(body):
    with pytest.raises(ValidationError):
        ReviewDecision(**body)


def test_label_override_needs_a_matching_score(db):
    aid = db.add('hostile', -0.6)
    with pytest.raises(HTTPException) as e:
        resolve_review(aid, ReviewDecision(resolution="overridden", sentiment_override="cooperative"))
    assert e.value.status_code == 422
    row = _state(db.conn, aid)
    assert (row['sentiment'], row['review_resolved'], row['analyst_approved']) == ('hostile', 0, 0)


def test_label_and_score_override_together(db):
    aid = db.add('hostile', -0.6)
    resolve_review(aid, ReviewDecision(resolution="overridden", sentiment_override="cooperative",
                                       score_override=0.5, note="misread the framing"))
    row = _state(db.conn, aid)
    assert (row['sentiment'], row['sentiment_score'], row['review_resolved'], row['analyst_approved']) == \
        ('cooperative', 0.5, 1, 1)
    note = db.conn.execute("SELECT sentiment_override, score_override FROM analyst_notes").fetchone()
    assert tuple(note) == ('cooperative', 0.5)


def test_boundary_score_is_neutral(db):
    # bandColour draws +0.3 grey, so it can't back a cooperative label
    aid = db.add('neutral', 0.1)
    with pytest.raises(HTTPException):
        resolve_review(aid, ReviewDecision(resolution="overridden", sentiment_override="cooperative",
                                           score_override=0.3))


def test_topic_only_override_of_an_odd_model_pair_still_saves(db):
    # The model's own pair disagrees (often why it was flagged). The UI sends
    # the model's label back unchanged; only the topic moves.
    aid = db.add('hostile', -0.1)
    resolve_review(aid, ReviewDecision(resolution="overridden", sentiment_override="hostile",
                                       score_override=-0.1, topic_override="MIL_POLICY"))
    row = _state(db.conn, aid)
    assert (row['topic_primary'], row['sentiment'], row['analyst_approved']) == ('MIL_POLICY', 'hostile', 1)


def test_mixed_takes_any_score(db):
    aid = db.add('hostile', -0.6)
    resolve_review(aid, ReviewDecision(resolution="overridden", sentiment_override="mixed"))
    assert _state(db.conn, aid)['sentiment'] == 'mixed'


def test_dismiss_hides_and_does_not_approve(db):
    aid = db.add('neutral', 0.0)
    resolve_review(aid, ReviewDecision(resolution="dismissed"))
    row = _state(db.conn, aid)
    assert (row['is_hidden'], row['analyst_approved'], row['review_resolved']) == (1, 0, 1)


def test_topic_list_matches_the_tier1_enum():
    # Same Gemini SDK stub as test_validate_sentiment.py: the import only
    # needs a Client attribute to exist.
    _google = types.ModuleType("google")
    _genai = types.ModuleType("google.genai")
    _genai.Client = lambda **kwargs: None
    _google.genai = _genai
    sys.modules.setdefault("google", _google)
    sys.modules.setdefault("google.genai", _genai)
    os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")
    from scraper.processors.ai_pipeline import _TOPIC_ENUM
    assert list(review.TOPICS) == [t.strip() for t in _TOPIC_ENUM.split(",")]
