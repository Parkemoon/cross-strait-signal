# -*- coding: utf-8 -*-
"""shared/article_dedup.py — same-outlet duplicate detection. The guard
cases are the real prod patterns the thresholds were measured against on
2026-08-24: the YDN daily PLA-dynamics series (identical title 133x,
templated content up to 0.80 similar day-to-day) must NEVER match; CT
Opinion re-pushes (0.99+ content, days apart) and same-day retitled
rewrites (content as low as 0.31 similar) must match."""
from shared.article_dedup import (
    choose_keeper,
    duplicate_rule,
    find_duplicate_groups,
    prepare,
)

_SEQ = iter(range(1, 1000))


def art(title, content, published_at, source_id=1, **flags):
    row = {
        'id': flags.pop('id', next(_SEQ)),
        'source_id': source_id,
        'title_original': title,
        'content_original': content,
        'published_at': published_at,
    }
    row.update(flags)
    p = prepare(row)
    assert p is not None
    return p


# A varied body comfortably over CONTENT_MIN_CHARS so the content rules
# engage — non-repeating so its trigram set is large enough for small
# perturbations to measure realistically.
BODY = (
    '國防部今日表示，中共解放軍持續在臺海周邊海、空域活動，國軍運用聯合情監偵手段嚴密掌握動態並妥適應處。'
    '陸委會發言人指出，北京當局近期加大對台灣的軍事與外交壓力，包括環島演訓、灰色地帶襲擾及國際場域打壓。'
    '學者分析認為，兩岸情勢升溫與美中戰略競爭密切相關，華府對台軍售與國會訪問頻率均較去年明顯增加。'
    '行政院長強調，政府將持續強化不對稱戰力與全社會防衛韌性，確保民主自由的生活方式不受威脅。'
    '在野黨立委則質疑國防預算編列效率，呼籲行政部門向立法院提出更完整的兵力整建說明與期程規劃。'
)


# --- R1: identical content, different URL/title, days apart ---

def test_r1_identical_content_across_days():
    a = art('時評》愧對抗日先烈', BODY, '2026-08-18T08:00:00')
    b = art('時評》愧對抗日先烈', BODY, '2026-08-20T21:00:00')
    assert duplicate_rule(a, b) == 'content-hash'


def test_r1_whitespace_variants_still_hash_equal():
    a = art('t1', BODY, '2026-08-18T08:00:00')
    b = art('t2', BODY.replace('，', '，\n '), '2026-08-19T08:00:00')
    # \n and space are stripped by normalisation; 、vs 。 would not be.
    assert duplicate_rule(a, b) == 'content-hash'


def test_r1_respects_seven_day_window():
    a = art('t', BODY, '2026-08-01T08:00:00')
    b = art('t', BODY, '2026-08-10T08:00:00')
    assert duplicate_rule(a, b) is None


def test_short_content_never_matches_on_content():
    # Below CONTENT_MIN_CHARS the fingerprint abstains — two thin rows
    # with the same boilerplate stub are not thereby dupes.
    a = art('完全不同的標題甲', '短文', '2026-08-18T08:00:00')
    b = art('毫無關聯的標題乙', '短文', '2026-08-18T09:00:00')
    assert duplicate_rule(a, b) is None


# --- R2: near-identical content within 72h ---

