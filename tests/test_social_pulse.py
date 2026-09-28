"""api/routes/social.py — the Social rail shows the latest Weibo batch only
and PTT posts from the last 24 hours. scraped_at is a T-separated ISO
string; comparing it against datetime()'s space-separated output let every
batch from the same UTC day through (153 rows on prod instead of 50)."""
import contextlib
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.routes import social  # noqa: E402

SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema.sql')


def _iso(dt):
    return dt.isoformat()   # '2026-09-28T18:05:28.034358+00:00', as the scrapers write it


@pytest.fixture
def db(monkeypatch):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    with open(SCHEMA, encoding='utf-8') as f:
        conn.executescript(f.read())

    now = datetime.now(timezone.utc).replace(microsecond=123456)
    # Three Weibo batches six hours apart (all the same UTC day is the case
    # that broke), the latest with two items.
    for hours_ago, keys in ((12, ['old1', 'old2', 'old3']), (6, ['mid1', 'mid2']), (0, ['new1', 'new2'])):
        at = _iso(now - timedelta(hours=hours_ago))
        for rank, key in enumerate(keys, 1):
            conn.execute(
                "INSERT INTO social_pulse (platform, item_key, title, rank_position, scraped_at) "
                "VALUES ('weibo', ?, ?, ?, ?)", (key, key, rank, at))
    # PTT: one post inside 24h, one just outside it.
    for key, hours_ago in (('ptt-recent', 20), ('ptt-stale', 26)):
        conn.execute(
            "INSERT INTO social_pulse (platform, item_key, title, push_count, scraped_at) "
            "VALUES ('ptt', ?, ?, 10, ?)", (key, key, _iso(now - timedelta(hours=hours_ago))))
    conn.commit()

    @contextlib.contextmanager
    def fake_conn():
        yield conn

    monkeypatch.setattr(social, 'db_conn', fake_conn)
    return conn


def test_weibo_is_latest_batch_only(db):
    out = social.social_pulse()
    assert [i['item_key'] for i in out['weibo']['items']] == ['new1', 'new2']


def test_ptt_window_is_24_hours(db):
    out = social.social_pulse()
    assert [i['title'] for i in out['ptt']['items']] == ['ptt-recent']


def test_ptt_scraper_dedup_window_is_24_hours(db):
    # Same column, same format: the scraper's "already stored" check must
    # agree with the rail's 24-hour window.
    from scraper.scrapers.ptt_scraper import already_stored_today
    assert already_stored_today(db, 'ptt-recent') is True
    assert already_stored_today(db, 'ptt-stale') is False
