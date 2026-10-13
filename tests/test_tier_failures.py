"""Tier-1 / Tier-2 failure paths in scraper/processors/ai_pipeline.py.

What each guards (all seen in the prod pipeline log before 2026-10-13):
- a Tier-1 answer wrapped in a stray brace or a one-item list was
  tombstoned, so the article never reached the feed (57 articles);
- a Tier-2 review that answered NOT_RELEVANT with null fields crashed on
  the NOT NULL sentiment column, and the swallowed error left the Tier-1
  escalation flag looking review-clean, which the feed autopilot then
  publishes (36 reviews);
- batch answers were paired with articles by position, so one item
  missing mid-job would have shifted every later answer onto the wrong
  article.
"""
import json
import os
import sqlite3
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")

from scraper.processors import ai_pipeline as ap  # noqa: E402
from scraper.utils.llm import TIER1_MODEL, parse_llm_json, parse_llm_object  # noqa: E402

SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema.sql')

ANALYSIS_ROW = ("SELECT ai.sentiment, ai.sentiment_score, ai.urgency, ai.summary_en, "
                "ai.is_escalation_signal, ai.needs_human_review, ai.review_reason, "
                "ai.model_used, a.title_en, a.ai_processed "
                "FROM ai_analysis ai JOIN articles a ON a.id = ai.article_id WHERE a.id = ?")


# ── parsing ──────────────────────────────────────────────────────────────

def test_stray_closing_brace_after_the_object_is_recovered():
    # the exact shape of the 52 "Extra data" tombstones
    assert parse_llm_object('{"topic_primary": "MIL_EXERCISE", "confidence": 0.9}\n}') == \
        {"topic_primary": "MIL_EXERCISE", "confidence": 0.9}


def test_one_item_list_around_the_object_is_unwrapped():
    text = '[\n  {"is_cross_strait_primary": false, "topic_primary": "NOT_RELEVANT"}\n]'
    assert parse_llm_object(text)["topic_primary"] == "NOT_RELEVANT"


def test_fenced_object_still_parses():
    assert parse_llm_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_truncated_answer_still_raises():
    with pytest.raises(json.JSONDecodeError):
        parse_llm_object('{"title_en": "cut off mid-str')


@pytest.mark.parametrize("text", ['[{"a": 1}, {"a": 2}]', '"just a string"', '[]'])
def test_anything_but_one_object_raises_value_error(text):
    with pytest.raises(ValueError):
        parse_llm_object(text)


def test_sweep_parse_stays_strict():
    # The alt-model sweeps count parse errors as an outcome; the lenient
    # parse must not leak into them.
    with pytest.raises(json.JSONDecodeError):
        parse_llm_json('{"a": 1}\n}')
    with pytest.raises(json.JSONDecodeError):
        ap._parse_tier1_json('{"a": 1}\n}')


# ── DB + fake client ─────────────────────────────────────────────────────

class _Resp:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return _Resp(answer if isinstance(answer, str) else json.dumps(answer))


@pytest.fixture
def db(monkeypatch):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    with open(SCHEMA, encoding='utf-8') as f:
        conn.executescript(f.read())
    src = conn.execute(
        "INSERT INTO sources (name, url, source_type, place, language, bias) "
        "VALUES ('LTN', 'https://ltn.example', 'independent_media', 'TW', 'zh-tw', 'green')").lastrowid
    conn.commit()
    monkeypatch.setattr(ap, 'log_usage', lambda *a, **k: None)
    monkeypatch.setattr(ap.time, 'sleep', lambda s: None)

    def add_article(title='共軍演習'):
        aid = conn.execute(
            "INSERT INTO articles (source_id, url, title_original, content_original, language, "
            "published_at) VALUES (?, ?, ?, '中共解放軍今日在台灣周邊海域演習。', 'zh-tw', "
            "'2026-10-13T01:00:00')", (src, f"https://x.example/{title}", title)).lastrowid
        conn.commit()
        return {'id': aid, 'title_original': title,
                'content_original': '中共解放軍今日在台灣周邊海域演習。',
                'language': 'zh-tw', 'published_at': '2026-10-13T01:00:00',
                'source_name': 'LTN', 'source_place': None}

    def use_tier2(*answers):
        models = _FakeModels(answers)
        monkeypatch.setattr(ap, 'client', types.SimpleNamespace(models=models))
        return models

    return types.SimpleNamespace(conn=conn, add_article=add_article, use_tier2=use_tier2)


def _tier1(**over):
    base = {
        'is_cross_strait_primary': True, 'title_en': 'PLA drills', 'summary_en': 'PLA drills near Taiwan.',
        'topic_primary': 'MIL_EXERCISE', 'sentiment': 'hostile', 'sentiment_score': -0.7,
        'sentiment_reasoning': 'PLA drills directed at Taiwan are a hostile act.',
        'urgency': 'priority', 'is_escalation_signal': True, 'confidence': 0.9,
        'entities': [], 'keywords_matched': [], 'key_figure_statements': [],
        'military_exercises': [], 'polls': [], 'diplomacy_statements': [],
    }
    base.update(over)
    return base


# ── Tier 1 nulls ─────────────────────────────────────────────────────────

def test_null_fields_in_a_tier1_answer_take_the_defaults(db):
    models = db.use_tier2()       # no escalation → Tier 2 must not be called
    art = db.add_article()
    analysis = _tier1(title_en=None, summary_en=None, sentiment=None, sentiment_score=None,
                      urgency=None, confidence=None, is_escalation_signal=None,
                      entities=None, keywords_matched=None, key_figure_statements=None,
                      military_exercises=None, polls=None, diplomacy_statements=None)
    assert ap._apply_tier1_analysis(db.conn, art, analysis, {}) == 'ok'
    row = db.conn.execute(ANALYSIS_ROW, (art['id'],)).fetchone()
    assert (row['sentiment'], row['urgency'], row['summary_en']) == ('neutral', 'routine', '')
    assert row['title_en'] == art['title_original']
    assert row['ai_processed'] == 1
    assert models.calls == 0


