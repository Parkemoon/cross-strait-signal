"""api/review_queue.py — the shared editorial state machine used by all four
review queues (military_exercises, polls, diplomacy_statements,
key_figure_statements)."""
import sqlite3
import pytest
from fastapi import HTTPException

from api.review_queue import approve_row, dismiss_row, merge_row, get_status


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE things (
            id INTEGER PRIMARY KEY,
            approval_status TEXT NOT NULL DEFAULT 'pending',
            merged_into_id INTEGER,
            reviewed_at TIMESTAMP,
            reviewed_by TEXT,
            blob TEXT
        )""")
    c.executemany(
        "INSERT INTO things (id, approval_status, blob) VALUES (?, ?, ?)",
        [(1, 'pending', 'x'), (2, 'approved', 'x'), (3, 'dismissed', 'x'),
         (4, 'merged', 'x'), (5, 'pending', 'x')])
    return c


def _row(conn, rid):
    return conn.execute("SELECT * FROM things WHERE id = ?", (rid,)).fetchone()


def test_approve(conn):
    assert approve_row(conn, 'things', 'thing', 1) == {"status": "approved", "id": 1}
    row = _row(conn, 1)
    assert row['approval_status'] == 'approved'
    assert row['reviewed_at'] is not None
    assert row['reviewed_by'] is None  # None preserves existing


def test_approve_missing_404(conn):
    with pytest.raises(HTTPException) as e:
        approve_row(conn, 'things', 'thing', 99)
    assert e.value.status_code == 404


def test_dismiss_with_reviewed_by_and_extra_set(conn):
    result = dismiss_row(conn, 'things', 'thing', 1, 'ed',
                         extra_set=", blob = NULL")
    assert result == {"status": "dismissed", "id": 1}
    row = _row(conn, 1)
    assert (row['approval_status'], row['reviewed_by'], row['blob']) == \
        ('dismissed', 'ed', None)


def test_reviewed_by_coalesce_preserves_existing(conn):
    dismiss_row(conn, 'things', 'thing', 1, 'ed')
    conn.execute("UPDATE things SET approval_status = 'pending' WHERE id = 1")
    approve_row(conn, 'things', 'thing', 1)  # reviewed_by=None
    assert _row(conn, 1)['reviewed_by'] == 'ed'


def test_merge(conn):
    result = merge_row(conn, 'things', 'thing', 1, 2, 'ed')
    assert result == {"status": "merged", "id": 1, "merged_into_id": 2}
    row = _row(conn, 1)
    assert (row['approval_status'], row['merged_into_id'], row['reviewed_by']) == \
        ('merged', 2, 'ed')


def test_merge_guards(conn):
    with pytest.raises(HTTPException) as e:      # self-merge
        merge_row(conn, 'things', 'thing', 1, 1)
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:      # source missing
        merge_row(conn, 'things', 'thing', 99, 2)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:      # source dismissed
        merge_row(conn, 'things', 'thing', 3, 2)
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:      # source already merged
        merge_row(conn, 'things', 'thing', 4, 2)
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:      # target missing
        merge_row(conn, 'things', 'thing', 1, 99)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:      # target not approved
        merge_row(conn, 'things', 'thing', 1, 5)
    assert e.value.status_code == 400
    # approved source may be merged (dedupe of two live rows)
    conn.execute("UPDATE things SET approval_status = 'approved' WHERE id = 5")
    assert merge_row(conn, 'things', 'thing', 2, 5)['status'] == 'merged'


def test_get_status(conn):
    assert get_status(conn, 'things', 'thing', 2) == 'approved'
    with pytest.raises(HTTPException):
        get_status(conn, 'things', 'thing', 99)
