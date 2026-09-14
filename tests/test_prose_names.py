# -*- coding: utf-8 -*-
"""Prose history pass helpers (shared/prose_names.py): recovering the model's
own rendering of a person from English text so it can be rewritten to the
registry form."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")

pytest.importorskip('pypinyin')

from shared.name_registry import rewrite_renderings  # noqa: E402
from shared.prose_names import candidate_spans, find_pairs, reads_as  # noqa: E402


@pytest.mark.parametrize('zh,span,ok', [
    ('劉復國', 'Liu Fuguo', True),          # Hanyu, run together
    ('劉復國', 'Liu Fu-guo', True),         # Hanyu, hyphenated
    ('劉復國', 'Fu-Kuo Liu', True),         # Wade-Giles, given first
    ('劉復國', 'Liu Fu-Kuo', True),         # capital after hyphen
    ('劉復國', 'Fukuo Liu', True),
    ('劉復國', 'Liu Fu-kuo', True),
    ('林佳龍', 'Lin Chia-ling', False),     # ling is not 龍 — another person
    ('林佳龍', 'Lin Chia-lung', True),
    ('林佳龍', 'Lin Jialong', True),
    ('黃仁勳', 'Jensen Huang', False),      # adopted name: not a reading
    ('葛兆恩', "Ge Zhao'en", True),
    ('葛兆恩', 'Ke Chao-en', True),
    ('陳菊', 'Chen Ju', True),              # two-character name
    ('陳菊', 'Chen Chu', True),
    ('陳菊', 'Chen Chu-mei', False),
    ('歐陽娜娜', 'Ouyang Nana', False),     # compound surname: out of scope
    ('劉復國', 'Foreign Minister', False),
    ('劉復國', 'Liu', False),
])
def test_reads_as(zh, span, ok):
    assert reads_as(zh, span) is ok


def test_candidate_spans_include_subspans():
    spans = candidate_spans("President Lai Ching-te met Fu-Kuo Liu and the U.S. envoy.")
    assert 'Lai Ching-te' in spans and 'President Lai' in spans and 'Fu-Kuo Liu' in spans
    assert 'President Lai Ching-te' in spans


def test_find_pairs_and_rewrite():
    persons = [('劉復國', 'Liu Fu-kuo'), ('林佳龍', 'Lin Chia-lung'), ('黃仁勳', 'Jensen Huang')]
    text = ("Fu-Kuo Liu said Lin Jialong and Lin Chia-ling would meet Jensen Huang; "
            "Liu Fu-kuo added that Foreign Minister Lin Chia-lung agreed.")
    pairs = find_pairs(text, persons)
    assert sorted(pairs) == [('Fu-Kuo Liu', 'Liu Fu-kuo'), ('Lin Jialong', 'Lin Chia-lung')]
    out = rewrite_renderings(text, pairs)
    assert out == ("Liu Fu-kuo said Lin Chia-lung and Lin Chia-ling would meet Jensen Huang; "
                   "Liu Fu-kuo added that Foreign Minister Lin Chia-lung agreed.")


def test_find_pairs_leaves_a_reading_two_people_share():
    persons = [('陳之漢', 'Holger Chen'), ('陳智菡', 'Vicky Chen')]
    assert find_pairs("Chen Chih-han spoke.", persons) == []
    assert find_pairs("Chen Chih-han spoke.", persons[:1]) == [('Chen Chih-han', 'Holger Chen')]


def test_find_pairs_never_rewrites_another_persons_current_form():
    # 陳建仁 rendered 'Chen Chien-jen'; 陳菊's current form is 'Chen Chu' — a span equal to a
    # current form is never treated as someone else's rendering.
    persons = [('陳建仁', 'Chen Chien-jen'), ('陳菊', 'Chen Chu')]
    assert find_pairs("Chen Chu and Chen Jianren spoke.", persons) == [('Chen Jianren', 'Chen Chien-jen')]
