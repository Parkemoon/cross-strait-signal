# -*- coding: utf-8 -*-
"""scraper/scrapers/fjsen_scraper.py — list parsing and the cross-page merge.
Fixtures are cut down from real taihai.fjsen.com markup captured 2026-10-05
(the channel front page and the 台湾时政 section list)."""
from scraper.scrapers.fjsen_scraper import (
    LIST_URL,
    MAX_LINKS_PER_PAGE,
    merge_lists,
    parse_list,
)

FRONT_HTML = """
<div class="top_xw"><ul>
  <li>·<a href="http://taihai.fjsen.com/2026-09/30/content_32261790.htm" target="_blank">国台办：坚决反对“台独”分裂符合中美双方共同 …</a></li>
  <li>·<a href="https://www.fjsen.com/zhuanti/node_321030.htm" target="_blank">专题页</a></li>
</ul></div>
<div class="xw">
  <h1><a href="https://www.fjsen.com/2026-10/01/content_32262354.htm" target="_blank">日月谭天丨又一部陆剧火爆台湾，照见民进党“去中国化”纯属无用功</a></h1>
  <a href="https://www.fjsen.com/2026-10/01/content_32262354.htm" target="_blank"></a>
  <p>近日，又一部大陆电视剧火爆台湾。<span><a href="https://www.fjsen.com/2026-10/01/content_32262354.htm" target="_blank">[详细]</a></span></p>
</div>
<ul><li><a href="http://fjnews.fjsen.com/2026-09/28/content_32260671.htm" target="_blank">两岸婚姻家庭服务驿站在福州台湾会馆揭牌</a></li></ul>
"""

SECTION_HTML = """
<div class="z_18"><ul class="">
<li><span>2026-09-30</span><a href="http://taihai.fjsen.com/2026-09/30/content_32261835.htm" target="_blank">简舒培为何狂打蒋万安？媒体人揭民调：为了选举彰显“根正苗绿”</a></li>
<li><span>2026-09-30</span><a href="http://taihai.fjsen.com/2026-09/30/content_32261790.htm" target="_blank">国台办：坚决反对“台独”分裂符合中美双方共同利益</a></li>
<li><span>2026-09-29</span><!-- href made relative + query added (live hrefs are absolute) to cover urljoin -->
<a href="2026-09/29/content_32261015.htm?from=list" target="_blank">苏贞昌女儿称不反对教师节放假，江怡臻酸：你后悔投反对票了吗</a></li>
</ul></div>
<div class="lmt">今日热点</div>
<div class="z_16"><ul>
<li>
<a href="http://fjnews.fjsen.com/2026-10/03/content_32262621.htm" target="_blank">可逛可吃可体验，非遗里的“闽式生活”</a>
</li>
</ul></div>
<div class="tu_wz"><a href="http://fjnews.fjsen.com/2026-10/03/content_32262628.htm" title="文化润八闽">文化润八闽</a></div>
"""

SECTION_URL = 'http://taihai.fjsen.com/tw_politics.htm'


def test_front_page_keeps_headlines_and_off_channel_picks():
    pairs = parse_list(FRONT_HTML, LIST_URL, channel_only=False)
    urls = [u for u, _ in pairs]
    assert urls == [
        'http://taihai.fjsen.com/2026-09/30/content_32261790.htm',
        'https://www.fjsen.com/2026-10/01/content_32262354.htm',   # h1 lead story
        'http://fjnews.fjsen.com/2026-09/28/content_32260671.htm',
    ]
    # the empty anchor and the [详细] link under the headline are not entries
    assert all(len(t) >= 4 for _, t in pairs)


def test_section_page_drops_the_site_wide_sidebar():
    pairs = parse_list(SECTION_HTML, SECTION_URL, channel_only=True)
    assert [u for u, _ in pairs] == [
        'http://taihai.fjsen.com/2026-09/30/content_32261835.htm',
        'http://taihai.fjsen.com/2026-09/30/content_32261790.htm',
        'http://taihai.fjsen.com/2026-09/29/content_32261015.htm',  # relative href, query dropped
    ]


def test_per_page_cap():
    many = ''.join(
        f'<li><a href="http://taihai.fjsen.com/2026-09/30/content_{n}.htm">台海新闻标题{n}</a></li>'
        for n in range(MAX_LINKS_PER_PAGE + 10))
    assert len(parse_list(f'<ul>{many}</ul>', SECTION_URL, channel_only=True)) == MAX_LINKS_PER_PAGE


def test_merge_dedups_and_prefers_the_full_title():
    front = parse_list(FRONT_HTML, LIST_URL, channel_only=False)
    section = parse_list(SECTION_HTML, SECTION_URL, channel_only=True)
    merged = merge_lists([front, section])
    urls = [u for u, _ in merged]
    assert len(urls) == len(set(urls)) == 5
    # first-seen order: the front page's entries lead
    assert urls[0] == 'http://taihai.fjsen.com/2026-09/30/content_32261790.htm'
    assert dict(merged)[urls[0]] == '国台办：坚决反对“台独”分裂符合中美双方共同利益'


def test_merge_never_trades_a_full_title_for_a_cut_one():
    url = 'http://taihai.fjsen.com/2026-09/30/content_1.htm'
    merged = merge_lists([[(url, '完整的标题文字')], [(url, '完整的 …')]])
    assert merged == [(url, '完整的标题文字')]
