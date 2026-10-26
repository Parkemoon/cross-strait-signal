"""Tests for MND daily PLA activity text parsing (`mnd_incursion_scraper.py`)."""
from scraper.scrapers.mnd_incursion_scraper import parse_summary


def test_parse_classic_median_crossing():
    text = (
        "迄0600時止，偵獲共機18架次（逾越中線進入北部、中部、西南及東部空域15架次）、"
        "共艦11艘及公務船3艘，持續在臺海周邊活動。"
    )
    assert parse_summary(text) == {
        "aircraft_total": 18,
        "aircraft_intruded": 15,
        "aircraft_zones": "N,C,SW,E",
        "vessels_total": 11,
        "coast_guard_total": 3,
    }


def test_parse_gong_and_ji_count_prefixes():
    # Sep 2026: 共N架次
    text_gong = (
        "迄0600時止，偵獲共機23架次（逾越中線進入北部、中部及西南空域共16架次）、"
        "共艦7艘及公務船7艘，持續在臺海周邊活動。"
    )
    assert parse_summary(text_gong) == {
        "aircraft_total": 23,
        "aircraft_intruded": 16,
        "aircraft_zones": "N,C,SW",
        "vessels_total": 7,
        "coast_guard_total": 7,
    }

    # Oct 2026: 計N架次 (and singular 計1架)
    text_ji = (
        "迄0600時止，偵獲共機3架次（逾越中線進入西南及東部空域計1架）、"
        "共艦6艘及公務船9艘，持續在臺海周邊活動。"
    )
    assert parse_summary(text_ji) == {
        "aircraft_total": 3,
        "aircraft_intruded": 1,
        "aircraft_zones": "SW,E",
        "vessels_total": 6,
        "coast_guard_total": 9,
    }


def test_parse_omitted_kongyu_and_no_median_crossing():
    # Omitted 空域 after sector name + 計 prefix (2026-10-18)
    text_no_kongyu = (
        "迄0600時止，偵獲共機2架次（逾越中線進入北部及中部計2架次）、"
        "共艦5艘及公務船9艘，持續在臺海周邊活動。"
    )
    assert parse_summary(text_no_kongyu) == {
        "aircraft_total": 2,
        "aircraft_intruded": 2,
        "aircraft_zones": "N,C",
        "vessels_total": 5,
        "coast_guard_total": 9,
    }

    # ADIZ entry without 逾越中線 and without 空域 (2026-10-08)
    text_adiz_only = (
        "迄0600時止，偵獲共機3架次（進入西南1架次）、"
        "共艦6艘及公務船1艘，持續在臺海周邊活動。"
    )
    assert parse_summary(text_adiz_only) == {
        "aircraft_total": 3,
        "aircraft_intruded": 1,
        "aircraft_zones": "SW",
        "vessels_total": 6,
        "coast_guard_total": 1,
    }


def test_parse_quiet_days_and_zero_intrusion_sorties():
    # Explicit quiet day
    quiet = (
        "迄0600時止，偵獲共艦5艘及公務船8艘，持續在臺海周邊活動。"
        "三、上述期間未偵獲共機，故無提供航跡圖。"
    )
    assert parse_summary(quiet) == {
        "aircraft_total": 0,
        "aircraft_intruded": 0,
        "aircraft_zones": None,
        "vessels_total": 5,
        "coast_guard_total": 8,
    }

    # Sorties detected around the strait, no intrusion parenthetical (2026-09-27)
    no_intrusion = (
        "迄0600時止，偵獲共機2架次、共艦5艘及公務船6艘，持續在臺海周邊活動。"
    )
    assert parse_summary(no_intrusion) == {
        "aircraft_total": 2,
        "aircraft_intruded": 0,
        "aircraft_zones": None,
        "vessels_total": 5,
        "coast_guard_total": 6,
    }


def test_parse_unrecognised_parenthetical_stays_none():
    # Guard: if MND changes parenthetical wording again, aircraft_intruded
    # must stay None (triggering the health check) rather than defaulting to 0.
    future_shift = (
        "迄0600時止，偵獲共機12架次（其中越過海峽中線計8架次）、"
        "共艦6艘及公務船3艘，持續在臺海周邊活動。"
    )
    res = parse_summary(future_shift)
    assert res["aircraft_total"] == 12
    assert res["aircraft_intruded"] is None
