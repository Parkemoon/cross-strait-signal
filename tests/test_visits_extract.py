"""Scope gate + validation for the cross-strait visits side-extract
(scraper/processors/visits_extract.validate_visit). Pure function, no DB,
no Gemini — the point is that the cross-strait-only rule holds in CODE
whatever the model emits."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")

from scraper.processors.visits_extract import (  # noqa: E402
    AFFILIATIONS, PRC_AFFILIATIONS, TW_AFFILIATIONS, side_of, validate_visit,
)
from api.routes import visits as visits_api  # noqa: E402


def _row(**over):
    base = {
        "direction": "TW_TO_PRC", "visit_status": "reported",
        "visitor_name_en": "Hsia Li-yan", "visitor_name_zh": "夏立言",
        "visitor_title": "KMT Vice Chairman", "visitor_affiliation": "KMT",
        "visit_level": "party_senior", "counterpart_name_en": "Wang Huning",
        "counterpart_affiliation": "CCP", "event_name_en": "Straits Forum",
        "location_label": "Xiamen", "start_date": "2026-06-15", "end_date": "2026-06-17",
        "purpose_en": "Led the KMT delegation to the Straits Forum.", "confidence": 0.9,
    }
    base.update(over)
    return base


def test_enums_mirror_api():
    assert AFFILIATIONS == visits_api.AFFILIATIONS
    assert TW_AFFILIATIONS == visits_api.TW_AFFILIATIONS
    assert PRC_AFFILIATIONS == visits_api.PRC_AFFILIATIONS


def test_happy_path():
    r = validate_visit(_row())
    assert r["visitor_side"] == "TW" and r["direction"] == "TW_TO_PRC"
    assert r["start_date"] == "2026-06-15" and r["end_date"] == "2026-06-17"
    assert r["confidence"] == 0.9


def test_side_derived_from_affiliation():
    assert side_of("kmt") == "TW" and side_of("TAO") == "PRC" and side_of("USA") is None


@pytest.mark.parametrize("over", [
    {"visitor_affiliation": "US_CONGRESS"},                     # unknown affiliation → can't prove scope
    {"visitor_affiliation": "KMT", "counterpart_affiliation": "DPP"},  # same side both ends
    {"direction": "PRC_TO_TW", "visitor_affiliation": "KMT"},   # direction contradicts side
    {"direction": "TW_TO_PRC", "visitor_affiliation": "TAO"},
    {"direction": "THIRD_VENUE", "visitor_affiliation": "CCP"}, # third-venue visitor must be TW side
    {"direction": "TW_TO_US"},                                  # not an enum
    {"visitor_name_en": None, "visitor_name_zh": None, "delegation_desc_en": None},
])
def test_scope_gate_drops(over):
    assert validate_visit(_row(**over)) is None


def test_junk_counterpart_affiliation_is_nulled_not_fatal():
    r = validate_visit(_row(counterpart_affiliation="SOME_ORG"))
    assert r is not None and r["counterpart_affiliation"] is None


def test_enum_fallbacks_and_dates():
    r = validate_visit(_row(visit_level="emperor", visit_status="maybe", start_date="June 2026",
                            end_date="2026-06-01", confidence="high"))
    assert r["visit_level"] == "other" and r["visit_status"] == "reported"
    assert r["start_date"] is None and r["end_date"] == "2026-06-01" and r["confidence"] is None


def test_end_before_start_dropped():
    r = validate_visit(_row(start_date="2026-06-15", end_date="2026-06-10"))
    assert r["end_date"] is None


def test_cjk_guard_on_english_fields():
    r = validate_visit(_row(purpose_en="率團出席海峽論壇並會見王滬寧", visitor_title="國民黨副主席"))
    assert r["purpose_en"] is None and r["visitor_title"] is None
