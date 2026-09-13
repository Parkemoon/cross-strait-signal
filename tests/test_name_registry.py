# -*- coding: utf-8 -*-
"""Name registry (shared/name_registry.py, shared/romanisation.py,
scraper/processors/name_lookup.py decision logic) and the poll intensity
collapse that replaced the prompt's arithmetic (audit 2026-09-13)."""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")

from shared import name_registry as nr  # noqa: E402
from shared.romanisation import hanyu_markers, side_from_role, to_wade_giles  # noqa: E402

MIGRATION = os.path.join(os.path.dirname(__file__), '..', 'db', 'migrations', '0014_name_registry.sql')


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    with open(MIGRATION, encoding='utf-8') as f:
        c.executescript(f.read())
    return c


# ── romanisation heuristics ──────────────────────────────────────────────

def test_side_from_role():
    assert side_from_role('KMT legislator') == 'TW'
    assert side_from_role('Taiwan Affairs Office spokesperson') == 'PRC'
    assert side_from_role('PRC Ministry of National Defense spokesperson') is None   # both sides match → ambiguous
    assert side_from_role('') is None


def test_hanyu_markers():
    assert hanyu_markers('Zheng Zhaoxin') == ['q/x/zh initial', 'unhyphenated given name']
    assert hanyu_markers('Xu Chun-ying') == ['q/x/zh initial']          # hybrid
    assert hanyu_markers('Cheng Chao-hsin') == []
    assert hanyu_markers('Wellington Koo') == []
    assert hanyu_markers('Han Kuo-yu') == []


def test_to_wade_giles():
    pytest.importorskip('pypinyin')
    assert to_wade_giles('鄭照新') == 'Cheng Chao-hsin'
    assert to_wade_giles('周永鴻') == 'Chou Yung-hung'
    assert to_wade_giles('吳思瑤') == 'Wu Szu-yao'
    assert to_wade_giles('Zheng') is None


# ── registry store ───────────────────────────────────────────────────────

def test_upsert_folds_simplified_and_never_overwrites_approved(conn):
    pytest.importorskip('zhconv')
    rid = nr.upsert(conn, '张钧凯', 'Chang Chun-kai', 'TW', 'wikidata', 'approved')
    row = conn.execute("SELECT * FROM name_registry WHERE id = ?", (rid,)).fetchone()
    assert row['zh_trad'] == '張鈞凱' and row['zh_simp'] == '张钧凯'
    assert nr.load_approved(conn) == {'張鈞凱': 'Chang Chun-kai', '张钧凯': 'Chang Chun-kai'}
    # a later worker pass cannot downgrade an approved row
    assert nr.upsert(conn, '張鈞凱', 'Zhang Junkai', 'TW', 'generated', 'pending') == rid
    assert conn.execute("SELECT en, status FROM name_registry WHERE id = ?", (rid,)).fetchone()[:] == ('Chang Chun-kai', 'approved')
    # but a pending row is updated in place
    pid = nr.upsert(conn, '李其澤', None, 'TW', 'generated', 'pending')
    assert nr.upsert(conn, '李其澤', 'Li Chi-tse', 'TW', 'wikidata', 'approved') == pid
    assert nr.load_approved(conn)['李其澤'] == 'Li Chi-tse'


def test_merge_precedence():
    canon = {'canonical': {'翁曉玲': 'Weng Hsiao-ling', '賴清德': 'Lai Ching-te'}, 'title_tokens': [], 'fold_prefixes': []}
    merged = nr.merge_canon(canon, {'翁曉玲': 'Weng Hsiao-Ling', '鄭照新': 'Cheng Chao-hsin'})
    assert merged['canonical']['翁曉玲'] == 'Weng Hsiao-Ling'     # registry (the analyst's later call) wins
    assert merged['canonical']['賴清德'] == 'Lai Ching-te'
    assert canon['canonical']['翁曉玲'] == 'Weng Hsiao-ling'       # the JSON structure is not mutated
    assert nr.merge_glossary({'a': '1'}, {'b': '2'}) == {'a': '1', 'b': '2'}


# ── text rewrite ─────────────────────────────────────────────────────────

def test_rewrite_renderings_is_whole_word_and_longest_first():
    text = "Zheng Zhaoxin met Wang Hung-wei; Zhengzhou is a city. Wang Hung-wei-style."
    out = nr.rewrite_renderings(text, [('Zheng Zhaoxin', 'Cheng Chao-hsin'), ('Wang Hung-wei', 'Wang Hong-wei')])
    assert out == "Cheng Chao-hsin met Wang Hong-wei; Zhengzhou is a city. Wang Hung-wei-style."
    assert nr.rewrite_renderings("Wu", [('Wu', 'Wu Cheng')]) == "Wu"            # too short to touch
    assert nr.rewrite_renderings(None, [('a', 'b')]) is None


