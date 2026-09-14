# -*- coding: utf-8 -*-
"""House style for English person names (shared/name_style.py) and its two
write-path hooks: the registry upsert and the Admin ▾ Names approve route.
Cases are the ones the 2026-09-14 audit of Ed's queue pass actually hit."""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")

from shared import name_registry as nr  # noqa: E402
from shared.name_style import chinese_reading, style_change, style_name  # noqa: E402

MIGRATION = os.path.join(os.path.dirname(__file__), '..', 'db', 'migrations', '0014_name_registry.sql')
pypinyin = pytest.importorskip('pypinyin')


@pytest.mark.parametrize('zh,en,side,role,want,rule', [
    # commas
    ('林昱佑', 'Lin, Yu-Yu', 'TW', '', 'Lin Yu-yu', 'style'),
    ('蔡欣育', 'Tsai, Hsin-Yu', 'TW', '', 'Tsai Hsin-yu', 'style'),
    ('盧蔣江', 'Lu, Chiang, and Chiang', 'TW', 'KMT officials', 'Lu, Chiang, and Chiang', None),   # not a person: left for the route to refuse
    # Taiwanese three-character names: Surname First-name
    ('呂禮詩', 'Lu Li-Shih', 'TW', '', 'Lu Li-shih', 'style'),
    ('張炳煌', 'Chang Bing Huang', 'TW', '', 'Chang Bing-huang', 'style'),
    ('黃馨慧', 'Huang Sinhuei', 'TW', 'KMT city councillor', 'Huang Sin-huei', 'style'),
    ('劉復國', 'Fu-Kuo Liu', 'TW', '', 'Liu Fu-kuo', 'order'),
    ('陳柏霖', 'Bolin Chen', 'TW', 'Taiwanese celebrity', 'Chen Bo-lin', 'order'),
    ('董佳瑜', 'Chiayu Tung', 'TW', '', 'Tung Chia-yu', 'order'),
    ('郭明錤', 'Ming-Chi Kuo', None, 'analyst at TF International Securities, Taiwan', 'Kuo Ming-chi', 'order'),
    ('周學佑', 'Chou Shyue-yow', 'TW', 'Deputy Representative to Japan', 'Chou Shyue-yow', None),  # hyphen = Chinese, not Japanese
    # left alone: adopted English names, PRC side, two characters, compound surname
    ('郭正亮', 'Julian Kuo', 'TW', '', 'Julian Kuo', None),
    ('黃仁勳', 'Jensen Huang', None, '', 'Jensen Huang', None),
    ('連勝文', 'Sean Lien', 'TW', '', 'Sean Lien', None),
    ('秦日新', 'Victor Chin', 'TW', 'KMT representative to the US', 'Victor Chin', None),
    ('習近平', 'Xi Jinping', 'PRC', '', 'Xi Jinping', None),
    ('陳斌華', 'Chen Binhua', None, 'Taiwan Affairs Office spokesperson', 'Chen Binhua', None),
    ('陳菊', 'Chen Chu', 'TW', '', 'Chen Chu', None),
    ('歐陽娜娜', 'Ouyang Nana', 'TW', '', 'Ouyang Nana', None),
    ('徐春鶯', 'Xu Chunying', None, '', 'Xu Chunying', None),               # no side evidence, unhyphenated: could be PRC style
    # left alone: Hanyu forms on Taiwan-side people — the SYSTEM is Ed's call, not a style fix
    ('尹乃菁', 'Yin Naijing', 'TW', 'KMT Culture and Communications Committee chair', 'Yin Naijing', None),
    ('駱以軍', 'Luo Yijun', 'TW', 'Taiwanese author', 'Luo Yijun', None),
    # Japanese: surname first
    ('岸田文雄', 'Fumio Kishida', 'TW', 'former Prime Minister of Japan', 'Kishida Fumio', 'japanese'),
    ('高市早苗', 'Sanae Takaichi', None, '', 'Takaichi Sanae', 'japanese'),
    ('隅修三', 'Shuzo Sumi', 'TW', 'President of the Japan-Taiwan Exchange Association', 'Sumi Shuzo', 'japanese'),
    ('玉城丹尼', 'Denny Tamaki', None, 'Governor of Okinawa', 'Tamaki Denny', 'japanese'),
    ('橋本明', 'Hashimoto Akira', None, "Director of Matsubara City Mayor's Office", 'Hashimoto Akira', None),
    ('上地常夫', 'Tsuneo Uechi', None, 'Mayor of Yonaguni Town', 'Uechi Tsuneo', 'japanese'),
    ('矢内原忠雄', 'Yanaihara Tadao', None, 'Japanese economist', 'Yanaihara Tadao', None),
    ('川普政府', 'Trump administration', None, '', 'Trump administration', None),
    ('唐納·川普', 'Donald Trump', None, 'US President', 'Donald Trump', None),
])
def test_style_change(zh, en, side, role, want, rule):
    assert style_change(zh, en, side, role) == (want, rule)


