# -*- coding: utf-8 -*-
"""English name style — the house rules for a person's English form
(Ed, 2026-09-14), applied wherever a name enters the registry
(shared/name_registry.upsert: the Step-3f lookup worker and the seed) and
wherever an analyst types one (the Admin ▾ Names approve / patch routes).

Rules, in the order they are applied:

1. No commas. "Lin, Yu-Yu" loses the comma and continues through the rules
   below; a form with more than one comma ("Lu, Chiang, and Chiang") is not
   a single person and comes back unchanged — the route refuses to approve
   a form that still carries a comma.
2. PRC-side names are left alone (Hanyu, no hyphen — "Xi Jinping").
3. An adopted English given name is left alone (Julian Kuo, Jensen Huang,
   Victor Chin, April Yao) — matched against ENGLISH_GIVEN, because plenty
   of English names also segment into pinyin syllables (ju-lian, jen-sen).
4. Japanese names are surname first, modern Japanese-government style
   (Kishida Fumio, Takaichi Sanae, Tamaki Denny). Evidence is the role
   (Japan, LDP, Diet, Okinawa …) or a token in JP_SURNAMES — never the
   registry `side`, because the lookup worker stamps every row TW. A name
   already surname-first is left; when neither token is a listed surname
   the form is left for the analyst rather than guessed.
5. Taiwanese three-character names are "Surname First-name": one-syllable
   surname, hyphenated two-syllable given name, only its first syllable
   capitalised (Lee Chien-lung, Lu Li-shih, Tung Chia-yu, Liu Fu-kuo). A
   form counts as a romanisation of *this* name only when every syllable's
   initial is consistent with its character's pinyin or Wade-Giles initial,
   surname-first or given-first — otherwise it is an adopted name and
   untouched. The romanisation SYSTEM is never changed here: a Hanyu form on
   a Taiwan-side person (Yin Naijing, Luo Yijun) is Ed's call and stays.
   Two-character and compound-surname names keep their accepted form. An
   unhyphenated surname-first form with no side evidence at all ("Xu
   Chunying" from the files) is left, since it may be PRC style.

`style_name(zh, en, side, role)` returns the styled form; `style_change`
also returns which rule fired, for logs and tests. Without pypinyin only
rules 1–4 can act (rule 5 needs the characters' readings).
"""
import re

from shared.romanisation import (_COMPOUND_SURNAMES, _INITIALS, _PY_SYLLABLES, _Style, _pinyin,
                                 hanyu_markers, side_from_role, wg_syllable)

CJK3 = re.compile(r'^[一-鿿]{3}$')

# Which English spellings may open a syllable whose pinyin initial is the key.
_INIT_OK = {
    'b': {'b', 'p'}, 'p': {'p'}, 'd': {'d', 't'}, 't': {'t'}, 'g': {'g', 'k'}, 'k': {'k'},
    'j': {'j', 'ch', 'c', 'g'}, 'q': {'q', 'ch', 'c'}, 'x': {'x', 'hs', 's', 'sh'},
    'zh': {'zh', 'ch', 'j'}, 'ch': {'ch'}, 'sh': {'sh', 's'}, 'r': {'r', 'j'},
    'z': {'z', 'ts', 'tz'}, 'c': {'c', 'ts', 'tz'}, 's': {'s'},
    'h': {'h'}, 'f': {'f'}, 'l': {'l'}, 'm': {'m'}, 'n': {'n'},
    'y': {'y', 'i', 'e', 'a', 'o', 'u'}, 'w': {'w', 'o', 'u', 'a', 'e'},
    '': {'a', 'e', 'o', 'i', 'u', 'y', 'w', 'n'},
}

