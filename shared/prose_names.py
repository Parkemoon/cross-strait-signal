# -*- coding: utf-8 -*-
"""Find the model's own renderings of a person's name inside English prose,
so history can be brought into line with the registry.

At extraction time `shared.name_registry.apply_to_analysis` knows the model's
rendering (the entity's own `name_en`) and swaps it for the canonical form in
the English text fields. For articles analysed before a name was settled the
rendering is gone — `renormalise_entities.py` rewrote the entity row — but the
prose still says "Liu Fuguo" or "Fu-Kuo Liu" while the chip says "Liu Fu-kuo".

This module recovers the pairs from the text itself. Every two- or three-token
capitalised span is a candidate; it is accepted as a rendering of a person
(zh, en_now) only when it reads EXACTLY as that person's characters — each
syllable equal to the character's pinyin or its Wade-Giles form (apostrophes,
umlauts and case ignored), surname-first or given-first, hyphenated or run
together. "Lin Chia-ling" is therefore never taken for 林佳龍 (ling ≠ lung /
long), "Foreign Minister" never segments, and a span equal to another person's
current form in the same article is left alone. Precision over recall: a
Tongyong spelling the model never produces is not worth the false positives.
"""
import re
from functools import lru_cache

from shared.romanisation import _COMPOUND_SURNAMES, _Style, _pinyin, wg_syllable

_TOKEN = r"[A-Z][a-z]+(?:-[A-Za-z]+)*(?:'[a-z]+)?"
_SPAN = re.compile(rf"(?<![A-Za-z\-'])({_TOKEN}(?:\s+{_TOKEN}){{1,2}})(?![A-Za-z\-'])")
_CJK = re.compile(r'^[一-鿿]{2,3}$')


@lru_cache(maxsize=None)
def readings(ch):
    """Lower-case spellings one character may take: pinyin (every heteronym) and its Wade-Giles form."""
    if _pinyin is None:
        return frozenset()
    out = set()
    for alts in _pinyin(ch, style=_Style.NORMAL, heteronym=True):
        for py in alts:
            py = py.replace('ü', 'v')
            out.add(py.replace('v', 'u'))
            out.add(wg_syllable(py).replace('v', 'u'))
    return frozenset(out)


def _norm(tok):
    return tok.lower().replace("'", '').replace('ü', 'u')


def _given_matches(given_str, chars):
    """True when given_str (lower, no hyphens) is r1 [+ r2] for readings of the given characters."""
    if len(chars) == 1:
        return given_str in readings(chars[0])
    for r1 in readings(chars[0]):
        if given_str.startswith(r1) and given_str[len(r1):] in readings(chars[1]):
            return True
    return False


def reads_as(zh, span):
    """True when `span` is a romanisation of the two- or three-character name `zh`
    (single-character surname), surname-first or given-first."""
    zh = (zh or '').strip()
    if not _CJK.match(zh) or zh[:2] in _COMPOUND_SURNAMES or _pinyin is None:
        return False
    toks = span.split()
    if not 2 <= len(toks) <= 3:
        return False
    for sur, given in ((toks[0], toks[1:]), (toks[-1], toks[:-1])):
        if '-' in sur:
            continue
        if _norm(sur) not in readings(zh[0]):
            continue
        g = ''.join(_norm(t) for t in given).replace('-', '')
        if _given_matches(g, zh[1:]):
            return True
    return False


def candidate_spans(text):
    """Every 2- and 3-token capitalised span in the text (sub-spans of longer runs included)."""
    out = set()
    for m in _SPAN.finditer(text or ''):
        toks = m.group(1).split()
        for n in (2, 3):
            for i in range(0, len(toks) - n + 1):
                out.add(' '.join(toks[i:i + n]))
    return out


def find_pairs(text, persons):
    """(rendering, en_now) pairs to rewrite in `text`. `persons` = [(zh, en_now), …] for
    the article. A span equal to any person's current form is never a rendering."""
    current = {en for _, en in persons if en}
    pairs = []
    for span in candidate_spans(text):
        if span in current:
            continue
        hits = {en_now for zh, en_now in persons if en_now and span != en_now and reads_as(zh, span)}
        if len(hits) == 1:                 # two people in one article can share a reading (陳之漢 / 陳智菡 → Chen Chih-han): leave it
            pairs.append((span, hits.pop()))
    return pairs
