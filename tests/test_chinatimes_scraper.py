# -*- coding: utf-8 -*-
"""scraper/scrapers/chinatimes_scraper.py — the parsing and dedup halves.
Fixtures are cut down from real chinatimes.com markup captured 2026-09-24
(a politics 總覽 list page, a realtime article, a 兩岸徵文 opinion piece)."""
import sqlite3

from scraper.scrapers.chinatimes_scraper import (
    already_stored,
    canonical_url,
    extract_body,
    is_challenge,
    list_url,
    parse_list,
    taipei_to_utc,
)

LIST_HTML = """
<div class="articlebox-compact"><div class="row">
  <div class="col-4 thumb-photo-wrapper"><div class="thumb-photo video"><div class="cropper">
    <a href="/realtimenews/20260924000038-260407"><img alt="x" class="photo" src="a.jpg"/></a>
  </div></div></div>
  <div class="col">
    <h3 class="title"><a href="/realtimenews/20260924000038-260407">
      直擊圓山市場「洋流」人潮  董智森：跟我打招呼的比較多
    </a></h3>
    <div class="meta-info">
      <time datetime="2026-09-24 00:12"><span class="hour">00:12</span><span class="date">2026/09/24</span></time>
      <div class="category"><a href="/politic/politic-news">新聞</a></div>
    </div>
    <p class="intro">民進黨台北市長參選人沈伯洋日前到石牌商圈…</p>
  </div>
</div></div>
<div class="articlebox-compact"><div class="row"><div class="col">
  <h3 class="title"><a href="https://www.chinatimes.com/newspapers/20260918000593-260118?ctrack=pc_politic_headl_p02">雲林最富鄉 麥寮鄉長三搶一</a></h3>
  <div class="meta-info"><time datetime="2026-09-18 03:34"></time></div>
</div></div></div>
<div class="articlebox-compact"><div class="row"><div class="col">
  <h3 class="title"><a href="/politic/politic-news">新聞</a></h3>
</div></div></div>
"""

ARTICLE_HTML = """
<h1 class="article-title">直擊圓山市場「洋流」人潮  董智森：跟我打招呼的比較多</h1>
<div class="article-body tbl-forkorts-article">
  <p>民進黨台北市長參選人沈伯洋日前到石牌商圈、公館夜市造勢。</p>
  <div class="ad text-wrap-around with-placeholder"><p>廣告</p></div>
  <p></p>
  <p>23日在《新聞大白話》節目，主持人譚伊倫問：董哥昨天不是有看到沈伯洋？</p>
  <div class="article-source">（中時新聞網）</div>
  <p>董智森直呼，「跟我打招呼的人比他還多！」</p>
  <div class="promote-word"><div class="payment-method-description">
    <p>您的每一份支持都至關重要。我們已開通 LINE Pay 、 Google Pay 、 Apple Pay 及 信用卡 等多種支持方式。</p>
  </div></div>
</div>
"""

OPINION_HTML = """
<div class="article-body">
  <p>古文詩詞內涵深遠，確實值得花些心思博聞強記。</p>
  <p>（齊人／台北市）</p>
  <p>【徵文啟事】</p>
  <p>中時新聞網「兩岸徵文」欄目，徵文主題：台灣人看大陸、大陸人看台灣。</p>
  <p>投稿信箱：tw@want-daily.com</p>
</div>
"""


def test_canonical_url_normalises_to_the_stored_chdtv_form():
    want = 'https://www.chinatimes.com/realtimenews/20260924000038-260407?chdtv'
    assert canonical_url('/realtimenews/20260924000038-260407') == want
    assert canonical_url('https://www.chinatimes.com/realtimenews/20260924000038-260407'
                         '?ctrack=pc_politic_headl_p01') == want
    assert canonical_url('/realtimenews/20260924000038-260407?chdtv') == want
    assert (canonical_url('/newspapers/20260918000593-260118')
            == 'https://www.chinatimes.com/newspapers/20260918000593-260118?chdtv')
    assert (canonical_url('/opinion/20260924000017-262106')
            == 'https://www.chinatimes.com/opinion/20260924000017-262106?chdtv')


