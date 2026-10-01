"""api/routes/review.py — the review routes are admin-only, reads included.

GET /review/queue and GET /review/stats used to rely on nginx alone
(`deny all` on the public site); the queue serves unapproved articles, so
the API checks the admin token itself."""
import contextlib
import os
import sqlite3
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.auth import require_admin  # noqa: E402
from api.routes import review  # noqa: E402

SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema.sql')
TOKEN = "s3cret-token"
READS = ["/review/queue", "/review/stats"]


@pytest.fixture
def client(monkeypatch):
    # The TestClient runs handlers on a worker thread.
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    with open(SCHEMA, encoding='utf-8') as f:
        conn.executescript(f.read())
    src = conn.execute(
        "INSERT INTO sources (name, url, source_type, place, language, bias) "
        "VALUES ('LTN', 'https://ltn.example', 'independent_media', 'TW', 'zh-tw', 'green')").lastrowid
    aid = conn.execute(
        "INSERT INTO articles (source_id, url, title_original, content_original, language, "
        "published_at, ai_processed, analyst_approved) VALUES (?, 'https://x.example/1', 't', 'c', "
        "'zh-tw', '2026-09-28T01:00:00', 1, 0)", (src,)).lastrowid
    conn.execute(
        "INSERT INTO ai_analysis (article_id, topic_primary, sentiment, sentiment_score, summary_en, "
        "needs_human_review, review_resolved) VALUES (?, 'DIP_STATEMENT', 'hostile', -0.6, 's', 1, 0)",
        (aid,))
    conn.commit()

    @contextlib.contextmanager
    def fake_conn():
        yield conn

    monkeypatch.setattr(review, 'db_conn', fake_conn)
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    app = FastAPI()
    app.include_router(review.router)
    return TestClient(app)


@pytest.mark.parametrize("path", READS)
@pytest.mark.parametrize("headers", [{}, {"X-Admin-Token": "wrong"}])
def test_reads_refuse_without_the_token(client, path, headers):
    r = client.get(path, headers=headers)
    assert r.status_code == 401
    assert "title_original" not in r.text and "pending" not in r.text


def test_reads_answer_with_the_token(client):
    auth = {"X-Admin-Token": TOKEN}
    queue = client.get("/review/queue", headers=auth)
    assert queue.status_code == 200
    assert [row["title_original"] for row in queue.json()] == ["t"]
    stats = client.get("/review/stats", headers=auth)
    assert stats.status_code == 200
    assert stats.json() == {"pending": 1, "resolved": 0, "pending_approval": 0}


@pytest.mark.parametrize("path", READS)
def test_unset_token_keeps_legacy_mode(client, monkeypatch, path):
    monkeypatch.setenv("ADMIN_TOKEN", "")
    assert client.get(path).status_code == 200


def test_every_review_route_requires_admin():
    for route in review.router.routes:
        calls = [d.call for d in route.dependant.dependencies]
        assert require_admin in calls, f"{sorted(route.methods)} {route.path} is not admin-gated"
