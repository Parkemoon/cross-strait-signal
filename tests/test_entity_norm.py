# -*- coding: utf-8 -*-
"""shared/entity_norm.py — the one resolver used by both the pipeline write
path and the renormalise back-fill. The regression cases are real corpus
mislabels the old bidirectional prefix scan produced (see §4.6 of the
2026-07-03 code review)."""
import pytest

from shared.entity_norm import load_canon, resolve_name_en


@pytest.fixture(scope='module')
def canon():
    return load_canon()  # the real shipped table


def test_exact_match(canon):
    assert resolve_name_en('賴清德', canon) == 'Lai Ching-te'
    assert resolve_name_en('解放軍海軍', canon) == 'PLA Navy (PLAN)'


def test_exact_allows_explicit_single_char_key(canon):
    assert resolve_name_en('習', canon) == 'Xi Jinping'


def test_title_strip_title_first(canon):
    # The canonical §4.6 corruption: used to resolve to the MINISTRY.
    assert resolve_name_en('國防部長顧立雄', canon) == 'Wellington Koo'
    assert resolve_name_en('陆委会副主委梁文杰', canon) == 'Liang Wen-chieh'
    assert resolve_name_en('中國國家主席習近平', canon) == 'Xi Jinping'


def test_title_strip_name_first(canon):
    assert resolve_name_en('賴清德總統', canon) == 'Lai Ching-te'


def test_title_token_inside_exact_key_does_not_reroute(canon):
    # 立法院 is an exact key containing no title token issue; and a title
    # token inside an unresolvable compound must not force a bogus match.
    assert resolve_name_en('立法院', canon) == 'Legislative Yuan'
    assert resolve_name_en('總統府秘書長潘孟安', canon) is None


def test_fold_prefix_longest_wins(canon):
    # 解放軍海軍陸戰隊 must fold to the NAVY, not the bare PLA.
    assert resolve_name_en('解放軍海軍陸戰隊', canon) == 'PLA Navy (PLAN)'
    assert resolve_name_en('漢光41號演習', canon) == 'Han Kuang 41'
    assert resolve_name_en('國民黨立院黨團', canon) == 'Kuomintang (KMT)'


def test_no_open_ended_prefix_regressions(canon):
    # Old scan: 韓國→Han Kuo-yu, 福建→Fujian carrier, 中華民國→ROC Armed
    # Forces. Now explicit exact entries with the RIGHT values.
    assert resolve_name_en('韓國', canon) == 'South Korea'
    assert resolve_name_en('福建', canon) == 'Fujian'
    assert resolve_name_en('中華民國', canon) == 'Republic of China (ROC)'
    # And a truncated person name no longer guesses via key-startswith-name.
    assert resolve_name_en('萬安', canon) is None


def test_unknown_name_returns_none(canon):
    assert resolve_name_en('不存在的實體', canon) is None
    assert resolve_name_en('', canon) is None
    assert resolve_name_en(None, canon) is None


def test_legacy_flat_file_shape(tmp_path):
    p = tmp_path / 'flat.json'
    p.write_text('{"中國": "China"}', encoding='utf-8')
    canon = load_canon(str(p))
    assert resolve_name_en('中國', canon) == 'China'
    assert canon['title_tokens'] == [] and canon['fold_prefixes'] == []
