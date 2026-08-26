"""Coast Guard presence from Global Fishing Watch (Phase 2e).

Pulls the 4Wings *presence* report (per-vessel, per-day, 0.01° cells) for each
zone polygon in data/coast_guard_zones.geojson, keeps the rows that belong to
a coast guard (CCG / CGA / JCG / USCG), and upserts them into
coast_guard_presence as one row per (date, zone, hull). GFW does the
point-in-polygon; we never handle raw positions.

Why GFW and not a live AIS feed: see COAST_GUARD_TRACKER_SCOPE.md (update
block). GFW is free for non-commercial use, covers 2017 → ~5 days ago, and
its identity index resolves all four rosters. Data lag ~5 days is the price.

Classification is NAME-based first, flag second, because the CCG spoofs
MIDs (hull 14513 under a Venezuelan MMSI, 14057 under a Japanese one) — a
flag filter alone would drop exactly the interesting rows. Server-side we
still filter by flag on the BIG zones to keep responses tractable; the flag
list is the four forces' flags plus every flag seen on a CCG-named identity
(refreshed by the roster pass), so known spoofs are kept.

Gotchas (all hit during the 2026-08-25 probe):
  * the gateway sits behind Cloudflare and 403s (error 1010) on Python's
    default User-Agent — always send a real UA;
  * `datasets[0]=…:latest` comes back keyed by the RESOLVED version
    (`public-global-presence:v4.0`) — read the first key, never hard-code;
  * `filters[0]` is SQL-ish and only knows a few columns (flag, geartype,
    vessel_id) — `vesselType` is NOT filterable;
  * `vessels/search` takes `query` OR `where`, never both.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import httpx

from scraper.utils.db import get_connection

GFW_BASE = "https://gateway.api.globalfishingwatch.org/v3"
USER_AGENT = "cross-strait-signal/1.0 (+https://strait-signal.net; open-source OSINT dashboard)"
PRESENCE_DATASET = "public-global-presence:latest"
IDENTITY_DATASET = "public-global-vessel-identity:latest"

ROOT = Path(__file__).resolve().parents[2]
ZONES_PATH = ROOT / "data" / "coast_guard_zones.geojson"
ROSTER_SEED_PATH = ROOT / "data" / "coast_guard_roster_seed.json"

# Zones small enough to pull unfiltered (every flag — catches MID spoofing
# without a roster). Everything else is pulled with the flag filter.
UNFILTERED_ZONES = {"kinmen_prohibited", "kinmen_restricted", "matsu_prohibited", "matsu_restricted"}
FORCE_FLAGS = {"CCG": "CHN", "CGA": "TWN", "JCG": "JPN", "USCG": "USA"}

# --- classification -------------------------------------------------------
# Order matters: CCG by name regardless of flag; then the flag-gated forces.
_CCG_NAME = re.compile(r"COAST\s*GUARD|GUARD\s*COAST|HAI\s*JING|HAIJING|ZHONGGUO\s*HAI|^CCG\s*\d", re.I)
_CCG_HULL = re.compile(r"(\d{4,5})\s*$")
_CGA_NAME = re.compile(r"^CG[\s-]?(\d{3,5})\b", re.I)            # CG5002 HSINCHU, CG-127, CG 129
_USCG_NAME = re.compile(r"^(?:USCGC|CGC|CG)\s+[A-Z]", re.I)      # CGC MIDGETT, CG MYRTLE HAZARD, USCGC ELM
_NOT_CG = re.compile(r"PILOT|CRUISE|EXPRESS|FERRY|TUG|CARGO", re.I)
_NOT_CCG_FLAGS = {"TWN", "JPN", "USA", "KOR"}


def _load_jcg_names() -> set[str]:
    if not ROSTER_SEED_PATH.exists():
        return set()
    seed = json.loads(ROSTER_SEED_PATH.read_text())
    return {n.upper() for n in seed.get("JCG", {}).get("names", [])}


_JCG_NAMES: set[str] | None = None


_NON_CG_TYPES = {"PASSENGER", "CARGO", "FISHING", "TANKER", "CARRIER", "GEAR", "BUNKER"}


def classify(name: str | None, flag: str | None, vessel_type: str | None = None) -> tuple[str | None, str | None]:
    """Return (force, hull_no) for an AIS shipname + flag, or (None, None).

    `vessel_type` is GFW's inferred type where available (presence rows carry
    it; identity records don't). JCG names are plain Japanese place names that
    ferries and merchant ships also use, so a JCG match additionally requires
    the type not to be an obvious civilian class."""
    global _JCG_NAMES
    n = (name or "").strip().upper()
    if not n:
        return None, None
    if vessel_type and vessel_type.upper() in _NON_CG_TYPES and flag == "JPN":
        return None, None
    if _CCG_NAME.search(n) and not _USCG_NAME.match(n):
        # "HAI JING" (海警) is also a Taiwanese ship name (416002727 HAI JING, TWN,
        # 84 hull-days in the eastern contiguous zone — a false positive caught
        # 2026-08-26). Only the explicit "CHINA …" forms are accepted under a
        # TWN/JPN/USA/KOR flag; the spoofed-MID CCG hulls carry other flags or none.
        if flag in _NOT_CCG_FLAGS and "CHINA" not in n and not n.startswith("CCG"):
            return None, None
        m = _CCG_HULL.search(n)
        return "CCG", (m.group(1) if m else None)
    if flag == "TWN":
        m = _CGA_NAME.match(n)
        if m and not _NOT_CG.search(n):
            return "CGA", m.group(1)
    if flag == "USA" and _USCG_NAME.match(n):
        return "USCG", None
    if flag == "JPN":
        if _JCG_NAMES is None:
            _JCG_NAMES = _load_jcg_names()
        if n in _JCG_NAMES:
            return "JCG", None
    return None, None


# --- client ---------------------------------------------------------------
class GFWClient:
    def __init__(self, token: str | None = None, sleep: float = 1.0):
        self.token = token or os.environ.get("GFW_API_TOKEN")
        if not self.token:
            raise RuntimeError("GFW_API_TOKEN is not set (see .env)")
        self.sleep = sleep
        self._client = httpx.Client(
            base_url=GFW_BASE, timeout=httpx.Timeout(600.0, connect=30.0),
            headers={"Authorization": f"Bearer {self.token}", "User-Agent": USER_AGENT,
                     "Accept": "application/json"},
        )

    def _request(self, method: str, path: str, *, params=None, json_body=None, retries: int = 5):
        delay = 5.0
        for attempt in range(retries):
            r = self._client.request(method, path, params=params, json=json_body)
            if r.status_code == 200:
                if self.sleep:
                    time.sleep(self.sleep)
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                print(f"  [gfw] {r.status_code} on {path}; retry in {delay:.0f}s", file=sys.stderr)
                time.sleep(delay)
                delay = min(delay * 2, 120)
                continue
            raise RuntimeError(f"GFW {method} {path} -> {r.status_code}: {r.text[:300]}")
        raise RuntimeError("unreachable")

    def presence_report(self, geometry: dict, start: str, end: str, flags: Iterable[str] | None = None) -> list[dict]:
        """Per-vessel, per-day, per-cell presence rows inside `geometry` for [start, end]."""
        params = [
            ("spatial-resolution", "HIGH"), ("temporal-resolution", "DAILY"), ("group-by", "VESSEL_ID"),
            ("datasets[0]", PRESENCE_DATASET), ("date-range", f"{start},{end}"), ("format", "JSON"),
        ]
        if flags:
            quoted = ",".join(f"'{f}'" for f in sorted(set(flags)))
            params.append(("filters[0]", f"flag in ({quoted})"))
        d = self._request("POST", "/4wings/report", params=params, json_body={"geojson": geometry})
        entries = d.get("entries") or []
        if not entries:
            return []
        first = entries[0] or {}
        if not first:           # GFW returns [{}] for an empty period (was a StopIteration)
            return []
        key = next(iter(first))
        return first.get(key) or []

    def identity_where(self, where: str, limit: int = 50, max_pages: int = 40) -> list[dict]:
        """All selfReportedInfo identity records matching a SQL-ish `where`."""
        out, since = [], None
        for _ in range(max_pages):
            params = {"where": where, "datasets[0]": IDENTITY_DATASET, "limit": limit}
            if since:
                params["since"] = since
            d = self._request("GET", "/vessels/search", params=params)
            entries = d.get("entries") or []
            for e in entries:
                for s in e.get("selfReportedInfo") or []:
                    out.append(s)
            since = d.get("since")
            if not since or not entries:
                break
        return out


# --- zones ----------------------------------------------------------------
def load_zones() -> list[dict]:
    fc = json.loads(ZONES_PATH.read_text())
    return [{"id": f["properties"]["id"], "group": f["properties"]["group"],
             "label_en": f["properties"]["label_en"], "geometry": f["geometry"]} for f in fc["features"]]


# --- presence ingest ------------------------------------------------------
def _extra_ccg_flags(conn) -> set[str]:
    rows = conn.execute("SELECT DISTINCT flag FROM coast_guard_vessels WHERE force='CCG' AND flag IS NOT NULL").fetchall()
    return {r[0] for r in rows if r[0]}


def aggregate(rows: list[dict], zone_id: str) -> list[dict]:
    """Collapse GFW cell rows to one row per (date, mmsi); classify on the way."""
    acc: dict[tuple[str, str], dict] = {}
    for r in rows:
        force, hull = classify(r.get("shipName"), r.get("flag"), r.get("vesselType"))
        if not force:
            continue
        mmsi = str(r.get("mmsi") or "")
        if not mmsi:
            continue
        k = (r["date"], mmsi)
        a = acc.get(k)
        h = float(r.get("hours") or 0.0)
        if a is None:
            a = acc[k] = {"date": r["date"], "zone_id": zone_id, "mmsi": mmsi, "force": force,
                          "name": r.get("shipName"), "flag": r.get("flag"), "hours": 0.0, "cells": 0,
                          "_lat": 0.0, "_lon": 0.0, "entry_ts": r.get("entryTimestamp"),
                          "exit_ts": r.get("exitTimestamp"), "vessel_id": r.get("vesselId"), "hull_no": hull}
        a["hours"] += h
        a["cells"] += 1
        a["_lat"] += h * float(r.get("lat") or 0.0)
        a["_lon"] += h * float(r.get("lon") or 0.0)
        if r.get("entryTimestamp") and (not a["entry_ts"] or r["entryTimestamp"] < a["entry_ts"]):
            a["entry_ts"] = r["entryTimestamp"]
        if r.get("exitTimestamp") and (not a["exit_ts"] or r["exitTimestamp"] > a["exit_ts"]):
            a["exit_ts"] = r["exitTimestamp"]
    out = []
    for a in acc.values():
        if a["hours"] > 0:
            a["lat"] = round(a["_lat"] / a["hours"], 4)
            a["lon"] = round(a["_lon"] / a["hours"], 4)
        else:
            a["lat"] = a["lon"] = None
        del a["_lat"], a["_lon"]
        out.append(a)
    return out


def upsert_presence(conn, rows: list[dict]) -> int:
    conn.executemany(
        """INSERT INTO coast_guard_presence
             (date, zone_id, mmsi, force, name, flag, hours, cells, lat, lon, entry_ts, exit_ts, vessel_id)
           VALUES (:date, :zone_id, :mmsi, :force, :name, :flag, :hours, :cells, :lat, :lon, :entry_ts, :exit_ts, :vessel_id)
           ON CONFLICT(date, zone_id, mmsi) DO UPDATE SET
             force=excluded.force, name=excluded.name, flag=excluded.flag, hours=excluded.hours,
             cells=excluded.cells, lat=excluded.lat, lon=excluded.lon, entry_ts=excluded.entry_ts,
             exit_ts=excluded.exit_ts, vessel_id=excluded.vessel_id""",
        rows,
    )
    # Hulls seen in presence but unknown to the roster get a provisional row
    # (source='presence') so the roster review queue sees them.
    conn.executemany(
        """INSERT INTO coast_guard_vessels (mmsi, vessel_id, name, flag, force, hull_no, first_seen, last_seen, source)
           VALUES (:mmsi, :vessel_id, :name, :flag, :force, :hull_no, :date, :date, 'presence')
           ON CONFLICT(mmsi) DO UPDATE SET
             last_seen = CASE WHEN excluded.last_seen > coalesce(coast_guard_vessels.last_seen, '') THEN excluded.last_seen ELSE coast_guard_vessels.last_seen END,
             first_seen = CASE WHEN coast_guard_vessels.first_seen IS NULL OR excluded.first_seen < coast_guard_vessels.first_seen THEN excluded.first_seen ELSE coast_guard_vessels.first_seen END,
             name = coalesce(coast_guard_vessels.name, excluded.name),
             updated_at = datetime('now')""",
        rows,
    )
    return len(rows)


def pull_zone(conn, client: GFWClient, zone: dict, start: str, end: str, extra_flags: set[str] | None = None) -> tuple[int, int]:
    flags = None
    if zone["id"] not in UNFILTERED_ZONES:
        flags = set(FORCE_FLAGS.values()) | (extra_flags or set())
    try:
        rows = client.presence_report(zone["geometry"], start, end, flags)
        kept = aggregate(rows, zone["id"])
        upsert_presence(conn, kept)
        conn.execute(
            "INSERT INTO coast_guard_pulls (zone_id, period_start, period_end, rows_total, rows_kept, status) VALUES (?,?,?,?,?,'ok')",
            (zone["id"], start, end, len(rows), len(kept)),
        )
        conn.commit()
        return len(rows), len(kept)
    except Exception as e:  # noqa: BLE001
        conn.execute(
            "INSERT INTO coast_guard_pulls (zone_id, period_start, period_end, status, error) VALUES (?,?,?,'error',?)",
            (zone["id"], start, end, f"{type(e).__name__}: {str(e)[:300]}"),
        )
        conn.commit()
        raise


def month_windows(start: date, end: date) -> list[tuple[str, str]]:
    """[(YYYY-MM-01, month-end)] covering start..end inclusive, clipped to the range."""
    out, cur = [], date(start.year, start.month, 1)
    while cur <= end:
        nxt = date(cur.year + (cur.month // 12), cur.month % 12 + 1, 1)
        s, e = max(cur, start), min(nxt - timedelta(days=1), end)
        out.append((s.isoformat(), e.isoformat()))
        cur = nxt
    return out


def pull_recent(days: int = 10, db_path: str | None = None, zones: Iterable[str] | None = None) -> int:
    """Pipeline entry point: re-pull the trailing window (GFW lags ~5 days and
    back-fills late AIS), idempotent via the (date, zone, mmsi) upsert."""
    conn = get_connection(db_path)
    client = GFWClient()
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)
    extra = _extra_ccg_flags(conn)
    total_kept = 0
    for z in load_zones():
        if zones and z["id"] not in zones:
            continue
        n, k = pull_zone(conn, client, z, start.isoformat(), end.isoformat(), extra)
        print(f"  [coast-guard] {z['id']:20s} {start}..{end}: {n} rows, {k} coast-guard hull-days")
        total_kept += k
    # Settle any hulls the presence pull added to the roster (source='presence').
    triage_roster(conn)
    conn.close()
    return total_kept


# --- roster triage --------------------------------------------------------
# MID (Maritime Identification Digits) prefixes per force. The only review
# question is "is this hull a coast-guard vessel?"; anomaly flags are facts
# about the AIS stream and never a criterion here. See
# scripts/triage_coast_guard_roster.py for the rules.
FORCE_MIDS = {"CCG": {"412", "413", "414"}, "CGA": {"416"}, "JCG": {"431", "432"},
              "USCG": {"303", "338", "366", "367", "368", "369"}}
_EXPLICIT_NAME = {
    "CCG": re.compile(r"CHINA\s*COAST\s*GUARD|ZHONGGUO\s*HAI|^CCG\s*\d", re.I),
    "CGA": _CGA_NAME,
    "USCG": _USCG_NAME,
}


def triage_verdict(name: str | None, flag: str | None, mmsi: str, force: str) -> tuple[str, str]:
    """('reject'|'confirm'|'leave', reason) for one roster row."""
    cls, _ = classify(name, flag)
    if cls is None:
        return "reject", "classifier no longer accepts name/flag"
    if cls != force:
        return "leave", f"classifier says {cls}"
    n = (name or "").strip().upper()
    pat = _EXPLICIT_NAME.get(force)
    if pat and pat.search(n):
        return "confirm", "explicit force name"
    if mmsi[:3] in FORCE_MIDS.get(force, set()):
        return "confirm", f"MID {mmsi[:3]} matches {force}"
    if force == "JCG":            # JCG names are a curated class list; classify() already required JPN flag
        return "confirm", "JCG class name under JPN flag"
    return "leave", "weak name + foreign/junk MID"


def triage_roster(conn, dry_run: bool = False, verbose: bool = False) -> dict:
    """Apply triage_verdict to every status='auto' row. Idempotent."""
    rows = conn.execute("SELECT mmsi, name, flag, force FROM coast_guard_vessels WHERE status='auto'").fetchall()
    out = {"confirmed": 0, "rejected": 0, "purged_presence": 0, "left": 0}
    for r in rows:
        verdict, reason = triage_verdict(r["name"], r["flag"], r["mmsi"], r["force"])
        if verdict == "leave":
            out["left"] += 1
            if verbose:
                print(f"  leave   {r['force']} {r['mmsi']} {r['name']!r} flag={r['flag']} — {reason}")
            continue
        status = "confirmed" if verdict == "confirm" else "rejected"
        out[status] += 1
        if verbose and verdict == "reject":
            print(f"  REJECT  {r['force']} {r['mmsi']} {r['name']!r} flag={r['flag']} — {reason}")
        if dry_run:
            continue
        conn.execute("UPDATE coast_guard_vessels SET status=?, notes=COALESCE(notes, ?), updated_at=datetime('now') WHERE mmsi=?",
                     (status, f"auto-triage: {reason}", r["mmsi"]))
        if verdict == "reject":
            cur = conn.execute("DELETE FROM coast_guard_presence WHERE mmsi=?", (r["mmsi"],))
            out["purged_presence"] += cur.rowcount
    if not dry_run:
        conn.commit()
    return out