# Syllables a romanised Chinese name may be built from: pinyin, the Wade-Giles
# forms the converter produces, and the Tongyong / Hokkien / older spellings
# that appear in Taiwanese names.
_SYLLABLES = set(_PY_SYLLABLES) | {wg_syllable(p) for p in _PY_SYLLABLES} | {
    'khim', 'jhih', 'jhang', 'cih', 'sih', 'jyun', 'siou', 'siu', 'wun', 'jyh', 'shyh', 'tzyy', 'jiun', 'hsiu',
    'shiu', 'huei', 'juei', 'chia', 'chiao', 'chien', 'chiang', 'hsiang', 'hsien', 'hsiao', 'hsueh', 'tsung', 'tzu',
    'jui', 'kuei', 'shih', 'jen', 'jo', 'tse', 'tseng', 'kung', 'hung', 'lung', 'tung', 'yung', 'chung', 'sung',
    'jung', 'nung', 'tsai', 'tsao', 'yow', 'shyue', 'liang', 'jeng', 'cheng', 'chern', 'jaw', 'jou', 'gwo', 'guo'}

JP_ROLE = re.compile(r"japan|\bldp\b|\bdiet\b|okinawa|tokyo|ryukyu|komeito|jsdf|self-defen|nippon|"
                     r"hokkaido|fukuoka|osaka|kyoto|nagasaki|ishigaki|yonaguni|matsubara", re.I)
JP_SURNAMES = {
    'abe', 'akiba', 'akimoto', 'ando', 'aoki', 'arai', 'araki', 'asao', 'aso', 'baba', 'chiba', 'edano', 'endo', 'eto',
    'ezaki', 'fujii', 'fujimoto', 'fujita', 'fujiwara', 'fukuda', 'funakoshi', 'furukawa', 'furuya', 'gabe',
    'hagiuda', 'hamada', 'hamaguchi', 'hanyu', 'hara', 'harada', 'haraguchi', 'hasegawa', 'hashimoto', 'hatoyama',
    'hatta', 'hayashi', 'hibino', 'higuchi', 'hiranuma', 'hirano', 'hirasawa', 'honda', 'hosoda', 'hyakuta', 'ichikawa',
    'ikeda', 'imai', 'inoue', 'isa', 'ishiba', 'ishihara', 'ishii', 'ishikawa', 'isozaki', 'ito', 'iuchi', 'iwasaki',
    'iwata', 'iwaya', 'kaieda', 'kakizawa', 'kamikawa', 'kanai', 'kanda', 'kaneko', 'katano', 'katayama', 'kato',
    'katsura', 'kawamura', 'kawashima', 'kihara', 'kikawada', 'kikuchi', 'kimura', 'kinoshita', 'kishi', 'kishida',
    'kitamura', 'kitaoka', 'kobayashi', 'koga', 'kohara', 'koike', 'koizumi', 'kojima', 'kokubun', 'kondo', 'konishi',
    'kono', 'kosha', 'kubo', 'kudo', 'kurosawa', 'maeda', 'maehara', 'maruyama', 'masuda', 'matayoshi', 'matsubara',
    'matsuda', 'matsui', 'matsukawa', 'matsumoto', 'matsuno', 'matsuo', 'matsushima', 'miki', 'miura', 'miyamoto',
    'miyazaki', 'miyazawa', 'mochida', 'mori', 'morita', 'moriyama', 'motegi', 'murakami', 'murata', 'nagashima',
    'nakagawa', 'nakajima', 'nakamura', 'nakano', 'nakasone', 'nakatani', 'nakayama', 'nishida', 'nishimura',
    'nishino', 'nishiumi', 'noda', 'noguchi', 'nomura', 'nukaga', 'ogasawara', 'ogawa', 'ohno', 'okada', 'okamoto',
    'okuma', 'ono', 'onoda', 'onodera', 'oshima', 'ota', 'otsuka', 'ozaki', 'ozato', 'saito', 'sakai', 'sakamoto',
    'sakurada', 'sakurai', 'sano', 'sasaki', 'sato', 'sawai', 'seki', 'sekiguchi', 'seko', 'sera', 'shiba',
    'shibasaki', 'shibata', 'shii', 'shimada', 'shimizu', 'shimomura', 'shindo', 'shiozaki', 'shirakawa', 'suga',
    'sugawara', 'sugimoto', 'sugita', 'sugiyama', 'sumi', 'suzuki', 'taira', 'takada', 'takagi', 'takahashi',
    'takaichi', 'takara', 'takeda', 'takei', 'takenouchi', 'takeuchi', 'takinami', 'tamaki', 'tamura', 'tanaka',
    'taniguchi', 'tomita', 'uchida', 'uechi', 'ueda', 'ueno', 'umemura', 'wada', 'watanabe', 'yaita', 'yamada',
    'yamagiwa', 'yamaguchi', 'yamamoto', 'yamanaka', 'yamao', 'yamashita', 'yamatani', 'yamazaki', 'yanaihara',
    'yokota', 'yokoyama', 'yoshida', 'yoshimura'}
