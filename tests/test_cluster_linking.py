"""scripts/cluster_events.py — the summary-cosine link, the group-average
guard against hub articles, and per-run cluster ids."""
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import cluster_events as ce  # noqa: E402

SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema.sql')

# Same story, no shared title keywords: each side's own headline.
SANCTIONS_TW = ("Allies' ministers punished by Beijing for the first time",
                "China's foreign ministry imposed sanctions on Paraguayan foreign minister Gustavo Villate "
                "and Belize minister Francis Fonseca, freezing their assets and banning entry.")
SANCTIONS_PRC = ("Supporting independence only drops a stone on one's own feet",
                 "The foreign ministry announced countermeasures against Paraguay's Gustavo Villate and "
                 "Belize's Francis Fonseca, freezing assets and banning entry over Taiwan.")
DRILL_TW = ("Defence ministry keeps watch on the PLA",
            "The defence ministry said PLA warships and aircraft held live-fire drills in five sea zones "
            "east of Fujian and that the armed forces were monitoring the drills closely.")
DRILL_PRC = ("Eastern Theatre Command tests joint combat readiness",
             "The Eastern Theatre Command said warships and aircraft held live-fire drills in five sea "
             "zones east of Fujian to test joint combat readiness.")
# A press-conference transcript: a little like every story it touches.
HUB = ("Transcript of the Taiwan Affairs Office press conference",
       "The spokesperson answered questions on sanctions freezing the assets of Gustavo Villate and Francis "
       "Fonseca and banning their entry, live-fire drills by warships and aircraft in five sea zones east of "
       "Fujian, a spy drama, and cross-strait flights.")
FILLER = [
    "Typhoon brings heavy rain to the east coast and schools close",
    "Baseball team wins the regional title after extra innings",
    "Legislature debates the central government budget for next year",
    "Semiconductor exports rose in the third quarter on AI demand",
    "City council approves new metro line extension",
    "Film festival opens with a documentary on fishing villages",
    "Central bank holds interest rates steady",
    "Hospital strike ends after pay agreement",
]


def _vectors(docs):
    """docs: {id: (title, summary)}; document frequencies include FILLER."""
    terms = {k: ce.summary_terms(t, s) for k, (t, s) in docs.items()}
    corpus = list(terms.values()) + [ce.summary_terms(f, '') for f in FILLER]
    df = Counter(w for t in corpus for w in t)
    return ce.summary_vectors(terms, df, len(corpus))


def _art(aid, source_id, doc, cluster=None):
    title, _ = doc
    return {'id': aid, 'source_id': source_id, 'title_en': title, 'title_original': title,
            'language': 'en', 'event_cluster_id': cluster}


def test_summary_link_joins_what_titles_miss():
    docs = {1: SANCTIONS_TW, 2: SANCTIONS_PRC}
    arts = [_art(1, 1, SANCTIONS_TW), _art(2, 2, SANCTIONS_PRC)]
    assert not ce.titles_are_similar(*ce.comparison_title(arts[0]), *ce.comparison_title(arts[1]))
    vec = _vectors(docs)
    assert ce.cosine(vec[1], vec[2]) >= ce.SUMMARY_THRESHOLD
    groups = ce.group_articles(arts, vec)
    assert groups[1] == groups[2]
    # The title-only behaviour is the summary rule switched off
    groups = ce.group_articles(arts, vec, summary_threshold=2.0)
    assert groups[1] != groups[2]


def test_same_source_never_linked():
    docs = {1: SANCTIONS_TW, 2: SANCTIONS_PRC}
    groups = ce.group_articles([_art(1, 1, SANCTIONS_TW), _art(2, 1, SANCTIONS_PRC)], _vectors(docs))
    assert groups[1] != groups[2]


def test_hub_does_not_chain_two_stories():
    docs = {1: SANCTIONS_TW, 2: SANCTIONS_PRC, 3: DRILL_TW, 4: DRILL_PRC, 5: HUB}
    vec = _vectors(docs)
    arts = [_art(1, 1, SANCTIONS_TW), _art(2, 2, SANCTIONS_PRC),
            _art(3, 3, DRILL_TW), _art(4, 4, DRILL_PRC), _art(5, 5, HUB)]
    # Precondition: the hub alone would bridge the stories.
    assert max(ce.cosine(vec[5], vec[i]) for i in (1, 2)) >= ce.SUMMARY_THRESHOLD
    assert max(ce.cosine(vec[5], vec[i]) for i in (3, 4)) >= ce.SUMMARY_THRESHOLD
    chained = ce.group_articles(arts, vec, group_threshold=0.0)
    assert len(set(chained.values())) == 1

    groups = ce.group_articles(arts, vec)
    assert groups[1] == groups[2]
    assert groups[3] == groups[4]
    assert groups[1] != groups[3]
    assert groups[5] in (groups[1], groups[3])   # the hub joins the one story it fits best


