"""scripts/cluster_events.py — cluster ids must stay TEXT in the
INTEGER-affinity event_cluster_id column. Bare 8-hex ids were coerced when
they looked numeric: '3e412345' became REAL inf (so unrelated clusters
merged), all-digit ids became integers."""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import cluster_events  # noqa: E402

SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema.sql')


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    with open(SCHEMA, encoding='utf-8') as f:
        c.executescript(f.read())
    for i in range(1, 4):
        c.execute("INSERT INTO sources (name, url, source_type, place, language, bias) "
                  "VALUES (?, ?, 'independent_media', 'TW', 'en', 'green')", (f"S{i}", f"https://s{i}.example"))
    return c


def _art(conn, source_id, title, published, cluster, size=2):
    return conn.execute(
        "INSERT INTO articles (source_id, url, title_original, title_en, content_original, language, "
        "published_at, ai_processed, event_cluster_id, cluster_size) VALUES (?, ?, ?, ?, 'c', 'en', ?, 1, ?, ?)",
        (source_id, f"https://x.example/{title}", title, title, published, cluster, size)).lastrowid


def test_new_ids_are_stored_as_text(conn):
    for _ in range(200):
        conn.execute("INSERT INTO articles (source_id, url, title_original, content_original, language, "
                     "published_at, event_cluster_id) VALUES (1, ?, 't', 'c', 'en', '2026-09-28', ?)",
                     (f"https://x.example/{_}", cluster_events.new_cluster_id()))
    kinds = {r[0] for r in conn.execute("SELECT DISTINCT typeof(event_cluster_id) FROM articles")}
    assert kinds == {'text'}


def test_the_old_format_was_coerced(conn):
    # Documents the failure the repair exists for.
    aid = _art(conn, 1, 'x', '2026-09-28T00:00:00', '3e412345')
    assert conn.execute("SELECT typeof(event_cluster_id), event_cluster_id FROM articles WHERE id = ?",
                        (aid,)).fetchone()[:] == ('real', float('inf'))


def test_repair_splits_infinity_and_rekeys_finite_ids(conn):
    inf = '9e999'   # stores as REAL inf, like '3e412345' did
    bluebook_a = _art(conn, 1, 'Japan Diplomatic Bluebook downgrades China neighbour', '2026-04-10T03:00:00', inf)
    bluebook_b = _art(conn, 2, 'Japan Bluebook downgrades China to important neighbour', '2026-04-10T09:00:00', inf)
    tanker_a = _art(conn, 1, 'Oil tanker carrying crude oil barrels sails for Taiwan', '2026-04-20T04:00:00', inf)
    tanker_b = _art(conn, 3, 'Tanker carries 2 million barrels of crude oil for Taiwan', '2026-04-20T09:00:00', inf)
    # Similar title but months later: its partners have moved on
    lone = _art(conn, 3, 'Japan Bluebook downgrades China again', '2026-07-01T00:00:00', inf)
    num_a = _art(conn, 1, 'n1', '2026-05-01T00:00:00', '12345678')
    num_b = _art(conn, 2, 'n2', '2026-05-01T01:00:00', '12345678')
    text = _art(conn, 3, 't1', '2026-05-01T02:00:00', 'cabcdef012345')

    summary = cluster_events.repair_numeric_cluster_ids(conn)
    assert summary == {'finite_clusters_rekeyed': 1, 'merged_rows': 5,
                       'regrouped_clusters': 2, 'unclustered_rows': 1}

    cid = {r['id']: (r['event_cluster_id'], r['cluster_size'])
           for r in conn.execute("SELECT id, event_cluster_id, cluster_size FROM articles")}
    assert cid[bluebook_a][0] == cid[bluebook_b][0]
    assert cid[tanker_a][0] == cid[tanker_b][0]
    assert cid[bluebook_a][0] != cid[tanker_a][0]
    assert cid[bluebook_a][1] == 2
    assert cid[lone] == (None, 1)
    assert cid[num_a][0] == cid[num_b][0] and cid[num_a][0].startswith('c')
    assert cid[text][0] == 'cabcdef012345'
    assert conn.execute("SELECT COUNT(*) FROM articles WHERE typeof(event_cluster_id) IN ('integer', 'real')"
                        ).fetchone()[0] == 0

    # Idempotent
    assert cluster_events.repair_numeric_cluster_ids(conn)['merged_rows'] == 0
