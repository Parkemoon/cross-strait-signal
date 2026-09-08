"""api/routes/visits.py — feed coverage of a visit: the visit family's own
articles (keeper + merged rows, chains included) plus their event-cluster
siblings, side-classified, feed-visible only for public callers."""
import contextlib
import os
import sqlite3
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")

from api.routes import visits as visits_route  # noqa: E402

SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema.sql')


def _src(conn, name, place, bias):
    cur = conn.execute(
        "INSERT INTO sources (name, url, source_type, place, language, bias) VALUES (?, ?, 'independent_media', ?, 'zh-tw', ?)",
        (name, f"https://{name.replace(' ', '')}.example", place, bias))
    return cur.lastrowid


def _art(conn, source_id, title, cluster, published, approved=1, review=0, resolved=0, score=0.0):
    cur = conn.execute(
        """INSERT INTO articles (source_id, url, title_original, title_en, content_original, language,
                                 published_at, ai_processed, analyst_approved, event_cluster_id, is_hidden)
           VALUES (?, ?, ?, ?, 'body', 'zh-tw', ?, 1, ?, ?, 0)""",
        (source_id, f"https://x.example/{title.replace(' ', '-')}", title, title, published, approved, cluster))
    aid = cur.lastrowid
    conn.execute(
        """INSERT INTO ai_analysis (article_id, topic_primary, sentiment, sentiment_score, summary_en,
                                    needs_human_review, review_resolved)
           VALUES (?, 'PARTY_VISIT', 'cooperative', ?, 'summary', ?, ?)""",
        (aid, score, review, resolved))
    return aid


def _visit(conn, article_id, status='approved', merged_into=None):
    cur = conn.execute(
        """INSERT INTO cross_strait_visits (article_id, direction, visitor_name_en, visitor_affiliation,
                                            visitor_side, approval_status, merged_into_id, start_date)
           VALUES (?, 'TW_TO_PRC', 'Cheng Li-wun', 'KMT', 'TW', ?, ?, '2026-04-08')""",
        (article_id, status, merged_into))
    return cur.lastrowid


@pytest.fixture
def db(monkeypatch):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    with open(SCHEMA, encoding='utf-8') as f:
        conn.executescript(f.read())

    udn = _src(conn, 'UDN', 'TW', 'blue')
    udn_breaking = _src(conn, 'UDN Breaking', 'TW', 'blue')
    xinhua = _src(conn, 'Xinhua', 'PRC', 'state_official')
    zaobao = _src(conn, 'Zaobao Cross-Strait', 'SG', 'centrist')

    a1 = _art(conn, udn, 'Cheng meets Chen Jining', 'clusX', '2026-04-08T08:00:00', score=0.6)
    a2 = _art(conn, xinhua, 'Chen Jining meets Cheng', 'clusX', '2026-04-08T09:00:00', score=0.7)
    a3 = _art(conn, zaobao, 'KMT chair in Shanghai', 'clusX', '2026-04-08T10:00:00')
    a4 = _art(conn, udn_breaking, 'Cheng at Sun Yat-sen Mausoleum', None, '2026-04-09T08:00:00')
    a5 = _art(conn, xinhua, 'Commentary on the visit', 'clusX', '2026-04-08T11:00:00', approved=0)
    a6 = _art(conn, udn, 'Han Kuo-yu on the budget', 'clusY', '2026-04-09T09:00:00')

    v1 = _visit(conn, a1)                                   # approved keeper
    v2 = _visit(conn, a4, status='merged', merged_into=v1)  # merged child
    v3 = _visit(conn, a2, status='merged', merged_into=v2)  # merged into the child — chain
    v4 = _visit(conn, a6, status='pending')                 # not public
    conn.commit()

    @contextlib.contextmanager
    def fake_conn():
        yield conn

    monkeypatch.setattr(visits_route, 'db_conn', fake_conn)
    return {'conn': conn, 'v1': v1, 'v4': v4, 'a1': a1, 'a2': a2, 'a3': a3, 'a4': a4, 'a5': a5, 'a6': a6}


def test_public_coverage_walks_merge_chain_and_cluster(db):
    out = visits_route.coverage(db['v1'], admin=False)
    by_id = {a['id']: a for a in out['articles']}
    assert set(by_id) == {db['a1'], db['a2'], db['a3'], db['a4']}
    # own + merged (chained) articles are 'visit'; the Zaobao sibling is 'cluster'
    assert by_id[db['a1']]['via'] == 'visit'
    assert by_id[db['a2']]['via'] == 'visit'      # reachable both ways — 'visit' wins
    assert by_id[db['a4']]['via'] == 'visit'
    assert by_id[db['a3']]['via'] == 'cluster'
    assert by_id[db['a3']]['cluster_id'] == 'clusX'
    # sides + outlets: UDN and UDN Breaking collapse to one publication
    assert out['counts'] == {'articles': 4, 'outlets': 3, 'TW': 2, 'PRC': 1, 'other': 1}
    assert by_id[db['a3']]['side'] is None
    # oldest first
    assert [a['id'] for a in out['articles']] == [db['a1'], db['a2'], db['a3'], db['a4']]


def test_admin_sees_unapproved_sibling(db):
    out = visits_route.coverage(db['v1'], admin=True)
    assert db['a5'] in {a['id'] for a in out['articles']}
    assert out['counts']['PRC'] == 2


def test_pending_visit_is_404_for_public_only(db):
    with pytest.raises(HTTPException) as e:
        visits_route.coverage(db['v4'], admin=False)
    assert e.value.status_code == 404
    assert visits_route.coverage(db['v4'], admin=True)['counts']['articles'] == 1
    with pytest.raises(HTTPException):
        visits_route.coverage(999, admin=True)


def test_list_carries_coverage_counts(db):
    out = visits_route.list_visits(days=3650, start=None, end=None, direction=None, affiliation=None,
                                   side=None, level=None, status=None, figure=None, limit=50)
    assert [v['id'] for v in out['visits']] == [db['v1']]
    assert out['visits'][0]['coverage'] == {'articles': 4, 'outlets': 3, 'TW': 2, 'PRC': 1, 'other': 1}


def test_counts_helper_handles_empty():
    assert visits_route._coverage_counts([]) == {'articles': 0, 'outlets': 0, 'TW': 0, 'PRC': 0, 'other': 0}