def test_apply_to_analysis_rewrites_entities_and_text():
    canon = {'鄭照新': 'Cheng Chao-hsin'}
    analysis = {
        'title_en': 'Zheng Zhaoxin defends budget',
        'summary_en': 'Taichung deputy mayor Zheng Zhaoxin said the city would proceed.',
        'key_quote_en': None, 'sentiment_reasoning': '',
        'entities': [{'name': '鄭照新', 'name_en': 'Zheng Zhaoxin', 'type': 'person', 'role': 'Deputy Mayor of Taichung'},
                     {'name': '台中市', 'name_en': 'Taichung City', 'type': 'location'}],
        'key_figure_statements': [{'speaker': 'Zheng Zhaoxin', 'statement_text': 'Zheng Zhaoxin: we will proceed.'}],
    }
    pairs = nr.apply_to_analysis(analysis, lambda zh: canon.get(zh))
    assert pairs == [('Zheng Zhaoxin', 'Cheng Chao-hsin')]
    assert analysis['entities'][0]['name_en'] == 'Cheng Chao-hsin'
    assert analysis['title_en'] == 'Cheng Chao-hsin defends budget'
    assert 'Cheng Chao-hsin said' in analysis['summary_en']
    assert analysis['key_figure_statements'][0]['statement_text'] == 'Cheng Chao-hsin: we will proceed.'
    assert analysis['key_quote_en'] is None
    # nothing to do → untouched
    assert nr.apply_to_analysis({'entities': [{'name': '王毅', 'name_en': 'Wang Yi', 'type': 'person'}]}, lambda zh: None) == []


# ── lookup decisions (no network) ────────────────────────────────────────

def _cand(roles=('KMT legislator',)):
    from collections import Counter
    return {'zh_trad': '陳冠廷', 'roles': Counter(roles), 'renderings': Counter({'Chen Kuan-ting': 5}), 'mentions': 5,
            'first_aid': 1, 'role_hint': roles[0]}


def test_decide_wikidata_cases():
    from scraper.processors.name_lookup import decide_wikidata
    clean = [{'qid': 'Q1', 'en': 'Chen Kuan-ting', 'desc': 'Taiwanese politician', 'citizenship': ['Taiwan'], 'positions': 2}]
    assert decide_wikidata(_cand(), clean)[:2] == ('approved', 'Chen Kuan-ting')
    namesake = [{'qid': 'Q2', 'en': 'REFRA1N', 'desc': 'Taiwanese esports gamer', 'citizenship': ['Taiwan'], 'positions': 0}]
    status, en, note, qid, _ = decide_wikidata(_cand(), namesake)
    assert status == 'pending' and en is None and 'namesake' in note and qid == 'Q2'
    hanyu = [{'qid': 'Q3', 'en': 'Chen Guanting', 'desc': 'Taiwanese politician', 'citizenship': ['Taiwan'], 'positions': 1}]
    assert decide_wikidata(_cand(), hanyu)[0] == 'pending'
    prc = [{'qid': 'Q4', 'en': 'Chen Guanting', 'desc': 'Chinese chess player', 'citizenship': ['PRC'], 'positions': 0}]
    assert decide_wikidata(_cand(), prc)[0] == 'pending'
    assert decide_wikidata(_cand(), []) is None


# ── poll intensity collapse (audit H8) ───────────────────────────────────

def test_collapse_intensity_sums_in_code():
    from scraper.processors.ai_pipeline import _normalise_poll_questions
    q = [{'question_text_zh': '對賴清德總統的施政表現是否滿意？', 'question_text_en': 'Satisfied with President Lai?',
          'options': [
              {'label_zh': '很滿意', 'label_en': 'Very satisfied', 'percentage': 15.9},
              {'label_zh': '還算滿意', 'label_en': 'Somewhat satisfied', 'percentage': 29.8},
              {'label_zh': '有點不滿意', 'label_en': 'Somewhat dissatisfied', 'percentage': 18.9},
              {'label_zh': '很不滿意', 'label_en': 'Very dissatisfied', 'percentage': 26.0},
              {'label_zh': '未明確回答', 'label_en': 'No response', 'percentage': 9.4}]}]
    out = _normalise_poll_questions(q)[0]['options']
    assert [(o['label_zh'], o['label_en'], o['percentage']) for o in out] == [
        ('滿意', 'Satisfied', 45.7), ('不滿意', 'Dissatisfied', 44.9), ('未明確回答', 'No response', 9.4)]
    # the article gave the aggregate as well → the plain rows stay, graded rows are dropped
    q[0]['options'].insert(0, {'label_zh': '滿意', 'label_en': 'Satisfied', 'percentage': 45.7})
    out = _normalise_poll_questions(q)[0]['options']
    assert [o['label_zh'] for o in out] == ['滿意', '很滿意', '還算滿意', '有點不滿意', '很不滿意', '未明確回答']
    # a plain three-option question is untouched
    plain = [{'question_text_zh': 'x', 'question_text_en': 'x', 'options': [
        {'label_zh': '支持', 'label_en': 'Support', 'percentage': 50.0},
        {'label_zh': '不支持', 'label_en': 'Oppose', 'percentage': 40.0},
        {'label_zh': '未明確回答', 'label_en': 'No response', 'percentage': 10.0}]}]
    assert [o['label_zh'] for o in _normalise_poll_questions(plain)[0]['options']] == ['支持', '不支持', '未明確回答']
