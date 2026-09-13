"""Romanisation heuristics shared by the name-registry worker, the audit
scripts and the tests.

Two questions answered from text alone, no network:

  side_from_role(role)   — which side of the strait a person entity sits on,
                           read from the model's own role text ('KMT
                           legislator' → TW, 'TAO spokesperson' → PRC, an
                           ambiguous or empty role → None).
  hanyu_markers(name_en) — does a romanised name carry a Hanyu Pinyin
                           marker a Wade-Giles / Tongyong rendering never
                           has: the initials q / x / zh, or an unhyphenated
                           two-syllable given name (Taiwan usage hyphenates:
                           Ching-te, Bi-khim, Kuo-yu). Established English
                           names (Wellington Koo, Eric Chu) carry neither.

Measured 2026-09-13 on 90 days of prod entities: ~9 % of Taiwan-side person
entities carried a marker, two-thirds of them from PRC-source articles in
simplified script. Detector noise: Japanese names in kanji trip the
unhyphenated rule, and a Taiwanese person whose established English name is
pinyin-shaped (the actor Chen Bolin) is a false positive — hence markers
flag for a lookup, they never rewrite anything by themselves.

to_wade_giles(name_zh) — deterministic Hanyu → Wade-Giles conversion in
Taiwan convention (no apostrophes, hyphenated given name, 思 = szu). Needs
pypinyin; returns None without it. Only ever a SUGGESTION: against the
glossary's own person entries it matches 35 of 87, and every miss is an
established English name or a Taiwan-idiosyncratic spelling (Jaw Shaw-kong,
Lu Shiow-yen), which is exactly why a sourced form beats a generated one.
"""
import re

try:  # optional dependency — the generated tier switches off without it
    from pypinyin import pinyin as _pinyin, Style as _Style
except ImportError:  # pragma: no cover
    _pinyin = None

TW_ROLE = re.compile(
    r"\b(taiwan|taiwanese|roc\b|kmt|dpp|tpp|npp|legislat|legislative yuan|mac\b|mainland affairs|"
    r"executive yuan|control yuan|examination yuan|premier|magistrate|taipei|kaohsiung|taichung|"
    r"tainan|taoyuan|hsinchu|keelung|kinmen|matsu|penghu|hualien|yilan|chiayi|changhua|nantou|"
    r"pingtung|taitung|miaoli|yunlin|mnd\b|ministry of national defen[cs]e|mofa\b|sef\b|"
    r"straits exchange|academia sinica|tsmc|presidential office)", re.I)
PRC_ROLE = re.compile(
    r"\b(prc\b|china|chinese|ccp|cpc|beijing|pla\b|people'?s liberation|tao\b|taiwan affairs office|"
    r"state council|xinhua|global times|mainland|fujian|xiamen|shanghai|guangdong|eastern theat|"
    r"communist|npc\b|cppcc|arats|mfa\b|foreign ministry spokes|hong kong|macau|macao|"
    r"united front|politburo)", re.I)

_HANYU_INITIAL = re.compile(r"(?:^|[\s\-'])(?:q|x|zh)[aeiouü]", re.I)
_SURNAME_GIVEN = re.compile(r"^([A-Z][a-z]+)\s+([A-Z][a-z]+)$")
CJK_NAME = re.compile(r'^[一-鿿]{2,4}$')


# PRC bodies whose names contain "Taiwan" — stripped before the TW test so
# "Taiwan Affairs Office spokesperson" reads as PRC, not both.
_PRC_TAIWAN_BODIES = re.compile(r"taiwan affairs office|taiwan (?:research|work|studies)|taiwan compatriot", re.I)


def side_from_role(role):
    r = role or ""
    tw = bool(TW_ROLE.search(_PRC_TAIWAN_BODIES.sub('', r)))
    prc = bool(PRC_ROLE.search(r))
    if tw and not prc:
        return "TW"
    if prc and not tw:
        return "PRC"
    return None


def _syllables(word):
    return len(re.findall(r"[aeiouü]+", word.lower()))


