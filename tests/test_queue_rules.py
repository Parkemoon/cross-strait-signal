"""shared/queue_rules.py — rule binning of exercise and poll candidates."""
import sqlite3

import pytest

from shared.queue_rules import bin_candidates, revert_bins


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.executescript("""
        CREATE TABLE military_exercises (
            id INTEGER PRIMARY KEY, name_en TEXT, start_date TEXT, location_label TEXT,
            approval_status TEXT NOT NULL DEFAULT 'pending',
            reviewed_at TIMESTAMP, reviewed_by TEXT);
        CREATE TABLE pollsters (id INTEGER PRIMARY KEY, slug TEXT);
        CREATE TABLE polls (
            id INTEGER PRIMARY KEY, pollster_id INTEGER, source_article_id INTEGER,
            sample_size INTEGER, pending_results_json TEXT,
            approval_status TEXT NOT NULL DEFAULT 'pending',
            reviewed_at TIMESTAMP, reviewed_by TEXT);
        CREATE TABLE key_figure_statements (
            id INTEGER PRIMARY KEY, figure_id TEXT, statement_kind TEXT, statement_text TEXT,
            approval_status TEXT NOT NULL DEFAULT 'pending',
            reviewed_at TIMESTAMP, reviewed_by TEXT);
        INSERT INTO key_figure_statements (id, figure_id, statement_kind, statement_text) VALUES
            (1, 'lai_chingte', 'quote', 'Peace relies on strength.'),
            (2, 'lai_chingte', 'action', 'Announced a drone academy.'),
            (3, 'xi_jinping', 'statement', 'Stressed reunification.');
        INSERT INTO pollsters VALUES (1, 'unknown'), (2, 'tvbs');
    """)
    c.executemany(
        "INSERT INTO military_exercises (id, name_en, start_date, location_label,"
        " approval_status, reviewed_at) VALUES (?, ?, ?, ?, ?, ?)",
        [(1, 'Han Kuang 42', '2026-07-09', 'Taiwan', 'pending', None),       # keeps
         (2, 'Drill', None, 'Kinmen', 'pending', None),                      # no start date
         (3, 'Drill', ' ', None, 'pending', None),                           # both: first rule wins
         (4, 'Drill', '2026-09-01', '', 'pending', None),                    # no location
         (5, 'Drill', None, None, 'pending', '2026-10-01 10:00:00'),         # analyst edited
         (6, 'Drill', None, None, 'approved', '2026-10-01 10:00:00')])       # not pending
    c.executemany(
        "INSERT INTO polls (id, pollster_id, source_article_id, sample_size,"
        " pending_results_json) VALUES (?, ?, ?, ?, ?)",
        [(1, 1, 100, 1000, '{"questions": []}'),   # unknown pollster
         (2, 2, 101, None, '{"questions": []}'),   # named pollster, no sample: kept for now
         (3, 1, None, 1000, None)])                # manual entry, never binned
    return c


def _status(conn, table, rid):
    return conn.execute(
        f"SELECT approval_status, reviewed_by FROM {table} WHERE id = ?", (rid,)).fetchone()


def test_dry_run_reports_and_writes_nothing(conn):
    got = {(t, r): ids for t, r, ids in bin_candidates(conn)}
    assert got[('military_exercises', 'no-start-date')] == [2, 3]
    assert got[('military_exercises', 'no-location')] == [4]
    assert got[('polls', 'unknown-pollster')] == [1]
    assert got[('key_figure_statements', 'not-a-quote')] == [2, 3]
    assert _status(conn, 'military_exercises', 2) == ('pending', None)


def test_apply_dismisses_and_stamps(conn):
    bin_candidates(conn, apply=True)
    assert _status(conn, 'military_exercises', 2) == ('dismissed', 'rule:no-start-date')
    assert _status(conn, 'military_exercises', 3) == ('dismissed', 'rule:no-start-date')
    assert _status(conn, 'military_exercises', 4) == ('dismissed', 'rule:no-location')
    assert _status(conn, 'military_exercises', 1) == ('pending', None)
    assert _status(conn, 'military_exercises', 5) == ('pending', None)
    assert _status(conn, 'polls', 1) == ('dismissed', 'rule:unknown-pollster')
    assert _status(conn, 'polls', 2) == ('pending', None)
    assert _status(conn, 'polls', 3) == ('pending', None)
    # the extraction is kept so a revert restores a usable row
    assert conn.execute("SELECT pending_results_json FROM polls WHERE id = 1").fetchone()[0]


def test_idempotent(conn):
    bin_candidates(conn, apply=True)
    assert all(not ids for _, _, ids in bin_candidates(conn, apply=True))


def test_revert_one_rule_then_all(conn):
    bin_candidates(conn, apply=True)
    assert revert_bins(conn, 'no-location') == 1
    assert _status(conn, 'military_exercises', 4) == ('pending', None)
    assert _status(conn, 'military_exercises', 2) == ('dismissed', 'rule:no-start-date')
    assert revert_bins(conn) == 5
    assert _status(conn, 'polls', 1) == ('pending', None)


def test_revert_leaves_analyst_decisions(conn):
    conn.execute("UPDATE military_exercises SET approval_status = 'dismissed',"
                 " reviewed_by = 'ed' WHERE id = 1")
    bin_candidates(conn, apply=True)
    revert_bins(conn)
    assert _status(conn, 'military_exercises', 1) == ('dismissed', 'ed')
