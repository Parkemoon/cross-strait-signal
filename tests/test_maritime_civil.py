"""Unit tests for the Maritime civilian-fleet + SAR layer (Phase 2g)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scraper.scrapers import gfw_civil  # noqa: E402
from scraper.scrapers.gfw_civil import aggregate_civil, aggregate_sar, keep_hull  # noqa: E402
from scraper.scrapers.gfw_coast_guard import classify  # noqa: E402

IS_CG = lambda n, f, t: classify(n, f, t)[0] is not None  # noqa: E731


def _cell(date, mmsi, name, flag, vtype, hours=1, lat=24.4, lon=118.4, vid=None):
    return {"date": date, "mmsi": mmsi, "shipName": name, "flag": flag, "vesselType": vtype, "hours": hours,
            "lat": lat, "lon": lon, "vesselId": vid or f"v{mmsi}", "entryTimestamp": f"{date}T01:00:00Z",
            "exitTimestamp": f"{date}T02:00:00Z"}


def test_coast_guard_rows_never_count_as_civilian(monkeypatch):
    monkeypatch.setattr(gfw_civil, "_ROSTER", {})
    rows = [_cell("2026-07-01", "413000001", "CHINACOASTGUARD14533", "CHN", "OTHER"),
            _cell("2026-07-01", "412000002", "JIAO GONG 72", "CHN", "OTHER"),
            _cell("2026-07-01", "412000002", "JIAO GONG 72", "CHN", "OTHER", lat=24.5, lon=118.5)]
    daily, hulls = aggregate_civil(rows, "kinmen_restricted", IS_CG)
    assert daily == [{"date": "2026-07-01", "zone_id": "kinmen_restricted", "flag": "CHN", "vessel_class": "OTHER",
                      "hull_days": 1, "hours": 2.0}]
    assert [h["mmsi"] for h in hulls] == ["412000002"]
    assert hulls[0]["cells"] == 2 and hulls[0]["lat"] == 24.45   # hours-weighted mean of two cells


def test_aggregate_only_chn_twn_but_roster_hull_kept_under_any_flag(monkeypatch):
    monkeypatch.setattr(gfw_civil, "_ROSTER", {"412501101": {"source": "AMTI/C4ADS 2021 App. A"}})
    rows = [_cell("2026-07-01", "412501101", "GUI BEI YU 39198", "GRD", "FISHING"),   # spoofed flag, listed hull
            _cell("2026-07-01", "416000009", "HAI FENG", "TWN", "FISHING"),
            _cell("2026-07-01", "353000010", "PANAMA STAR", "PAN", "CARGO")]
    daily, hulls = aggregate_civil(rows, "east_coast_box", IS_CG)
    assert {(d["flag"], d["vessel_class"]) for d in daily} == {("TWN", "FISHING")}
    assert [h["mmsi"] for h in hulls] == ["412501101"]


def test_keep_hull_rules(monkeypatch):
    monkeypatch.setattr(gfw_civil, "_ROSTER", {})
    assert keep_hull("kinmen_restricted", "CHN", "FISHING", "1")          # every CHN hull in the small zones
    assert keep_hull("contiguous_n", "CHN", "OTHER", "1")                # CHN non-fishing everywhere
    assert not keep_hull("contiguous_n", "CHN", "FISHING", "1")          # CHN fishing in big zones = aggregate only
    assert not keep_hull("kinmen_restricted", "TWN", "OTHER", "1")       # TWN hulls are aggregate only


def test_sar_split_matched_vs_unmatched():
    rows = [{"date": "2025-07-13", "detections": 1, "vesselId": "abc", "mmsi": "416000001", "flag": "TWN", "vesselType": "FISHING"},
            {"date": "2025-07-13", "detections": 2, "vesselId": "abc", "mmsi": "416000001", "flag": "TWN", "vesselType": "FISHING"},
            {"date": "2025-07-13", "detections": 5, "vesselId": "", "mmsi": "", "flag": "", "vesselType": ""},
            {"date": "2025-07-13", "detections": 0, "vesselId": "", "mmsi": "", "flag": "", "vesselType": ""}]
    agg = {(a["matched"], a["flag"], a["vessel_class"]): a for a in aggregate_sar(rows, "median_line_east")}
    assert agg[(1, "TWN", "FISHING")]["detections"] == 3 and agg[(1, "TWN", "FISHING")]["vessels"] == 1
    assert agg[(0, "", "")]["detections"] == 5 and agg[(0, "", "")]["vessels"] == 0
    assert len(agg) == 2   # the zero-detection row is dropped


def test_api_caveat_scopes_have_copy_text():
    import json
    from api.routes.maritime import CAVEAT_SCOPES
    with open(os.path.join(os.path.dirname(__file__), "..", "data", "site_copy.json"), encoding="utf-8") as f:
        copy = json.load(f)
    for k in CAVEAT_SCOPES:
        assert copy.get(f"maritime.caveat.{k}", "").strip(), f"missing copy for maritime.caveat.{k}"