ENGLISH_GIVEN = {
    'aaron', 'adam', 'alan', 'albert', 'alex', 'alexander', 'alice', 'allen', 'amy', 'andrew', 'andy', 'angela',
    'anita', 'ann', 'anna', 'anne', 'annie', 'anthony', 'april', 'arthur', 'audrey', 'austin', 'barry', 'ben',
    'benjamin', 'betty', 'bill', 'bob', 'brian', 'bruce', 'carl', 'carol', 'catherine', 'cathy', 'charles', 'chris',
    'christina', 'christine', 'cindy', 'claire', 'connie', 'daniel', 'david', 'dennis', 'derek', 'diane', 'don',
    'doris', 'douglas', 'ed', 'eddie', 'edward', 'elizabeth', 'emily', 'enoch', 'eric', 'eugene', 'eva', 'felix',
    'fiona', 'frank', 'fred', 'freddy', 'gary', 'gavin', 'george', 'gloria', 'gordon', 'grace', 'hannah', 'harry',
    'helen', 'henry', 'herman', 'howard', 'ian', 'irina', 'iris', 'ivy', 'jack', 'jacky', 'james', 'jamie', 'jane',
    'janet', 'jason', 'jeff', 'jeffrey', 'jenni', 'jenny', 'jensen', 'jeremy', 'jerry', 'jesse', 'jessica', 'jill',
    'jimmy', 'joan', 'joanne', 'joe', 'john', 'johnny', 'jonathan', 'joseph', 'josephine', 'joyce', 'judy', 'julia',
    'julian', 'justin', 'karen', 'karin', 'kate', 'kathy', 'keith', 'kelly', 'ken', 'kenji', 'kenneth', 'kenny',
    'kent', 'kevin', 'kit', 'larry', 'laura', 'lawrence', 'lily', 'linda', 'lisa', 'louis', 'louise', 'lucy',
    'maggie', 'margaret', 'mark', 'martin', 'mary', 'matthew', 'mavis', 'max', 'may', 'michael', 'michelle', 'monica',
    'morgan', 'nancy', 'nelson', 'nick', 'nina', 'oliver', 'olivia', 'oscar', 'patrick', 'paul', 'pauline', 'peggy',
    'peter', 'philip', 'puma', 'ralph', 'raymond', 'rebecca', 'rex', 'richard', 'ricky', 'rita', 'robert', 'ronan',
    'rose', 'roy', 'ryan', 'sally', 'sam', 'sandy', 'sarah', 'scott', 'sean', 'sharon', 'shirley', 'sidney', 'simon',
    'sophia', 'stanley', 'stella', 'stephen', 'steve', 'steven', 'sue', 'susan', 'sylvia', 'ted', 'teresa', 'terry',
    'thomas', 'tiffany', 'tim', 'tina', 'tom', 'tommy', 'tony', 'vanessa', 'vera', 'vicky', 'victor', 'vincent',
    'vivian', 'vivienne', 'walter', 'warren', 'wayne', 'wellington', 'wendy', 'william', 'wilson', 'winnie',
    'yolanda', 'yvonne'}


def _py_initial(py):
    return next((i for i in _INITIALS if py.startswith(i)), '')


def _tok_initial(tok):
    t = tok.lower()
    for i in ('zh', 'ch', 'sh', 'hs', 'ts', 'tz'):
        if t.startswith(i):
            return i
    return t[:1]


