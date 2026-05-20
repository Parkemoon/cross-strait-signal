"""Unit tests for the MAC YoY percentage parser.

MAC publishes most YoY columns with a '%' suffix (e.g. "30.6%"), but the
'TW visitors to PRC' growth column writes a decimal fraction without '%'
(e.g. "0.103" meaning 10.3%). This parser bridges both formats; misreads
here corrupt every YoY value in the economy tab.
"""
from scraper.scrapers.mac_economic_scraper import parse_pct


def test_percent_suffix_returns_face_value():
    assert parse_pct("30.6%") == 30.6


def test_negative_percent_suffix():
    assert parse_pct("-12.4%") == -12.4


def test_decimal_fraction_under_one_is_scaled_to_percent():
    """0.103 with no '%' → 10.3 (MAC's idiosyncratic encoding)."""
    assert abs(parse_pct("0.103") - 10.3) < 1e-9


def test_negative_decimal_fraction_under_one_is_scaled():
    assert abs(parse_pct("-0.05") - (-5.0)) < 1e-9


def test_value_exactly_one_is_preserved():
    """Exactly 1.0 (no '%') is a real 100% reading, not 1% — don't scale it."""
    assert parse_pct("1.0") == 1.0


def test_value_above_one_is_preserved():
    assert parse_pct("23.4") == 23.4


def test_dash_is_treated_as_missing():
    assert parse_pct("－") is None
    assert parse_pct("-") is None
    assert parse_pct("") is None


def test_whitespace_and_quotes_are_stripped():
    assert parse_pct(' "30.6%" ') == 30.6


def test_quoted_decimal_fraction_still_scales():
    assert abs(parse_pct('"0.05"') - 5.0) < 1e-9


def test_unparseable_returns_none():
    assert parse_pct("not-a-number") is None