def test_chinese_reading_orders():
    assert chinese_reading('劉復國', 'Fu-Kuo Liu') == ('G', 'Liu', ['fu', 'kuo'])
    assert chinese_reading('劉復國', 'Liu Fu-kuo') == ('S', 'Liu', ['fu', 'kuo'])
    assert chinese_reading('劉復國', 'Peter Liu') is None
    assert chinese_reading('黃仁勳', 'Jensen Huang') is not None   # jen-sen happens to fit 仁勳's initials — ENGLISH_GIVEN is what protects it
    assert chinese_reading('陳菊', 'Chen Chu') is None            # two characters: out of scope


def test_style_name_is_idempotent():
    for zh, en in [('呂禮詩', 'Lu Li-Shih'), ('劉復國', 'Fu-Kuo Liu'), ('岸田文雄', 'Fumio Kishida'), ('林昱佑', 'Lin, Yu-Yu')]:
        once = style_name(zh, en, 'TW', 'former Prime Minister of Japan' if zh == '岸田文雄' else '')
        assert style_name(zh, once, 'TW', 'former Prime Minister of Japan' if zh == '岸田文雄' else '') == once


@pytest.fixture
def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    with open(MIGRATION, encoding='utf-8') as f:
        c.executescript(f.read())
    return c


def test_upsert_applies_house_style(conn):
    nr.upsert(conn, '呂禮詩', 'Lu Li-Shih', 'TW', 'wikidata', 'pending', role_hint='retired naval captain')
    nr.upsert(conn, '岸田文雄', 'Fumio Kishida', 'TW', 'wikidata', 'pending', role_hint='former Prime Minister of Japan')
    nr.upsert(conn, '郭正亮', 'Julian Kuo', None, 'glossary', 'approved')
    rows = {r['zh_trad']: r['en'] for r in conn.execute("SELECT zh_trad, en FROM name_registry")}
    assert rows == {'呂禮詩': 'Lu Li-shih', '岸田文雄': 'Kishida Fumio', '郭正亮': 'Julian Kuo'}


def test_approve_route_styles_and_refuses_commas(conn, monkeypatch):
    from contextlib import contextmanager
    from fastapi import HTTPException
    from api.routes import names

    @contextmanager
    def fake_db():
        yield conn
    monkeypatch.setattr(names, 'db_conn', fake_db)
    rid = nr.upsert(conn, '劉復國', 'Fu-Kuo Liu', 'TW', 'wikidata', 'pending', role_hint='Director, Taiwan Security Research Center')
    bad = nr.upsert(conn, '盧蔣江', 'Lu, Chiang, and Chiang', 'TW', 'search', 'pending', role_hint='KMT officials')
    out = names.approve(rid, names.Decision(reviewed_by='test'))
    assert out['en'] == 'Liu Fu-kuo'
    row = conn.execute("SELECT en, source, status FROM name_registry WHERE id = ?", (rid,)).fetchone()
    assert (row['en'], row['source'], row['status']) == ('Liu Fu-kuo', 'wikidata', 'approved')   # styled at insert, so approving the proposal is not an edit
    with pytest.raises(HTTPException) as e:
        names.approve(bad, names.Decision(reviewed_by='test'))
    assert e.value.status_code == 400
    patched = names.patch(rid, names.Decision(en='Liu Fu-Kuo'))          # a typed form is styled too
    assert patched['en'] == 'Liu Fu-kuo'