def test_canonical_url_rejects_non_articles():
    assert canonical_url('/politic/politic-news') is None
    assert canonical_url('/politic/total?page=2&chdtv') is None
    assert canonical_url('https://wantrich.chinatimes.com/news/20260924000038-260407') is None
    assert canonical_url('/realtimenews/20260924000038-260407/amp') is None
    assert canonical_url('') is None


def test_taipei_to_utc_is_naive_utc():
    assert taipei_to_utc('2026-09-24 00:12') == '2026-09-23T16:12:00'
    assert taipei_to_utc('2026-09-18 03:34') == '2026-09-17T19:34:00'
    assert taipei_to_utc('') is None
    assert taipei_to_utc('2026/09/24') is None
    assert taipei_to_utc(None) is None


def test_parse_list_reads_title_url_and_time():
    items = parse_list(LIST_HTML)
    assert items == [
        {'url': 'https://www.chinatimes.com/realtimenews/20260924000038-260407?chdtv',
         'title': '直擊圓山市場「洋流」人潮 董智森：跟我打招呼的比較多',
         'published_at': '2026-09-23T16:12:00'},
        {'url': 'https://www.chinatimes.com/newspapers/20260918000593-260118?chdtv',
         'title': '雲林最富鄉 麥寮鄉長三搶一',
         'published_at': '2026-09-17T19:34:00'},
    ]


def test_extract_body_keeps_direct_paragraphs_only():
    assert extract_body(ARTICLE_HTML) == (
        '民進黨台北市長參選人沈伯洋日前到石牌商圈、公館夜市造勢。\n'
        '23日在《新聞大白話》節目，主持人譚伊倫問：董哥昨天不是有看到沈伯洋？\n'
        '董智森直呼，「跟我打招呼的人比他還多！」')


def test_extract_body_cuts_the_call_for_submissions():
    assert extract_body(OPINION_HTML) == (
        '古文詩詞內涵深遠，確實值得花些心思博聞強記。\n（齊人／台北市）')


def test_extract_body_without_a_body_is_empty():
    assert extract_body('<html><title>請稍候...</title><p>正在執行安全驗證</p></html>') == ''


def test_is_challenge():
    assert is_challenge(403, '請稍候...')
    assert is_challenge(403, '政治 - 中時新聞網')
    assert is_challenge(200, '請稍候...')
    assert not is_challenge(200, '總覽 -政治 - 中時新聞網')


def test_list_url_uses_the_paginated_overview():
    assert (list_url('https://www.chinatimes.com/politic/', 1)
            == 'https://www.chinatimes.com/politic/total?page=1&chdtv')
    assert (list_url('https://www.chinatimes.com/chinese/', 3)
            == 'https://www.chinatimes.com/chinese/total?page=3&chdtv')


def _db(*urls):
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE articles (id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL)')
    conn.executemany('INSERT INTO articles (url) VALUES (?)', [(u,) for u in urls])
    return conn


def test_already_stored_matches_any_query_variant():
    base = 'https://www.chinatimes.com/realtimenews/20260923004852-260407'
    canonical = base + '?chdtv'
    assert already_stored(_db(base + '?chdtv'), canonical)
    assert already_stored(_db(base + '?ctrack=pc_politic_headl_p01'), canonical)
    assert already_stored(_db(base), canonical)
    assert not already_stored(_db(), canonical)


def test_already_stored_does_not_match_a_longer_path():
    base = 'https://www.chinatimes.com/realtimenews/20260923004852-260407'
    conn = _db(base + '0?chdtv', base + 'A?chdtv', base + '/amp?chdtv')
    assert not already_stored(conn, base + '?chdtv')
