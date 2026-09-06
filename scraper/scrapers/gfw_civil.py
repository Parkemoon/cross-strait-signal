"""Civilian-fleet + SAR dark-vessel layer from Global Fishing Watch (Phase 2g).

The Maritime tab's "militia / dredger" layer, named after what is measured:

  1. CIVIL PRESENCE — the non-coast-guard rows of the SAME 4Wings presence
     report Step 2n already pulls per zone (scraper/scrapers/gfw_coast_guard.py
     hands every response here before discarding the non-CG rows). Aggregated
     to per (day, zone, flag, class) hull-days for CHN + TWN, plus per-hull
     rows for the subset worth naming (see keep_hull). Zero extra API cost.
  2. SAR DETECTIONS — GFW's `public-global-sar-presence` (Sentinel-1 radar
     detections, 2017→, ≥~20 m hulls, nothing within ~1 km of shore), per
     zone per day, split matched-to-AIS vs unmatched. Unmatched = radar saw a
     hull and no AIS identity matched — the honest "dark vessel" measure and the
     ceiling that pairs with the AIS-visible floor on the same page.

What this layer deliberately does NOT claim (probed 2026-09-04):
  * "dredger": GFW's presence vesselType is coarse (FISHING / CARGO / OTHER /
    PASSENGER / GEAR / SEISMIC_VESSEL) and the public identity index exposes
    nothing finer for these hulls — dredgers, tugs, supply and survey ships are
    all OTHER. We show "non-fishing (OTHER)" and say so.
  * "militia": only hulls on a PUBLISHED identification list are flagged
    (data/maritime_militia_roster.json — AMTI/C4ADS appendices, with the
    citation on the row). Nothing is inferred from behaviour in v1.

SAR latency (measured 2026-09-06): the SAR dataset carries no endDate and
returns an empty (not erroring) report for any window it hasn't published —
data ran to 2026-06-26 on 2026-09-06, i.e. ~2 months behind. Step 2p therefore
re-pulls a 120-day trailing window once a day, and the health check allows
100 days before calling the series stale.

Filter gotchas (4Wings, measured): `vessel_type in ('other')` works with
LOWER-case values (upper-case returns null entries); `matched = 'false'`
must be the STRING literal (a bare boolean 422s); the SAR dataset accepts
HIGH/DAILY with no group-by and returns identity fields blank on unmatched
rows.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

from scraper.utils.db import get_connection

ROOT = Path(__file__).resolve().parents[2]
MILITIA_ROSTER_PATH = ROOT / "data" / "maritime_militia_roster.json"

SAR_DATASET = "public-global-sar-presence:latest"
AGG_FLAGS = {"CHN", "TWN"}                       # comparable across zones (big zones are flag-filtered)
# Small zones: every CHN hull gets a per-hull row. Elsewhere only CHN
# non-fishing ("OTHER") hulls and roster-listed hulls do — CHN fishing in the
# 24 nm sectors / median band / Taiwan Bank runs to thousands of hulls a
# month and is served as the daily aggregate instead.
HULL_ZONES = {"kinmen_prohibited", "kinmen_restricted", "matsu_prohibited", "matsu_restricted", "pratas_24nm"}
HULL_CLASSES_EVERYWHERE = {"OTHER"}


# --- militia roster -------------------------------------------------------
_ROSTER: dict[str, dict] | None = None


def militia_roster() -> dict[str, dict]:
    """{mmsi: row} from data/maritime_militia_roster.json (empty if absent)."""
    global _ROSTER
    if _ROSTER is None:
        _ROSTER = {}
        if MILITIA_ROSTER_PATH.exists():
            data = json.loads(MILITIA_ROSTER_PATH.read_text(encoding="utf-8"))
            for r in data.get("vessels", []):
                m = str(r.get("mmsi") or "").strip()
                if m:
                    _ROSTER[m] = r
    return _ROSTER


def _norm_class(v: str | None) -> str:
    v = (v or "").strip().upper()
    return v or "UNKNOWN"


def keep_hull(zone_id: str, flag: str | None, vessel_class: str, mmsi: str) -> bool:
    if mmsi in militia_roster():
        return True
    if flag != "CHN":
        return False
    return zone_id in HULL_ZONES or vessel_class in HULL_CLASSES_EVERYWHERE


# --- civil presence ingest ------------------------------------------------
def aggregate_civil(rows: list[dict], zone_id: str, is_coast_guard) -> tuple[list[dict], list[dict]]:
    """(daily aggregate rows, per-hull rows) from GFW presence cell rows.

    `is_coast_guard(name, flag, vessel_type) -> bool` excludes the rows the
    coast-guard layer owns, so a CCG cutter never counts as a civilian hull."""
    per_hull: dict[tuple[str, str], dict] = {}
    for r in rows:
        mmsi = str(r.get("mmsi") or "")
        if not mmsi or is_coast_guard(r.get("shipName"), r.get("flag"), r.get("vesselType")):
            continue
        k = (r["date"], mmsi)
        a = per_hull.get(k)
        h = float(r.get("hours") or 0.0)
        if a is None:
            a = per_hull[k] = {"date": r["date"], "zone_id": zone_id, "mmsi": mmsi, "flag": r.get("flag") or None,
                               "vessel_class": _norm_class(r.get("vesselType")), "name": r.get("shipName"),
                               "hours": 0.0, "cells": 0, "_lat": 0.0, "_lon": 0.0,
                               "entry_ts": r.get("entryTimestamp"), "exit_ts": r.get("exitTimestamp"),
                               "vessel_id": r.get("vesselId")}
        a["hours"] += h
        a["cells"] += 1
        a["_lat"] += h * float(r.get("lat") or 0.0)
        a["_lon"] += h * float(r.get("lon") or 0.0)
        if r.get("entryTimestamp") and (not a["entry_ts"] or r["entryTimestamp"] < a["entry_ts"]):
            a["entry_ts"] = r["entryTimestamp"]
        if r.get("exitTimestamp") and (not a["exit_ts"] or r["exitTimestamp"] > a["exit_ts"]):
            a["exit_ts"] = r["exitTimestamp"]
    daily: dict[tuple[str, str, str], dict] = {}
    hulls: list[dict] = []
    for a in per_hull.values():
        if a["hours"] > 0:
            a["lat"], a["lon"] = round(a["_lat"] / a["hours"], 4), round(a["_lon"] / a["hours"], 4)
        else:
            a["lat"] = a["lon"] = None
        del a["_lat"], a["_lon"]
        if a["flag"] in AGG_FLAGS:
            d = daily.setdefault((a["date"], a["flag"], a["vessel_class"]),
                                 {"date": a["date"], "zone_id": zone_id, "flag": a["flag"],
                                  "vessel_class": a["vessel_class"], "hull_days": 0, "hours": 0.0})
            d["hull_days"] += 1
            d["hours"] += a["hours"]
        if keep_hull(zone_id, a["flag"], a["vessel_class"], a["mmsi"]):
            hulls.append(a)
    return list(daily.values()), hulls


def write_civil(conn, zone_id: str, start: str, end: str, daily: list[dict], hulls: list[dict]) -> None:
    """Replace the window's aggregate rows (GFW back-fills late AIS, so a
    re-pull must be able to LOWER a count), upsert the per-hull rows, and
    keep maritime_civil_vessels current — roster columns from the file."""
    conn.execute("DELETE FROM maritime_civil_daily WHERE zone_id=? AND date BETWEEN ? AND ?", (zone_id, start, end))
    conn.executemany(
        "INSERT INTO maritime_civil_daily (date, zone_id, flag, vessel_class, hull_days, hours) "
        "VALUES (:date,:zone_id,:flag,:vessel_class,:hull_days,:hours)",
        daily)
    conn.executemany(
        """INSERT INTO maritime_civil_presence (date, zone_id, mmsi, flag, vessel_class, name, hours, cells, lat, lon, entry_ts, exit_ts, vessel_id)
           VALUES (:date,:zone_id,:mmsi,:flag,:vessel_class,:name,:hours,:cells,:lat,:lon,:entry_ts,:exit_ts,:vessel_id)
           ON CONFLICT(date, zone_id, mmsi) DO UPDATE SET
             flag=excluded.flag, vessel_class=excluded.vessel_class, name=excluded.name, hours=excluded.hours,
             cells=excluded.cells, lat=excluded.lat, lon=excluded.lon, entry_ts=excluded.entry_ts,
             exit_ts=excluded.exit_ts, vessel_id=excluded.vessel_id""",
        hulls)
    roster = militia_roster()
    vrows = []
    for h in hulls:
        m = roster.get(h["mmsi"]) or {}
        vrows.append({**h, "militia_source": m.get("source"), "militia_url": m.get("source_url"),
                      "militia_name_zh": m.get("name_zh"), "militia_port": m.get("home_port")})
    conn.executemany(
        """INSERT INTO maritime_civil_vessels (mmsi, vessel_id, name, flag, vessel_class, first_seen, last_seen,
                                               militia_source, militia_url, militia_name_zh, militia_port)
           VALUES (:mmsi,:vessel_id,:name,:flag,:vessel_class,:date,:date,:militia_source,:militia_url,:militia_name_zh,:militia_port)
           ON CONFLICT(mmsi) DO UPDATE SET
             last_seen = CASE WHEN excluded.last_seen > coalesce(maritime_civil_vessels.last_seen,'') THEN excluded.last_seen ELSE maritime_civil_vessels.last_seen END,
             first_seen = CASE WHEN maritime_civil_vessels.first_seen IS NULL OR excluded.first_seen < maritime_civil_vessels.first_seen THEN excluded.first_seen ELSE maritime_civil_vessels.first_seen END,
             name = coalesce(excluded.name, maritime_civil_vessels.name),
             flag = coalesce(excluded.flag, maritime_civil_vessels.flag),
             vessel_class = excluded.vessel_class, vessel_id = coalesce(excluded.vessel_id, maritime_civil_vessels.vessel_id),
             militia_source = coalesce(excluded.militia_source, maritime_civil_vessels.militia_source),
             militia_url = coalesce(excluded.militia_url, maritime_civil_vessels.militia_url),
             militia_name_zh = coalesce(excluded.militia_name_zh, maritime_civil_vessels.militia_name_zh),
             militia_port = coalesce(excluded.militia_port, maritime_civil_vessels.militia_port),
             updated_at = datetime('now')""",
        vrows)


def log_pull(conn, kind: str, zone_id: str, start: str, end: str, total: int | None, kept: int | None,
             error: str | None = None) -> None:
    conn.execute(
        "INSERT INTO maritime_pulls (kind, zone_id, period_start, period_end, rows_total, rows_kept, status, error) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (kind, zone_id, start, end, total, kept, "error" if error else "ok", error))


def ingest_civil_rows(conn, zone_id: str, start: str, end: str, rows: list[dict], is_coast_guard) -> tuple[int, int]:
    """Called by gfw_coast_guard.pull_zone with the raw presence rows of one
    (zone, window). Tolerates a DB without migration 0012 (logs and skips)."""
    try:
        daily, hulls = aggregate_civil(rows, zone_id, is_coast_guard)
        write_civil(conn, zone_id, start, end, daily, hulls)
        log_pull(conn, "civil", zone_id, start, end, len(rows), len(hulls))
        return len(daily), len(hulls)
    except Exception as e:  # noqa: BLE001
        if "no such table" in str(e):
            print(f"  [maritime] civil layer skipped ({e}) — run scripts/migrate.py", file=sys.stderr)
            return 0, 0
        try:
            log_pull(conn, "civil", zone_id, start, end, None, None, f"{type(e).__name__}: {str(e)[:300]}")
        except Exception:  # noqa: BLE001
            pass
        raise


# --- SAR detections --------------------------------------------------------
def sar_report(client, geometry: dict, start: str, end: str) -> list[dict]:
    params = [
        ("spatial-resolution", "HIGH"), ("temporal-resolution", "DAILY"),
        ("datasets[0]", SAR_DATASET), ("date-range", f"{start},{end}"), ("format", "JSON"),
    ]
    d = client._request("POST", "/4wings/report", params=params, json_body={"geojson": geometry})
    entries = d.get("entries") or []
    if not entries or not entries[0]:
        return []
    key = next(iter(entries[0]))
    return entries[0].get(key) or []


def aggregate_sar(rows: list[dict], zone_id: str) -> list[dict]:
    acc: dict[tuple, dict] = {}
    vessels: dict[tuple, set] = defaultdict(set)
    for r in rows:
        vid = r.get("vesselId") or ""
        matched = 1 if (vid or r.get("mmsi")) else 0
        flag = (r.get("flag") or "") if matched else ""
        cls = _norm_class(r.get("vesselType")) if matched else ""
        if matched and cls == "UNKNOWN":
            cls = ""
        k = (r["date"], matched, flag, cls)
        a = acc.setdefault(k, {"date": r["date"], "zone_id": zone_id, "matched": matched, "flag": flag,
                               "vessel_class": cls, "detections": 0, "vessels": 0})
        a["detections"] += int(r.get("detections") or 0)
        if vid:
            vessels[k].add(vid)
    for k, a in acc.items():
        a["vessels"] = len(vessels.get(k, ()))
    return [a for a in acc.values() if a["detections"] > 0]


def write_sar(conn, zone_id: str, start: str, end: str, rows: list[dict]) -> None:
    conn.execute("DELETE FROM maritime_sar_daily WHERE zone_id=? AND date BETWEEN ? AND ?", (zone_id, start, end))
    conn.executemany(
        "INSERT INTO maritime_sar_daily (date, zone_id, matched, flag, vessel_class, detections, vessels) "
        "VALUES (:date,:zone_id,:matched,:flag,:vessel_class,:detections,:vessels)",
        rows)


def pull_sar_zone(conn, client, zone: dict, start: str, end: str) -> tuple[int, int]:
    try:
        rows = sar_report(client, zone["geometry"], start, end)
        agg = aggregate_sar(rows, zone["id"])
        write_sar(conn, zone["id"], start, end, agg)
        log_pull(conn, "sar", zone["id"], start, end, len(rows), sum(a["detections"] for a in agg))
        conn.commit()
        return len(rows), len(agg)
    except Exception as e:  # noqa: BLE001
        log_pull(conn, "sar", zone["id"], start, end, None, None, f"{type(e).__name__}: {str(e)[:300]}")
        conn.commit()
        raise


SAR_LAG_DAYS = 120       # GFW publishes SAR ~2 months late (probed 2026-09-06: data to 06-26, nothing after)
SAR_MIN_HOURS = 20       # re-pull a zone at most once a day (each report is ~30 s and GFW serialises them)


def _sar_pulled_recently(conn, zone_id: str, hours: int = SAR_MIN_HOURS) -> bool:
    r = conn.execute(
        "SELECT 1 FROM maritime_pulls WHERE kind='sar' AND zone_id=? AND status='ok' "
        "AND pulled_at >= datetime('now', ?) LIMIT 1", (zone_id, f"-{hours} hours")).fetchone()
    return r is not None


def pull_sar_recent(days: int = SAR_LAG_DAYS, db_path: str | None = None, zones: Iterable[str] | None = None,
                    force: bool = False) -> int:
    """Pipeline entry point (Step 2p): re-pull the trailing SAR window per
    zone. GFW's SAR product lands ~2 MONTHS late (not the ~5 days of the AIS
    presence dataset — measured 2026-09-06) and AIS matching is revised as
    late AIS arrives, so the window is `days` long (default 120) and replaced
    wholesale; a zone is skipped when it was pulled ok in the last
    SAR_MIN_HOURS, which turns the 6-hourly tick into a daily pull."""
    from scraper.scrapers.gfw_coast_guard import GFWClient, load_zones   # lazy: avoid import cycle
    conn = get_connection(db_path)
    client = GFWClient()
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)
    total = 0
    for z in load_zones():
        if zones and z["id"] not in zones:
            continue
        if not force and _sar_pulled_recently(conn, z["id"]):
            continue
        n, k = pull_sar_zone(conn, client, z, start.isoformat(), end.isoformat())
        print(f"  [maritime-sar] {z['id']:20s} {start}..{end}: {n} cell-rows, {k} day/class rows")
        total += k
    conn.close()
    return total