def hanyu_markers(name_en):
    """List of marker labels found in a romanised name (empty = none)."""
    n = (name_en or "").strip()
    out = []
    if _HANYU_INITIAL.search(n):
        out.append("q/x/zh initial")
    m = _SURNAME_GIVEN.match(n)
    if m and _syllables(m.group(2)) >= 2 and "-" not in m.group(2):
        out.append("unhyphenated given name")
    return out


def pinyin_for_tw(name_en, role):
    """True when the entity reads as Taiwan-side by role and its English
    name carries a Hanyu marker."""
    return side_from_role(role) == "TW" and bool(hanyu_markers(name_en))


# ── Hanyu → Wade-Giles (Taiwan convention) ──────────────────────────────
_INITIALS = ['zh', 'ch', 'sh', 'b', 'p', 'm', 'f', 'd', 't', 'n', 'l', 'g', 'k', 'h',
             'j', 'q', 'x', 'r', 'z', 'c', 's', 'y', 'w']
_INIT_MAP = {'b': 'p', 'p': 'p', 'm': 'm', 'f': 'f', 'd': 't', 't': 't', 'n': 'n', 'l': 'l',
             'g': 'k', 'k': 'k', 'h': 'h', 'j': 'ch', 'q': 'ch', 'x': 'hs', 'zh': 'ch', 'ch': 'ch',
             'sh': 'sh', 'r': 'j', 'z': 'ts', 'c': 'ts', 's': 's', 'y': 'y', 'w': 'w', '': ''}
_FINAL_MAP = {'ong': 'ung', 'iong': 'iung', 'ian': 'ien', 'ie': 'ieh', 'er': 'erh', 'ue': 'ueh', 've': 'ueh'}
_WHOLE = {'zi': 'tzu', 'ci': 'tzu', 'si': 'szu', 'zhi': 'chih', 'chi': 'chih', 'shi': 'shih', 'ri': 'jih',
          'yi': 'i', 'ye': 'yeh', 'you': 'yu', 'yu': 'yu', 'yue': 'yueh', 'yuan': 'yuan', 'yun': 'yun',
          'yan': 'yen', 'yong': 'yung', 'er': 'erh',
          'ju': 'chu', 'qu': 'chu', 'xu': 'hsu', 'jue': 'chueh', 'que': 'chueh', 'xue': 'hsueh',
          'juan': 'chuan', 'quan': 'chuan', 'xuan': 'hsuan', 'jun': 'chun', 'qun': 'chun', 'xun': 'hsun',
          'lv': 'lu', 'nv': 'nu', 'lve': 'lueh', 'nve': 'nueh', 'lue': 'lueh', 'nue': 'nueh'}
_UO_TO_O = {'d', 't', 'n', 'l', 'z', 'c', 's', 'r', 'zh', 'ch'}
_UI_TO_UEI = {'g', 'k'}
_COMPOUND_SURNAMES = {'歐陽', '欧阳', '司馬', '司马', '諸葛', '诸葛', '上官', '司徒', '張簡', '张简', '范姜'}


def wg_syllable(py):
    py = py.lower().replace('ü', 'v')
    if py in _WHOLE:
        return _WHOLE[py]
    init = next((i for i in _INITIALS if py.startswith(i)), '')
    fin = py[len(init):]
    if fin == 'uo':
        fin = 'o' if init in _UO_TO_O else 'uo'
    elif fin == 'ui' and init in _UI_TO_UEI:
        fin = 'uei'
    elif fin in _FINAL_MAP:
        fin = _FINAL_MAP[fin]
    return _INIT_MAP.get(init, init) + fin


def to_wade_giles(name_zh):
    """'鄭照新' → 'Cheng Chao-hsin'; None without pypinyin or for non-CJK input."""
    name_zh = (name_zh or '').strip()
    if _pinyin is None or not CJK_NAME.match(name_zh):
        return None
    n_sur = 2 if name_zh[:2] in _COMPOUND_SURNAMES else 1
    syls = [s[0] for s in _pinyin(name_zh, style=_Style.NORMAL, heteronym=False)]
    sur = ''.join(wg_syllable(s) for s in syls[:n_sur]).capitalize()
    given = '-'.join(wg_syllable(s) for s in syls[n_sur:])
    given = given[:1].upper() + given[1:]
    return f"{sur} {given}" if given else sur