# ── Tier 2 ───────────────────────────────────────────────────────────────

def test_tier2_not_relevant_with_nulls_holds_the_row_and_keeps_tier1_sentiment(db):
    db.use_tier2({'is_cross_strait_primary': False, 'topic_primary': 'NOT_RELEVANT',
                  'sentiment': None, 'sentiment_score': None, 'is_escalation_signal': None,
                  'confidence': 0.0})
    art = db.add_article()
    ap._apply_tier1_analysis(db.conn, art, _tier1(), {})
    row = db.conn.execute(ANALYSIS_ROW, (art['id'],)).fetchone()
    assert (row['sentiment'], row['sentiment_score']) == ('hostile', -0.7)
    assert row['needs_human_review'] == 1
    assert 'Flash=NOT_RELEVANT' in row['review_reason']
    assert 'Low confidence' not in row['review_reason']
    assert row['model_used'] == TIER1_MODEL


def test_a_failed_tier2_review_holds_the_row(db):
    db.use_tier2('this is not json')
    art = db.add_article()
    ap._apply_tier1_analysis(db.conn, art, _tier1(), {})
    row = db.conn.execute(ANALYSIS_ROW, (art['id'],)).fetchone()
    assert row['needs_human_review'] == 1
    assert row['review_reason'] == 'Tier 2 review failed: JSONDecodeError'
    assert (row['sentiment'], row['is_escalation_signal']) == ('hostile', 1)


def test_a_failed_tier2_review_keeps_the_tier1_reasons(db):
    db.use_tier2(ValueError('boom'))
    art = db.add_article()
    ap._apply_tier1_analysis(db.conn, art, _tier1(sentiment_score=-0.1), {})
    reason = db.conn.execute(ANALYSIS_ROW, (art['id'],)).fetchone()['review_reason']
    assert reason.startswith('label=hostile but score=-0.10')
    assert reason.endswith('Tier 2 review failed: ValueError')


def test_a_clean_tier2_review_clears_a_tier1_flag_it_fixed(db):
    # Tier 1: label hostile, score -0.10 → flagged. Tier 2 agrees on every
    # label and fixes the score, so nothing is left to review.
    db.use_tier2(_tier1(sentiment_score=-0.6))
    art = db.add_article()
    ap._apply_tier1_analysis(db.conn, art, _tier1(sentiment_score=-0.1), {})
    row = db.conn.execute(ANALYSIS_ROW, (art['id'],)).fetchone()
    assert row['sentiment_score'] == -0.6
    assert (row['needs_human_review'], row['review_reason']) == (0, None)
    assert row['model_used'].endswith('(review)')


def test_a_tier2_disagreement_still_flags(db):
    db.use_tier2(_tier1(sentiment='neutral', sentiment_score=0.0, sentiment_reasoning='',
                        is_escalation_signal=False))
    art = db.add_article()
    ap._apply_tier1_analysis(db.conn, art, _tier1(), {})
    row = db.conn.execute(ANALYSIS_ROW, (art['id'],)).fetchone()
    assert row['needs_human_review'] == 1
    assert 'Sentiment disagreement' in row['review_reason']
    assert 'Escalation disagreement' in row['review_reason']


def test_a_transient_tier2_error_is_retried_once(db):
    busy = Exception('503 UNAVAILABLE')
    busy.code = 503
    models = db.use_tier2(busy, _tier1(sentiment_score=-0.6))
    art = db.add_article()
    ap._apply_tier1_analysis(db.conn, art, _tier1(), {})
    row = db.conn.execute(ANALYSIS_ROW, (art['id'],)).fetchone()
    assert models.calls == 2
    assert row['model_used'].endswith('(review)')
    assert row['needs_human_review'] == 0


# ── batch pairing ────────────────────────────────────────────────────────

def _item(article_id=None, text='{}'):
    meta = {'article_id': str(article_id)} if article_id is not None else None
    return types.SimpleNamespace(metadata=meta, response=_Resp(text), error=None)


def test_tagged_answers_pair_by_article_id_whatever_their_order():
    responses = [_item(30), _item(10)]           # 20 missing, order shuffled
    pairs = ap._pair_batch_responses([10, 20, 30], responses)
    assert [(a, r.metadata['article_id']) for a, r in pairs] == [(10, '10'), (30, '30')]


def test_untagged_answers_pair_by_position_only_when_counts_agree():
    assert [a for a, _ in ap._pair_batch_responses([1, 2], [_item(), _item()])] == [1, 2]
    assert ap._pair_batch_responses([1, 2, 3], [_item(), _item()]) == []


def test_submission_tags_each_request_with_its_article_id(db, monkeypatch):
    art = db.add_article()

    class _KeepOpen:
        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def close(self):
            pass

    created = {}

    def create(model, src, config):
        created['src'] = src
        return types.SimpleNamespace(name='batches/test-job')

    monkeypatch.setattr(ap, 'get_connection', lambda: _KeepOpen(db.conn))
    monkeypatch.setattr(ap, 'client', types.SimpleNamespace(batches=types.SimpleNamespace(create=create)))
    assert ap.submit_tier1_batch(limit=10) == ['batches/test-job']
    assert [r['metadata'] for r in created['src']] == [{'article_id': str(art['id'])}]