def _perturb(text, n):
    """Replace n well-spaced characters — dents trigram Jaccard slightly."""
    chars = list(text)
    step = max(1, len(chars) // (n + 1))
    for i in range(n):
        chars[(i + 1) * step - 1] = 'änöü'[i % 4]
    return ''.join(chars)


def test_r2_near_identical_content_matches():
    a = art('原標題', BODY, '2026-08-18T08:00:00')
    b = art('改過的標題完全不同', _perturb(BODY, 2), '2026-08-19T08:00:00')
    assert duplicate_rule(a, b) == 'content-sim'


def test_r2_templated_series_at_080_does_not_match():
    # Proxy for the YDN daily report: heavily-shared template, ~30% of
    # trigrams differ → similarity in the 0.6–0.8 band, below the 0.90 floor.
    a = art('中共解放軍臺海周邊海、空域動態', BODY, '2026-08-18T08:00:00')
    b = art('中共解放軍臺海周邊海、空域動態', _perturb(BODY, 30), '2026-08-19T08:00:00')
    assert duplicate_rule(a, b) is None


def test_r2_respects_72h_window():
    a = art('原標題', BODY, '2026-08-15T08:00:00')
    b = art('不同標題', _perturb(BODY, 2), '2026-08-19T09:00:00')
    assert duplicate_rule(a, b) is None


# --- R3: same-day title match, content may diverge ---

def test_r3_punctuation_title_variant_same_day():
    # Real pair 12221/12966: title differs only in spacing, content 0.62.
    a = art('批中國「害台」10措施  陸委會：極度廉價的騙局', BODY, '2026-04-17T08:00:00')
    b = art('批中國「害台」10措施 陸委會：極度廉價的騙局', _perturb(BODY, 40), '2026-04-17T12:00:00')
    assert duplicate_rule(a, b) == 'title-same-day'


def test_r3_fuzzy_title_rewrite_same_day():
    # Real pair 23552/24422: clause order swapped, content diverged.
    a = art('談台灣與中國沒有統一問題 吳志中：只有攻佔、侵略問題', BODY, '2026-04-26T08:00:00')
    b = art('吳志中：台灣與中國沒有統一問題 只有攻佔、侵略問題', _perturb(BODY, 40), '2026-04-26T12:00:00')
    assert duplicate_rule(a, b) == 'title-same-day'


def test_quiet_day_series_template_is_not_a_dupe():
    # Real prod false-positive pair 21567/22805 (caught in the 2026-08-24
    # dry-run): the QUIET-day variant of the YDN daily report is a 68-char
    # template where consecutive days differ by one digit — trigram
    # similarity 0.93 across different days' data. The 200-char content
    # floor makes both content rules abstain; the title rule can't fire
    # cross-day.
    a = art('中共解放軍臺海周邊海、空域動態',
            '（本報訊）國防部今日表示，迄0600時止，偵獲共機2架次及共艦7艘，持續在臺海周邊活動。'
            '國軍運用任務機、艦及岸置飛彈系統嚴密監控與應處。', '2026-04-24T06:00:00')
    b = art('中共解放軍臺海周邊海、空域動態',
            '（本報訊）國防部今日表示，迄0600時止，偵獲共機8架次及共艦7艘，持續在臺海周邊活動。'
            '國軍運用任務機、艦及岸置飛彈系統嚴密監控與應處。', '2026-04-25T06:00:00')
    assert duplicate_rule(a, b) is None


def test_r3_identical_title_different_day_is_not_a_dupe():
    # THE guard case: the YDN daily series — same title, consecutive
    # days, meaningfully different content. Title rule must not fire
    # across days; content at 0.6–0.8 must not fire either.
    a = art('中共解放軍臺海周邊海、空域動態', BODY, '2026-08-18T06:00:00')
    b = art('中共解放軍臺海周邊海、空域動態', _perturb(BODY, 30), '2026-08-19T06:00:00')
    assert duplicate_rule(a, b) is None


def test_r3_unrelated_same_day_titles_do_not_match():
    a = art('賴總統贈勳美眾院外委會榮譽主席', BODY, '2026-08-04T08:00:00')
    b = art('國防部公布共機動態', _perturb(BODY, 40), '2026-08-04T09:00:00')
    assert duplicate_rule(a, b) is None


# --- grouping + keeper ---

def test_cross_source_pairs_never_group():
    # Cross-outlet duplication is signal (agency copy, state messaging).
    a = art('同一篇報導', BODY, '2026-08-18T08:00:00', source_id=1)
    b = art('同一篇報導', BODY, '2026-08-18T09:00:00', source_id=2)
    groups, _ = find_duplicate_groups([a, b])
    assert groups == []


def test_transitive_repushes_form_one_group():
    # CT Opinion pattern: the same column re-pushed daily for 3 days —
    # day 1 and day 3 chain through day 2 even where a direct rule
    # (e.g. R2's 72h) might not link them.
    arts = [art('時評》別擋小朋友赴陸', BODY, f'2026-07-{d}T08:00:00')
            for d in ('30', '31')] + [art('時評》別擋小朋友赴陸', BODY, '2026-08-01T08:00:00')]
    groups, rules = find_duplicate_groups(arts)
    assert len(groups) == 1 and len(groups[0]) == 3
    assert all(rules[p['id']] == 'content-hash' for p in groups[0])


def test_keeper_prefers_approved_then_richer_then_earlier():
    plain = art('t', BODY, '2026-08-18T10:00:00')
    approved = art('t', BODY, '2026-08-18T11:00:00', analyst_approved=1)
    assert choose_keeper([plain, approved]) is approved

    rich = art('t', BODY + BODY, '2026-08-18T11:00:00')
    thin = art('t', BODY, '2026-08-18T10:00:00')
    assert choose_keeper([rich, thin]) is rich

    early = art('t', BODY, '2026-08-18T10:00:00')
    late = art('t', BODY, '2026-08-18T11:00:00')
    assert choose_keeper([early, late]) is early


def test_keeper_never_picks_hidden_over_visible():
    hidden = art('t', BODY + BODY, '2026-08-18T10:00:00',
                 is_hidden=1, analyst_approved=1)
    visible = art('t', BODY, '2026-08-18T11:00:00')
    assert choose_keeper([hidden, visible]) is visible


def test_keeper_protects_analyst_overrides():
    overridden = art('t', BODY, '2026-08-18T11:00:00', has_override=1)
    longer = art('t', BODY + BODY, '2026-08-18T10:00:00')
    assert choose_keeper([overridden, longer]) is overridden
