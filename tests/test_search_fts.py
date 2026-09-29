"""Feed search and the FTS indexes (migrations 0016-0018, 2026-09-29).

articles_fts (unicode61) treats a run of Chinese characters as a single token,
so a name inside a sentence was unsearchable: 賴清德 found 616 of 4,593
articles on staging. Chinese terms now go through articles_fts_zh (trigram)
with a LIKE confirmation, or LIKE alone under three characters. The update
trigger used to re-index an article's whole body on every approval."""
import contextlib
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.routes import articles  # noqa: E402
from scraper.utils import db as scraper_db  # noqa: E402
from scripts.migrate import apply_migrations  # noqa: E402

SCHEMA = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema.sql')

FEED_DEFAULTS = dict(entity=None, topic=None, sentiment=None, source_place=None, source_name=None,
                     bias=None, urgency=None, escalation_only=False, search=None, include_pending=False,
                     alt_model=None, alt_arm=None, page=1, page_size=50, admin=False)

ARTICLES = {
    # Names and terms inside unbroken runs of Han characters, as outlets print them.
    'lai_trad': ('總統賴清德今日出席國防部記者會', '賴清德表示國軍持續監控共軍動態並強化戰備', 'Lai attends MND briefing', 'zh-tw'),
    'lai_simp': ('赖清德再发谋独言论', '国台办发言人表示赖清德的言论是挑衅', 'TAO criticises Lai', 'zh-cn'),
    'tao_trad': ('國台辦今日舉行例行記者會', '發言人回應台獨問題', 'TAO holds press conference', 'zh-tw'),
    'drill': ('解放軍東部戰區宣布軍演', '東部戰區在台灣海峽周邊舉行聯合演習', 'PLA drills near Taiwan', 'zh-tw'),
    # Every trigram of 台灣海峽 occurs, never contiguously.
    'scattered': ('台灣海巡署公布數據', '灣海峽兩字出現在別處', 'Coast guard data places vessels', 'zh-tw'),
    'percent': ('台北股市上漲', '漲幅約百分之二', 'Taipei stocks rise', 'zh-tw'),
}


def _feed(**kw):
    return articles.list_articles(**{**FEED_DEFAULTS, **kw})


def _ids(out):
    return {a['url'] for a in out['articles']}


def _insert_article(conn, key, approved=1):
    title, body, title_en, lang = ARTICLES[key]
    cur = conn.execute(
        "INSERT INTO articles (source_id, url, title_original, title_en, content_original, language, "
        "published_at, analyst_approved) VALUES (1, ?, ?, ?, ?, ?, '2026-09-28T08:00:00+00:00', ?)",
        (key, title, title_en, body, lang, approved))
    conn.execute(
        "INSERT INTO ai_analysis (article_id, topic_primary, sentiment, sentiment_score, summary_en) "
        "VALUES (?, 'MIL_EXERCISE', 'neutral', 0, 'summary')", (cur.lastrowid,))
    return cur.lastrowid


