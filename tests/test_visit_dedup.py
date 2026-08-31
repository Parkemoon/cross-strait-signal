"""Unit tests for shared/visit_dedup.py (pure clustering/keeper logic)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.visit_dedup import cluster_visits, plan_dedup, richness, visitor_key  # noqa: E402

_BASE = {
    'visit_status': 'reported', 'visitor_name_en': 'Cheng Li-wun',
    'visitor_name_zh': '鄭麗文', 'visitor_title': None, 'visitor_affiliation': 'KMT',
    'visitor_figure_id': 'cheng_liwun', 'delegation_desc_en': None,
    'counterpart_name_en': None, 'counterpart_name_zh': None, 'counterpart_title': None,
    'counterpart_affiliation': None, 'counterpart_figure_id': None,
    'event_name_en': None, 'event_name_zh': None, 'location_label': 'Beijing',
    'start_date': None, 'end_date': None, 'purpose_en': None, 'quote_zh': None,
    'confidence': 0.9, 'approval_status': 'pending', 'direction': 'TW_TO_PRC',
}


def row(id, eff, **kw):
    r = dict(_BASE, id=id, effective_date=eff)
    r.update(kw)
    return r


def test_script_variants_share_key_via_figure_id():
    a = row(1, '2026-04-01', visitor_name_zh='鄭麗文')
    b = row(2, '2026-04-02', visitor_name_zh='郑丽文')
    assert visitor_key(a) == visitor_key(b)


def test_direction_splits_key():
    a = row(1, '2026-04-01')
    b = row(2, '2026-04-01', direction='PRC_TO_TW')
    assert visitor_key(a) != visitor_key(b)


def test_chain_clusters_one_trip_and_splits_distinct_trips():
    rows = [row(1, '2026-04-01'), row(2, '2026-04-10'), row(3, '2026-04-28'),
            row(4, '2026-07-01')]  # 3 chains 9/18d apart; 4 is 64d later
    clusters = sorted(cluster_visits(rows), key=len, reverse=True)
    assert [len(c) for c in clusters] == [3, 1]
    assert {r['id'] for r in clusters[0]} == {1, 2, 3}


def test_keeper_prefers_approved_then_status_then_richness():
    sparse_approved = row(1, '2026-04-01', approval_status='approved',
                          location_label=None, confidence=0.3)
    rich_pending = row(2, '2026-04-02', counterpart_name_en='Xi Jinping',
                       start_date='2026-04-01', purpose_en='Met Xi.')
    assert richness(sparse_approved) > richness(rich_pending)

    planned_rich = row(3, '2026-04-01', visit_status='planned',
                       counterpart_name_en='Xi Jinping', purpose_en='Will meet.')
    reported_sparse = row(4, '2026-04-02')
    assert richness(reported_sparse) > richness(planned_rich)

    generic_loc = row(5, '2026-04-01', location_label='Mainland China')
    specific_loc = row(6, '2026-04-02', location_label='Nanjing')
    assert richness(specific_loc) > richness(generic_loc)


def test_plan_marks_only_pending_dupes():
    approved = row(1, '2026-04-01', approval_status='approved')
    approved2 = row(2, '2026-04-03', approval_status='approved',
                    counterpart_name_en='Wang Huning')
    pending = row(3, '2026-04-02')
    plans = plan_dedup([approved, approved2, pending])
    assert len(plans) == 1
    assert {r['id'] for r in plans[0]['dupes']} == {3}
    assert plans[0]['keeper']['approval_status'] == 'approved'


def test_singletons_and_keeper_only_clusters_are_omitted():
    assert plan_dedup([row(1, '2026-04-01')]) == []
    a = row(1, '2026-04-01', approval_status='approved')
    b = row(2, '2026-04-02', approval_status='approved')
    assert plan_dedup([a, b]) == []  # two approved rows: analyst's call


def test_no_figure_id_falls_back_to_en_then_zh_name():
    # en name preferred: script-agnostic, so trad/simp zh variants still meet
    a = row(1, '2026-04-01', visitor_figure_id=None, visitor_name_zh='張榮恭',
            visitor_name_en='Chang Jung-kung')
    b = row(2, '2026-04-02', visitor_figure_id=None, visitor_name_zh='张荣恭',
            visitor_name_en='Chang Jung-kung')
    assert visitor_key(a) == visitor_key(b)
    # zh fallback when no en name; whitespace-normalised
    c = row(3, '2026-04-01', visitor_figure_id=None, visitor_name_en=None, visitor_name_zh='張 榮恭')
    d = row(4, '2026-04-02', visitor_figure_id=None, visitor_name_en=None, visitor_name_zh='張榮恭')
    assert visitor_key(c) == visitor_key(d)
