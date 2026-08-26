"""Regression tests for the Coast Guard tracker data layer (2026-08-26 audit)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scraper.scrapers import cga_stats_scraper as cga  # noqa: E402
from scraper.scrapers.gfw_coast_guard import classify  # noqa: E402


def test_ccg_name_forms_under_chinese_or_spoofed_flags():
    assert classify("CHINA COASTGUARD2101", "CHN") == ("CCG", "2101")
    assert classify("ZHONGGUOHAIJING 2501", "CHN") == ("CCG", "2501")
    assert classify("HAI JING 2201", "CHN") == ("CCG", "2201")
    assert classify("CHINACOASTGUARD14513", None) == ("CCG", "14513")     # Venezuelan MID, no flag
    assert classify("CHINACOASTGUARD14531", "GRD") == ("CCG", "14531")    # spoofed Grenada flag


def test_hai_jing_is_not_ccg_under_taiwan_flag():
    # 416002727 "HAI JING" is a Taiwanese vessel — 84 false hull-days before the fix.
    assert classify("HAI JING", "TWN") == (None, None)
    assert classify("HAI JING NO.1", "TWN") == (None, None)
    assert classify("CG5002 HSINCHU", "TWN") == ("CGA", "5002")
    assert classify("CGC MIDGETT", "USA") == ("USCG", None)


def _fake_table(rows):
    """rows: list of (label, e_prc) → shape parse_table/_record expect."""
    return [(label, [None, None, e, 0]) for label, e in rows]


def test_yearbook_bare_gregorian_year_row_sets_month_context(monkeypatch):
    # Shape of the 114年 yearbook 表8-1: ROC-labelled history, then a bare "2025"
    # annual row, then that year's months. Before the fix the "2025" row was
    # skipped and the months inherited report_year-1.
    table = _fake_table([("112年2023", 1006), ("113年2024", 1135), ("2025", 907), ("1月", 99), ("2月", 74)])
    monkeypatch.setattr(cga, "parse_table", lambda _pdf: table)
    monkeypatch.setattr(cga, "_record", lambda cells: {"e_prc": cells[2], "d_prc": cells[3]})
    monkeypatch.setattr(cga, "_categories", lambda v: [{"category": "fishing_prc", "cases": None,
                                                        "expelled": v["e_prc"], "detained": v["d_prc"]}])
    rows = {(r["period"], r["granularity"]): r["expelled"] for r in cga.rows_by_month(b"", 2025)}
    assert rows[("2025", "year")] == 907
    assert rows[("2025-01", "month")] == 99
    assert rows[("2024", "year")] == 1135
    assert ("2024-01", "month") not in rows


def test_monthly_report_month_wrap_advances_year(monkeypatch):
    # 114年10月 report: 113年 annual, Oct–Dec 2024, 114年 YTD annual, Jan–Oct 2025.
    table = _fake_table([("113年2024", 1135), ("10月", 109), ("11月", 102), ("12月", 98),
                         ("114年2025", 642), ("1月", 99), ("10月", 136)])
    monkeypatch.setattr(cga, "parse_table", lambda _pdf: table)
    monkeypatch.setattr(cga, "_record", lambda cells: {"e_prc": cells[2], "d_prc": cells[3]})
    monkeypatch.setattr(cga, "_categories", lambda v: [{"category": "fishing_prc", "cases": None,
                                                        "expelled": v["e_prc"], "detained": v["d_prc"]}])
    rows = {r["period"]: r["expelled"] for r in cga.rows_by_month(b"", 2025) if r["granularity"] == "month"}
    assert rows["2024-10"] == 109 and rows["2025-10"] == 136 and rows["2025-01"] == 99
