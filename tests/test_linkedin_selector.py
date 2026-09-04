"""Unit tests for shared/linkedin_selector.py (ranking + exclusion, pure) and
the pure parts of scraper/processors/linkedin_draft.py (assembly + rule
validation — no Gemini call; the module builds the client at import, so a
placeholder key is set the same way tests/test_visits_extract.py does)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")

from shared.linkedin_selector import (  # noqa: E402
    breadth_score, describe_cluster, dominant_topic, exclusion_reasons,
    outlet_of, rank_clusters, side_of,
)

_N = {'n': 0}


def art(cluster, source, place, bias, score=0.0, topic='DIP_STATEMENT', approved=1,
        published='2026-09-01T08:00:00', review=0, resolved=0, quote=None):
    _N['n'] += 1
    return {
        'id': _N['n'], 'cluster_id': cluster, 'published_at': published, 'url': f'https://x/{_N["n"]}',
        'language': 'zh-tw', 'title_en': f'{source} on {cluster}', 'analyst_approved': approved,
        'source_name': source, 'place': place, 'bias': bias, 'topic_primary': topic,
        'sentiment': 'neutral', 'sentiment_score': score, 'urgency': 'routine',
        'summary_en': 'Summary.', 'key_quote': quote, 'key_quote_en': None,
        'is_new_formulation': 0, 'is_escalation_signal': 0,
        'needs_human_review': review, 'review_resolved': resolved,
    }


def tw(cluster, source='LTN Politics', bias='green', **kw):
    return art(cluster, source, 'TW', bias, **kw)


def prc(cluster, source='Xinhua Chinese', bias='state_official', **kw):
    return art(cluster, source, 'PRC', bias, **kw)


# ── sides / outlets ─────────────────────────────────────────────────────────

def test_side_of_uses_place_for_tw_and_bias_for_prc():
    assert side_of('TW', 'green') == 'TW'
    assert side_of('TW', 'blue') == 'TW'
    assert side_of('TW', 'centrist') == 'TW'          # My-Formosa
    assert side_of('SG', 'centrist') is None          # Zaobao is not Taiwan-side
    assert side_of('UK', 'centrist') is None          # BBC Chinese
    assert side_of('PRC', 'state_nationalist') == 'PRC'
    assert side_of('HK', 'china_centrist') == 'PRC'   # Ming Pao
    assert side_of('HK', 'state_official') == 'PRC'   # RTHK


def test_outlet_collapses_sections():
    assert outlet_of('UDN Breaking') == outlet_of('UDN International') == 'United Daily News'
    assert outlet_of('LTN Defence') == outlet_of('LTN World')
    assert outlet_of('CT Opinion') == 'China Times'
    assert outlet_of('Ming Pao Editorial') == 'Ming Pao'
    assert outlet_of('Guancha') == 'Guancha'


# ── breadth ─────────────────────────────────────────────────────────────────

def test_breadth_three_and_three_beats_six_and_one():
    assert breadth_score(3, 3) > breadth_score(6, 1)
    assert breadth_score(3, 3) > breadth_score(4, 2)
    assert breadth_score(0, 5) == 0.0


def test_breadth_counts_outlets_not_articles():
    rows = [tw('c', 'UDN'), tw('c', 'UDN Breaking'), tw('c', 'UDN International'), prc('c')]
    c = describe_cluster('c', rows)
    assert c['tw_outlets'] == ['United Daily News']
    assert c['tw_n'] == 3
    assert c['breadth'] == breadth_score(1, 1)


# ── ranking ─────────────────────────────────────────────────────────────────

def test_ranking_prefers_balanced_breadth():
    rows = []
    # balanced: 3 TW outlets + 3 PRC outlets
    for s in ('LTN Politics', 'UDN', 'CT Politics'):
        rows.append(tw('bal', s))
    for s in ('Xinhua Chinese', 'Global Times', 'Guancha'):
        rows.append(prc('bal', s))
    # lopsided: 6 TW outlets + 1 PRC outlet, more articles overall
    for s, b in (('LTN Politics', 'green'), ('CNA Politics', 'green_leaning'), ('UDN', 'blue'),
                 ('CT Politics', 'blue'), ('YDN', 'green_leaning'), ('My-Formosa', 'centrist')):
        rows.append(tw('lop', s, b))
    rows.append(prc('lop'))
    ranked, excluded = rank_clusters(rows)
    assert [c['cluster_id'] for c in ranked] == ['bal', 'lop']
    assert excluded == []
    assert ranked[0]['rank'] == 1 and ranked[1]['rank'] == 2


def test_tiebreak_divergence_then_article_count():
    rows = [
        # A: same breadth, divergent sides
        tw('A', score=-0.8), prc('A', score=+0.6),
        # B: same breadth, both neutral, but more articles
        tw('B', score=0.0), prc('B', score=0.0), prc('B', 'Xinhua Chinese', score=0.0),
        # C: same breadth, same divergence as B, fewer articles
        tw('C', score=0.0), prc('C', score=0.0),
    ]
    ranked, _ = rank_clusters(rows)
    assert [c['cluster_id'] for c in ranked] == ['A', 'B', 'C']
    assert ranked[0]['divergence'] == pytest.approx(1.4)


def test_top_n_and_factors_exposed():
    rows = []
    for cid in ('a', 'b', 'c', 'd'):
        rows += [tw(cid), prc(cid)]
    ranked, _ = rank_clusters(rows, top_n=3)
    assert len(ranked) == 3
    for k in ('breadth', 'divergence', 'tw_outlets', 'prc_outlets', 'tw_mean', 'prc_mean',
              'dominant_topic', 'n_articles', 'article_ids'):
        assert k in ranked[0]


# ── exclusion ───────────────────────────────────────────────────────────────

def test_excludes_missing_side():
    rows = [tw('onlytw'), tw('onlytw', 'UDN'), prc('onlyprc'), prc('onlyprc', 'Guancha'),
            tw('intl'), art('intl', 'Zaobao Cross-Strait', 'SG', 'centrist')]
    ranked, excluded = rank_clusters(rows)
    assert ranked == []
    reasons = {c['cluster_id']: c['excluded_because'] for c in excluded}
    assert reasons['onlytw'] == ['no_prc_side']
    assert reasons['onlyprc'] == ['no_tw_side']
    assert reasons['intl'] == ['no_prc_side']      # Zaobao counts for neither side


def test_excludes_domestic_tw_dominant_topic_only_when_dominant():
    rows = [tw('dom', topic='POL_DOMESTIC_TW'), tw('dom', 'UDN', topic='POL_DOMESTIC_TW'),
            prc('dom', topic='POL_TONGDU'),
            tw('ok', topic='POL_DOMESTIC_TW'), prc('ok', topic='POL_TONGDU'),
            prc('ok', 'Guancha', topic='POL_TONGDU')]
    ranked, excluded = rank_clusters(rows)
    assert [c['cluster_id'] for c in ranked] == ['ok']
    assert excluded[0]['cluster_id'] == 'dom'
    assert excluded[0]['excluded_because'] == ['excluded_topic:POL_DOMESTIC_TW']


def test_dominant_topic_tie_goes_to_earliest():
    rows = [tw('t', topic='POL_DOMESTIC_TW', published='2026-09-01T09:00:00'),
            prc('t', topic='MIL_EXERCISE', published='2026-09-01T08:00:00')]
    assert dominant_topic(rows) == 'MIL_EXERCISE'


def test_pending_members_allowed_but_invisible():
    """Ed 2026-09-04: pending members don't disqualify a cluster, but only
    approved members feed sides / outlets / means / material."""
    rows = [tw('pend', score=-0.6), prc('pend', score=0.2), prc('pend', 'Guancha', score=-0.9, approved=0),
            tw('rev'), prc('rev', review=1, resolved=0),               # only PRC article is in review
            tw('resolved'), prc('resolved', review=1, resolved=1),
            tw('none', approved=0), prc('none', approved=0)]
    ranked, excluded = rank_clusters(rows)
    assert [c['cluster_id'] for c in ranked] == ['pend', 'resolved']
    pend = ranked[0]
    assert pend['n_articles'] == 2 and pend['pending_n'] == 1 and pend['n_members'] == 3
    assert pend['prc_outlets'] == ['Xinhua Chinese']                    # Guancha row unseen
    assert pend['prc_mean'] == pytest.approx(0.2)                       # -0.9 not averaged in
    assert len(pend['article_ids']) == 3 and len(pend['approved_ids']) == 2
    reasons = {c['cluster_id']: c['excluded_because'] for c in excluded}
    assert reasons['rev'] == ['no_prc_side']
    assert reasons['none'] == ['no_approved_members', 'no_tw_side', 'no_prc_side']


def test_never_reproposes_same_cluster_or_overlapping_articles():
    a1, a2 = tw('x'), prc('x')
    rows = [a1, a2, tw('y'), prc('y')]
    ranked, _ = rank_clusters(rows)
    assert len(ranked) == 2
    proposed = {'cluster_ids': {'x'}, 'article_ids': set()}
    ranked, excluded = rank_clusters(rows, proposed)
    assert [c['cluster_id'] for c in ranked] == ['y']
    assert excluded[0]['excluded_because'] == ['already_proposed:cluster']
    # re-clustered under a new id but sharing an article → still excluded
    rows2 = [dict(a1, cluster_id='x2'), prc('x2', 'Guancha'), tw('y'), prc('y')]
    proposed = {'cluster_ids': {'x'}, 'article_ids': {a1['id']}}
    ranked, excluded = rank_clusters(rows2, proposed)
    assert [c['cluster_id'] for c in ranked] == ['y']
    assert excluded[0]['excluded_because'] == ['already_proposed:shares_articles']


def test_multiple_reasons_reported_together():
    c = describe_cluster('m', [tw('m', topic='POL_DOMESTIC_TW'), tw('m', 'UDN', topic='POL_DOMESTIC_TW', approved=0)])
    assert exclusion_reasons(c) == ['excluded_topic:POL_DOMESTIC_TW', 'no_prc_side']
    assert c['pending_n'] == 1


# ── draft assembly / validation (pure) ──────────────────────────────────────

from scraper.processors import linkedin_draft as draft  # noqa: E402


def test_assemble_and_validate_post():
    rows = [tw('q', score=-0.6, quote='台灣是主權獨立的國家'), prc('q', score=-0.4, quote='台湾是中国的一部分')]
    c = describe_cluster('q', rows)
    parts = {'headline': 'Beijing and Taipei trade statements on sovereignty',
             'what_happened': 'Both governments issued statements.',
             'tw_framing': 'Liberty Times quoted the MAC: 台灣是主權獨立的國家 (Taiwan is a sovereign, independent country).',
             'prc_framing': 'Xinhua repeated the TAO line.'}
    post = draft.assemble_post(parts, c)
    assert post.startswith(parts['headline'] + '\n')
    assert 'Taiwan-side framing:' in post and 'PRC-side framing:' in post
    assert '-0.60, hostile' in post and '-0.40, hostile' in post
    assert post.rstrip().endswith(draft.SITE_URL)
    assert draft.validate_post(post, c) == []

    bad = post.replace('Both governments', 'Both governments — allegedly') + ' #taiwan'
    bad = bad.replace('台灣是主權獨立的國家', '台灣是主權獨立的國家，北京不同意')
    problems = draft.validate_post(bad, c)
    assert any('em-dash' in p for p in problems)
    assert any('hashtag' in p for p in problems)
    assert any('not found in any stored key quote' in p for p in problems)

    long_first = ('x' * 250) + post
    assert any('first line' in p for p in draft.validate_post(long_first, c))
    assert any('limit 1300' in p for p in draft.validate_post(post + 'y' * 1300, c))