def _readings(ch):
    if _pinyin is None:
        return []
    return list({s for s in sum(_pinyin(ch, style=_Style.NORMAL, heteronym=True), [])})


def _consistent(tok, ch):
    ti = _tok_initial(tok)
    return any(ti in _INIT_OK.get(_py_initial(p), set()) for p in _readings(ch))


def _segment(tok):
    """Split a letter string into known syllables (fewest pieces); None when it cannot be split."""
    t = tok.lower().replace("'", '')
    if not t.isalpha():
        return None
    best = [None] * (len(t) + 1)
    best[0] = []
    for i in range(len(t)):
        if best[i] is None:
            continue
        for j in range(min(len(t), i + 6), i, -1):
            if t[i:j] in _SYLLABLES and (best[j] is None or len(best[i]) + 1 < len(best[j])):
                best[j] = best[i] + [t[i:j]]
    return best[len(t)]


def _given_syllables(tokens):
    out = []
    for tk in tokens:
        for part in tk.split('-'):
            seg = _segment(part)
            if seg is None:
                return None
            out.extend(seg)
    return out


def chinese_reading(zh, en):
    """('S'|'G', surname_token, [given_syllable, given_syllable]) when `en` reads as a
    romanisation of the three-character name `zh` surname-first ('S') or given-first
    ('G'); None otherwise (adopted English name, another person, unreadable)."""
    if _pinyin is None or not CJK3.match(zh or ''):
        return None
    toks = (en or '').split()
    if not 2 <= len(toks) <= 3:
        return None
    for order, sur, given in (('S', toks[0], toks[1:]), ('G', toks[-1], toks[:-1])):
        if '-' in sur:
            continue
        seg = _segment(sur)
        if not seg or len(seg) != 1 or not _consistent(sur, zh[0]):
            continue
        g = _given_syllables(given)
        if g and len(g) == 2 and _consistent(g[0], zh[1]) and _consistent(g[1], zh[2]):
            return (order, sur, g)
    return None


def tw_form(sur, given):
    return f"{sur.capitalize()} {given[0].capitalize()}-{given[1].lower()}"


def style_change(zh, en, side=None, role=None):
    """(styled_en, rule) — rule is None when nothing changed."""
    en = ' '.join((en or '').split())
    if not en:
        return en, None
    toks = en.split()
    if ',' in en:
        if en.count(',') > 1 or len(toks) != 2:
            return en, None                       # not a single person — the caller refuses it
        en = en.replace(',', '')
        toks = en.split()
        rule = 'comma'
    else:
        rule = None
    side_eff = side if side in ('TW', 'PRC', 'OTHER') else side_from_role(role or '')
    if side_eff == 'PRC' or toks[0].lower() in ENGLISH_GIVEN:
        return en, rule
    low = [t.lower() for t in toks]
    zh = (zh or '').strip()
    jp = bool(JP_ROLE.search(role or '')) or any(t in JP_SURNAMES for t in low)
    if jp and len(toks) == 2 and '-' not in en and chinese_reading(zh, en) is None:
        if low[0] in JP_SURNAMES:
            return en, rule
        if low[1] in JP_SURNAMES:
            return f"{toks[1]} {toks[0]}", 'japanese'
        return en, rule
    if not CJK3.match(zh) or zh[:2] in _COMPOUND_SURNAMES:
        return en, rule
    rd = chinese_reading(zh, en)
    if rd is None or hanyu_markers(en):
        return en, rule                           # adopted name, or a Hanyu form (Ed's call)
    order, sur, given = rd
    want = tw_form(sur, given)
    if want == en:
        return en, rule
    if side_eff is None and '-' not in en and order == 'S':
        return en, rule                           # could be PRC style; no evidence either way
    return want, ('order' if order == 'G' else 'style')


def style_name(zh, en, side=None, role=None):
    """The house-style English form of `en` for the Chinese name `zh`."""
    return style_change(zh, en, side, role)[0]