def test_title_links_join_unconditionally():
    a = {'id': 1, 'source_id': 1, 'title_en': 'Japan Bluebook downgrades China neighbour',
         'title_original': '', 'language': 'en'}
    b = {'id': 2, 'source_id': 2, 'title_en': 'Japan Bluebook downgrades China to important neighbour',
         'title_original': '', 'language': 'en'}
    # Empty vectors: cosine 0 everywhere, so only the title rule can join them
    groups = ce.group_articles([a, b], {}, group_threshold=1.0)
    assert groups[1] == groups[2]


def test_fresh_ids_per_run_and_aged_out_singletons_kept():
    arts = [_art(1, 1, SANCTIONS_TW, 'cold'), _art(2, 2, SANCTIONS_PRC), _art(3, 3, DRILL_TW),
            _art(4, 4, DRILL_PRC), _art(5, 5, HUB, 'ckeep'), _art(6, 6, HUB)]
    groups = {1: 1, 2: 1, 3: 3, 4: 3, 5: 5, 6: 6}
    assign, clear = ce.cluster_assignments(arts, groups)
    assert assign[1] == assign[2] and assign[1][1] == 2
    assert assign[3] == assign[4] and assign[3][0] != assign[1][0]
    # A group never inherits an old id: that let stories grow for a week
    assert assign[1][0] != 'cold'
    # Singletons: one with an id keeps it (not touched), one without is cleared
    assert 5 not in assign and 6 not in assign
    assert clear == [6]


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / 'c.db')
    c = sqlite3.connect(path)
    with open(SCHEMA, encoding='utf-8') as f:
        c.executescript(f.read())
    for i, place in enumerate(['TW', 'PRC', 'TW', 'PRC', 'PRC'], start=1):
        c.execute("INSERT INTO sources (name, url, source_type, place, language, bias) "
                  "VALUES (?, ?, 'independent_media', ?, 'en', 'centrist')", (f"S{i}", f"https://s{i}.example", place))
    c.commit()
    c.close()

    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn
    monkeypatch.setattr(ce, 'get_connection', connect)
    return connect


def _insert(conn, source_id, doc, hours_ago, cluster=None):
    title, summary = doc
    published = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime('%Y-%m-%dT%H:%M:%S')
    aid = conn.execute(
        "INSERT INTO articles (source_id, url, title_original, title_en, content_original, language, "
        "published_at, ai_processed, event_cluster_id) VALUES (?, ?, ?, ?, 'c', 'en', ?, 1, ?)",
        (source_id, f"https://x.example/{title}/{hours_ago}", title, title, published, cluster)).lastrowid
    conn.execute("INSERT INTO ai_analysis (article_id, topic_primary, sentiment, summary_en) "
                 "VALUES (?, 'DIP_SANCTIONS', 'neutral', ?)", (aid, summary))
    return aid


def test_end_to_end_cross_strait_story(db):
    conn = db()
    for f in FILLER:   # document-frequency background
        _insert(conn, 5, (f, f), hours_ago=200)
    tw = _insert(conn, 1, SANCTIONS_TW, hours_ago=30)
    prc = _insert(conn, 2, SANCTIONS_PRC, hours_ago=20)
    drill_tw = _insert(conn, 3, DRILL_TW, hours_ago=10)
    drill_prc = _insert(conn, 4, DRILL_PRC, hours_ago=8)
    hub = _insert(conn, 2, HUB, hours_ago=6)
    single = _insert(conn, 5, ("Cabinet reshuffle announced", "The premier named three new ministers."), 5)
    conn.commit()
    conn.close()

    ce.cluster_recent_articles(hours=48)

    conn = db()
    row = {r['id']: (r['event_cluster_id'], r['cluster_size'])
           for r in conn.execute("SELECT id, event_cluster_id, cluster_size FROM articles")}
    assert row[tw][0] == row[prc][0] and row[tw][0]
    assert row[drill_tw][0] == row[drill_prc][0] and row[drill_tw][0] != row[tw][0]
    assert row[hub][0] in (row[tw][0], row[drill_tw][0])
    assert row[single] == (None, 1)
