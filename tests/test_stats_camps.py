"""api/routes/stats.py — the sidebar's "Taiwan by camp" gauges carry all four
Taiwan alignment bands. blue_leaning used to be missing from the query, so
the green side showed two bands and the blue side one."""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.routes import stats  # noqa: E402

SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema.sql')
BANDS = ('green', 'green_leaning', 'blue_leaning', 'blue')


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    with open(SCHEMA, encoding='utf-8') as f:
        c.executescript(f.read())
    for i, bias in enumerate(BANDS + ('state_official',)):
        sid = c.execute("INSERT INTO sources (name, url, source_type, place, language, bias) "
                        "VALUES (?, ?, 'independent_media', ?, 'zh-tw', ?)",
                        (bias, f"https://{i}.example", 'PRC' if bias == 'state_official' else 'TW', bias)).lastrowid
        aid = c.execute("INSERT INTO articles (source_id, url, title_original, content_original, language, "
                        "published_at, ai_processed, analyst_approved) VALUES (?, ?, 't', 'c', 'zh-tw', "
                        "strftime('%Y-%m-%dT%H:%M:%S', 'now', '-1 day'), 1, 1)",
                        (sid, f"https://x.example/{bias}")).lastrowid
        c.execute("INSERT INTO ai_analysis (article_id, topic_primary, sentiment, sentiment_score, summary_en) "
                  "VALUES (?, 'POL_TONGDU', 'neutral', 0.0, 's')", (aid,))
    return c


@pytest.mark.parametrize("scoped", [False, True])
def test_camp_gauges_cover_all_four_bands(conn, scoped):
    out = stats._dashboard_stats_body(conn, 30, 'POL_TONGDU' if scoped else None,
                                      None, None, False, None, None, None)
    assert sorted(b['bias'] for b in out['sentiment_by_bias']) == sorted(BANDS)
