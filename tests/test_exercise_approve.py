"""api/routes/military.py approve_exercise — the approved-twin dedupe.

Step 1 folds a candidate into an approved row with the same canonical name
and performer. Without a date guard every recurring patrol collapsed into
the first one approved (prod: the 2026-07-02 joint-combat-readiness-patrol
vanished into the 2026-05-25 row)."""
import contextlib
import os
import sqlite3
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")

from api.routes import military  # noqa: E402

SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema.sql')


@pytest.fixture
def db(monkeypatch):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    with open(SCHEMA, encoding='utf-8') as f:
        conn.executescript(f.read())

    def add(start_date, status='pending', canonical='joint-combat-readiness-patrol', performer='PRC'):
        return conn.execute(
            "INSERT INTO military_exercises (article_id, canonical_name, performer, start_date, approval_status) "
            "VALUES (1, ?, ?, ?, ?)", (canonical, performer, start_date, status)).lastrowid

    @contextlib.contextmanager
    def fake_conn():
        yield conn

    monkeypatch.setattr(military, 'db_conn', fake_conn)
    return types.SimpleNamespace(conn=conn, add=add)


def _status(conn, rid):
    r = conn.execute("SELECT approval_status, merged_into_id FROM military_exercises WHERE id = ?", (rid,)).fetchone()
    return (r['approval_status'], r['merged_into_id'])


def test_distant_twin_does_not_absorb_a_later_patrol(db):
    may = db.add('2026-05-25', status='approved')
    july = db.add('2026-07-02')
    out = military.approve_exercise(july)
    assert 'duplicate_of' not in out
    assert _status(db.conn, july) == ('approved', None)
    assert _status(db.conn, may) == ('approved', None)


def test_near_twin_absorbs_the_candidate(db):
    first = db.add('2026-09-09', status='approved')
    dup = db.add('2026-09-10')
    out = military.approve_exercise(dup)
    assert out['duplicate_of'] == first
    assert _status(db.conn, dup) == ('merged', first)


def test_nearest_twin_wins(db):
    db.add('2026-08-20', status='approved')
    near = db.add('2026-09-08', status='approved')
    cand = db.add('2026-09-10')
    assert military.approve_exercise(cand)['duplicate_of'] == near


def test_undated_candidate_still_joins_a_dated_twin(db):
    # A re-report with no date of its own (the Han Kuang 42 case on prod)
    hk = db.add('2026-04-11', status='approved', canonical='han-kuang-42', performer='ROC')
    cand = db.add(None, canonical='han-kuang-42', performer='ROC')
    assert military.approve_exercise(cand)['duplicate_of'] == hk


def test_dated_candidate_skips_an_undated_twin(db):
    db.add(None, status='approved')
    cand = db.add('2026-09-10')
    out = military.approve_exercise(cand)
    assert 'duplicate_of' not in out
    assert _status(db.conn, cand) == ('approved', None)