def _new_db(path=':memory:'):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    with open(SCHEMA, encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.execute("INSERT INTO sources (name, url, source_type, place, language, scrape_method, bias) "
                 "VALUES ('Test', 'https://example.test', 'independent_media', 'TW', 'zh-tw', 'rss', 'centrist')")
    return conn


@pytest.fixture
def db(monkeypatch):
    conn = _new_db()
    for key in ARTICLES:
        _insert_article(conn, key)
    conn.commit()

    @contextlib.contextmanager
    def fake_conn():
        yield conn

    monkeypatch.setattr(articles, 'db_conn', fake_conn)
    return conn


def test_name_inside_a_run_of_chinese_is_found(db):
    assert 'lai_trad' in _ids(_feed(search='賴清德'))


def test_longer_term_needs_contiguous_match(db):
    found = _ids(_feed(search='台灣海峽'))
    assert found == {'drill'}          # 'scattered' has every trigram, not the phrase


def test_two_character_term(db):
    assert _ids(_feed(search='軍演')) == {'drill'}


def test_one_character_term(db):
    assert 'percent' in _ids(_feed(search='漲'))


def test_like_wildcards_are_literal(db):
    assert _ids(_feed(search='台%')) == set()
    assert _ids(_feed(search='台_')) == set()


def test_simplified_query_finds_traditional_text(db):
    pytest.importorskip('zhconv')
    assert {'lai_trad', 'lai_simp'} <= _ids(_feed(search='赖清德'))


def test_traditional_query_finds_simplified_text(db):
    pytest.importorskip('zhconv')
    assert {'lai_trad', 'lai_simp'} <= _ids(_feed(search='賴清德'))


def test_tai_spelling_survives_conversion(db):
    # zhconv's zh-tw form is 國臺辦; Taiwanese outlets print 國台辦.
    pytest.importorskip('zhconv')
    assert {'tao_trad', 'lai_simp'} <= _ids(_feed(search='国台办'))


def test_latin_search_stays_whole_word(db):
    found = _ids(_feed(search='PLA'))
    assert 'drill' in found
    assert 'scattered' not in found     # 'places' is not the word PLA


def test_search_respects_approval(db):
    db.execute("UPDATE articles SET analyst_approved = 0 WHERE url = 'drill'")
    assert _ids(_feed(search='軍演')) == set()
    assert _ids(_feed(search='軍演', include_pending=True, admin=True)) == {'drill'}


def test_short_term_ignores_unanalysed_articles(db):
    # The feed inner-joins ai_analysis; an article without one never shows.
    db.execute("INSERT INTO articles (source_id, url, title_original, content_original, language, "
               "analyst_approved) VALUES (1, 'bare', '軍演', '軍演', 'zh-tw', 1)")
    assert _ids(_feed(search='軍演', include_pending=True, admin=True)) == {'drill'}


def test_approval_does_not_reindex(db):
    before = db.total_changes
    db.execute("UPDATE articles SET analyst_approved = 1, event_cluster_id = 'c0123456789ab' WHERE url = 'drill'")
    # One row in articles; the old trigger also wrote a delete + insert into articles_fts.
    assert db.total_changes - before == 1


def test_title_edit_reindexes_both_indexes(db):
    db.execute("UPDATE articles SET title_original = '總統府發布新聞稿', title_en = 'Presidential Office statement' "
               "WHERE url = 'drill'")
    assert 'drill' in _ids(_feed(search='總統府'))
    assert 'drill' in _ids(_feed(search='statement'))
    assert 'drill' not in _ids(_feed(search='東部戰區宣布'))    # only in the old title
    for table in ('articles_fts', 'articles_fts_zh'):
        db.execute(f"INSERT INTO {table}({table}, rank) VALUES('integrity-check', 1)")


def test_migration_backfills_and_narrows_existing_db(tmp_path):
    """A pre-0018 database: no trigram table, the old catch-all update trigger."""
    conn = _new_db(str(tmp_path / 'old.db'))
    conn.executescript("""
        DROP TRIGGER articles_zh_ai; DROP TRIGGER articles_zh_ad; DROP TRIGGER articles_zh_au;
        DROP TABLE articles_fts_zh;
        DROP TRIGGER articles_au;
        CREATE TRIGGER articles_au AFTER UPDATE ON articles BEGIN
            INSERT INTO articles_fts(articles_fts, rowid, title_original, title_en, content_original, content_en)
            VALUES('delete', old.id, old.title_original, old.title_en, old.content_original, old.content_en);
            INSERT INTO articles_fts(rowid, title_original, title_en, content_original, content_en)
            VALUES (new.id, new.title_original, new.title_en, new.content_original, new.content_en);
        END;
    """)
    _insert_article(conn, 'lai_trad')
    conn.commit()

    apply_migrations(conn, quiet=True)

    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == 'wal'
    hits = conn.execute("SELECT rowid FROM articles_fts_zh WHERE articles_fts_zh MATCH '\"賴清德\"'").fetchall()
    assert len(hits) == 1               # the pre-existing row was indexed by the rebuild
    before = conn.total_changes
    conn.execute("UPDATE articles SET analyst_approved = 1")
    assert conn.total_changes - before == 1
    conn.close()


def test_migrations_are_noops_on_a_fresh_schema(tmp_path):
    """init_db.py runs schema.sql and then every migration."""
    conn = _new_db(str(tmp_path / 'fresh.db'))
    apply_migrations(conn, quiet=True)
    triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    assert {'articles_ai', 'articles_ad', 'articles_au',
            'articles_zh_ai', 'articles_zh_ad', 'articles_zh_au'} <= triggers
    conn.close()


def test_synchronous_normal_only_under_wal(tmp_path):
    rollback = str(tmp_path / 'rollback.db')
    sqlite3.connect(rollback).close()
    conn = scraper_db.get_connection(rollback)
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2        # FULL
    conn.execute("PRAGMA journal_mode = WAL")
    conn.close()
    conn = scraper_db.get_connection(rollback)
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1        # NORMAL
    conn.close()


def test_save_article_commits(tmp_path):
    path = str(tmp_path / 'scrape.db')
    _new_db(path).commit()
    writer = scraper_db.get_connection(path)
    scraper_db.save_article(writer, 1, 'https://example.test/a', '標題', '內文', 'zh-tw', None)
    reader = sqlite3.connect(path)
    assert reader.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 1
    writer.close()
    reader.close()
