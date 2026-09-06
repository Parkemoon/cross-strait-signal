"""Maritime civilian-fleet + dark-vessel endpoints (Phase 2g).

Serves the three feeds scraper/scrapers/gfw_civil.py writes:
  maritime_civil_daily     per (day, zone, flag, class) hull-days — CHN/TWN
                           non-coast-guard hulls from the Step 2n presence pull
  maritime_civil_presence  per-hull rows (CHN hulls in the small zones, CHN
                           non-fishing everywhere, roster-listed hulls anywhere)
  maritime_sar_daily       Sentinel-1 detections per (day, zone), matched-to-AIS
                           vs unmatched

Framing rules carried from the coast-guard tracker: AIS presence is a FLOOR;
SAR unmatched detections are the radar-visible CEILING (≥~20 m hulls, >1 km
from shore, per satellite pass — not hull-days); GFW's vessel classes are
coarse, so "OTHER" is shown as non-fishing and never as "dredger"; militia is
the cited study's INFERENCE (ownership / subsidy / training records), never ours
and never proof — the militia exists, which hulls belong to it is not public
(Ed, 2026-09-06). Caveat TEXT lives in
data/site_copy.json (maritime.caveat.<key>), the SCOPE here.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.database import db_conn
from api.routes.coast_guard import _zones_fc
from api.routes.copy import get_copy
from scraper.scrapers.gfw_civil import HULL_ZONES, militia_roster

router = APIRouter(prefix="/api/military/maritime", tags=["maritime"])

CLASSES = ("FISHING", "OTHER", "CARGO", "PASSENGER", "GEAR", "SEISMIC_VESSEL", "UNKNOWN")
CLASS_LABELS = {"FISHING": "fishing", "OTHER": "non-fishing (other)", "CARGO": "cargo", "PASSENGER": "passenger",
                "GEAR": "gear / small craft", "SEISMIC_VESSEL": "seismic / survey", "UNKNOWN": "unclassified"}
FLAGS = ("CHN", "TWN")

CAVEAT_SCOPES = {
    "civil_floor": "all",           # AIS-visible only; same floor as the coast-guard series
    "class_coarse": "all",          # OTHER ≠ dredger; GFW exposes nothing finer
    "big_zone_flags": "all",        # big zones are pulled flag-filtered; only CHN/TWN comparable
    "sar_detections": "sar",        # detections per pass, ≥20 m, >1 km offshore
    "sar_coverage": "sar",          # Sentinel-1B loss Dec 2021 → 1C Dec 2024 changes pass counts
    "militia_roster": "militia",    # roster is SCS-focused; absence ≠ no militia
    "taiwan_bank": "taiwan_bank",   # box is our approximation of the shoal, Taiwan side of the line
}


def caveats() -> list[dict]:
    text = get_copy()
    return [{"key": k, "scope": scope, "en": text.get(f"maritime.caveat.{k}", "")}
            for k, scope in CAVEAT_SCOPES.items() if text.get(f"maritime.caveat.{k}")]


def _zone_ids(group: Optional[str]) -> list[str]:
    ids = [f["properties"]["id"] for f in _zones_fc()["features"] if f["properties"]["group"] == group]
    if not ids:
        raise HTTPException(400, "unknown group")
    return ids


def _scope(where: list, args: list, zone: Optional[str], group: Optional[str], col: str = "zone_id") -> None:
    if zone:
        where.append(f"{col} = ?"); args.append(zone)
    if group:
        ids = _zone_ids(group)
        where.append(f"{col} IN ({','.join('?' * len(ids))})"); args += ids


def _latest(conn, table: str) -> Optional[str]:
    r = conn.execute(f"SELECT MAX(date) FROM {table}").fetchone()
    return r[0] if r else None


@router.get("/summary")
def summary(days: int = Query(30, ge=7, le=365)):
    """Headline numbers for the civilian-fleet section: per (flag, class)
    hull-days this window vs the previous one, per-zone CHN fishing /
    non-fishing, SAR matched vs unmatched detections, roster hulls seen."""
    with db_conn() as conn:
        latest = _latest(conn, "maritime_civil_daily")
        sar_latest = _latest(conn, "maritime_sar_daily")
        out = {"latest_date": latest, "sar_latest_date": sar_latest, "days": days, "civil": [], "zones": [],
               "sar": None, "militia": {"roster_size": len(militia_roster()), "seen": []}, "caveats": caveats(),
               "hull_zones": sorted(HULL_ZONES), "class_labels": CLASS_LABELS}
        if not latest:
            return out
        end = date.fromisoformat(latest)
        start = end - timedelta(days=days - 1)
        prev_start, prev_end = start - timedelta(days=days), start - timedelta(days=1)
        out["window_start"] = start.isoformat()

        def window(a: date, b: date):
            rows = conn.execute(
                """SELECT flag, vessel_class, SUM(hull_days) AS hull_days, ROUND(SUM(hours),1) AS hours
                   FROM maritime_civil_daily WHERE date BETWEEN ? AND ? GROUP BY flag, vessel_class""",
                (a.isoformat(), b.isoformat())).fetchall()
            return {(r["flag"], r["vessel_class"]): dict(r) for r in rows}

        cur, prev = window(start, end), window(prev_start, prev_end)
        for flag in FLAGS:
            for cls in CLASSES:
                c, p = cur.get((flag, cls)), prev.get((flag, cls))
                if not c and not p:
                    continue
                out["civil"].append({"flag": flag, "vessel_class": cls, "label": CLASS_LABELS[cls],
                                     "hull_days": (c or {}).get("hull_days", 0), "hours": (c or {}).get("hours", 0.0),
                                     "prev_hull_days": (p or {}).get("hull_days", 0)})
        # Per-zone CHN fishing / non-fishing for the map + table.
        zrows = conn.execute(
            """SELECT zone_id, vessel_class, SUM(hull_days) AS hull_days FROM maritime_civil_daily
               WHERE date BETWEEN ? AND ? AND flag='CHN' GROUP BY zone_id, vessel_class""",
            (start.isoformat(), end.isoformat())).fetchall()
        by_zone: dict[str, dict] = {}
        for r in zrows:
            by_zone.setdefault(r["zone_id"], {})[r["vessel_class"]] = r["hull_days"]
        srows = {}
        if sar_latest:
            s_end = date.fromisoformat(sar_latest)
            s_start = s_end - timedelta(days=days - 1)
            for r in conn.execute(
                    """SELECT zone_id, SUM(CASE WHEN matched=1 THEN detections ELSE 0 END) AS matched,
                              SUM(CASE WHEN matched=0 THEN detections ELSE 0 END) AS unmatched
                       FROM maritime_sar_daily WHERE date BETWEEN ? AND ? GROUP BY zone_id""",
                    (s_start.isoformat(), s_end.isoformat())):
                srows[r["zone_id"]] = {"matched": r["matched"], "unmatched": r["unmatched"]}
        for f in _zones_fc()["features"]:
            p = f["properties"]
            z = by_zone.get(p["id"], {})
            out["zones"].append({"zone_id": p["id"], "label_en": p["label_en"], "label_zh": p["label_zh"], "group": p["group"],
                                 "chn_fishing": z.get("FISHING", 0), "chn_other": z.get("OTHER", 0),
                                 "chn_cargo": z.get("CARGO", 0), "sar": srows.get(p["id"])})
        # SAR headline: this window vs previous, on the SAR series' own latest date.
        if sar_latest:
            s_end = date.fromisoformat(sar_latest)
            s_start = s_end - timedelta(days=days - 1)
            ps, pe = s_start - timedelta(days=days), s_start - timedelta(days=1)

            def sar_window(a: date, b: date):
                r = conn.execute(
                    """SELECT SUM(CASE WHEN matched=1 THEN detections ELSE 0 END) AS matched,
                              SUM(CASE WHEN matched=0 THEN detections ELSE 0 END) AS unmatched,
                              SUM(CASE WHEN matched=1 AND flag='CHN' THEN detections ELSE 0 END) AS matched_chn,
                              SUM(CASE WHEN matched=1 AND flag='TWN' THEN detections ELSE 0 END) AS matched_twn
                       FROM maritime_sar_daily WHERE date BETWEEN ? AND ?""", (a.isoformat(), b.isoformat())).fetchone()
                d = {k: (r[k] or 0) for k in ("matched", "unmatched", "matched_chn", "matched_twn")}
                tot = d["matched"] + d["unmatched"]
                d["dark_share"] = round(d["unmatched"] / tot, 3) if tot else None
                return d

            out["sar"] = {"window_start": s_start.isoformat(), "current": sar_window(s_start, s_end),
                          "previous": sar_window(ps, pe), "coverage_start": conn.execute(
                              "SELECT MIN(date) FROM maritime_sar_daily").fetchone()[0]}
        # Roster-listed hulls seen in the trailing year — a citation fact, not a judgement.
        yr = (end - timedelta(days=364)).isoformat()
        seen = conn.execute(
            """SELECT v.mmsi, v.name, v.flag, v.vessel_class, v.militia_source, v.militia_url, v.militia_name_zh, v.militia_port,
                      COUNT(*) AS hull_days, MAX(p.date) AS last_date, GROUP_CONCAT(DISTINCT p.zone_id) AS zones
               FROM maritime_civil_vessels v JOIN maritime_civil_presence p ON p.mmsi = v.mmsi
               WHERE v.militia_source IS NOT NULL AND p.date >= ?
               GROUP BY v.mmsi ORDER BY hull_days DESC LIMIT 50""", (yr,)).fetchall()
        out["militia"]["seen"] = [dict(r, zones=(r["zones"] or "").split(",")) for r in seen]
        out["militia"]["since"] = yr
        out["coverage_start"] = conn.execute("SELECT MIN(date) FROM maritime_civil_daily").fetchone()[0]
        out["last_pull_at"] = conn.execute("SELECT MAX(pulled_at) FROM maritime_pulls WHERE status='ok'").fetchone()[0]
        return out


@router.get("/civil/monthly")
def civil_monthly(zone: Optional[str] = None, group: Optional[str] = None, flag: str = Query("CHN"),
                  months: int = Query(60, ge=1, le=200)):
    """Per-month hull-days by vessel class for one flag — the long-series strips."""
    if flag not in FLAGS:
        raise HTTPException(400, f"flag must be one of {FLAGS}")
    with db_conn() as conn:
        where, args = ["flag = ?"], [flag]
        _scope(where, args, zone, group)
        rows = conn.execute(
            f"""SELECT substr(date,1,7) AS month, vessel_class, SUM(hull_days) AS hull_days, ROUND(SUM(hours),1) AS hours
                FROM maritime_civil_daily WHERE {' AND '.join(where)}
                GROUP BY month, vessel_class ORDER BY month DESC LIMIT ?""", args + [months * len(CLASSES)]).fetchall()
        return {"flag": flag, "rows": [dict(r) for r in reversed(rows)]}


@router.get("/civil/daily")
def civil_daily(zone: Optional[str] = None, group: Optional[str] = None, flag: str = Query("CHN"),
                days: int = Query(90, ge=7, le=3660)):
    if flag not in FLAGS:
        raise HTTPException(400, f"flag must be one of {FLAGS}")
    with db_conn() as conn:
        latest = _latest(conn, "maritime_civil_daily")
        if not latest:
            return {"latest_date": None, "rows": []}
        end = date.fromisoformat(latest)
        start = end - timedelta(days=days - 1)
        where, args = ["flag = ?", "date BETWEEN ? AND ?"], [flag, start.isoformat(), end.isoformat()]
        _scope(where, args, zone, group)
        rows = conn.execute(
            f"""SELECT date, vessel_class, SUM(hull_days) AS hull_days, ROUND(SUM(hours),1) AS hours
                FROM maritime_civil_daily WHERE {' AND '.join(where)} GROUP BY date, vessel_class ORDER BY date""", args).fetchall()
        return {"latest_date": latest, "start": start.isoformat(), "rows": [dict(r) for r in rows]}


@router.get("/civil/vessels")
def civil_vessels(zone: Optional[str] = None, group: Optional[str] = None, vessel_class: Optional[str] = None,
                  militia: bool = False, days: int = Query(30, ge=1, le=3660), limit: int = Query(200, ge=1, le=2000)):
    """Named hulls with per-hull rows in the window (CHN hulls in the small
    zones, CHN non-fishing everywhere, roster-listed hulls anywhere)."""
    with db_conn() as conn:
        latest = _latest(conn, "maritime_civil_daily")
        end = date.fromisoformat(latest) if latest else date.today()
        start = (end - timedelta(days=days - 1)).isoformat()
        where, args = ["p.date >= ?"], [start]
        _scope(where, args, zone, group, col="p.zone_id")
        if vessel_class:
            where.append("p.vessel_class = ?"); args.append(vessel_class.upper())
        if militia:
            where.append("v.militia_source IS NOT NULL")
        rows = conn.execute(
            f"""SELECT p.mmsi, COALESCE(v.name, MAX(p.name)) AS name, COALESCE(v.flag, MAX(p.flag)) AS flag,
                       MAX(p.vessel_class) AS vessel_class, COUNT(*) AS hull_days, ROUND(SUM(p.hours),1) AS hours,
                       GROUP_CONCAT(DISTINCT p.zone_id) AS zones, MIN(p.date) AS first_date, MAX(p.date) AS last_date,
                       v.first_seen, v.last_seen, v.militia_source, v.militia_url, v.militia_name_zh, v.militia_port, v.vessel_id
                FROM maritime_civil_presence p LEFT JOIN maritime_civil_vessels v ON v.mmsi = p.mmsi
                WHERE {' AND '.join(where)}
                GROUP BY p.mmsi ORDER BY hull_days DESC, hours DESC LIMIT ?""", args + [limit]).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["zones"] = (d["zones"] or "").split(",") if d.get("zones") else []
            out.append(d)
        return {"latest_date": latest, "window_start": start, "vessels": out}


@router.get("/sar/monthly")
def sar_monthly(zone: Optional[str] = None, group: Optional[str] = None, months: int = Query(60, ge=1, le=200)):
    """Per-month SAR detections: matched-to-AIS vs unmatched (dark), with the
    CHN / TWN matched split and the dark share."""
    with db_conn() as conn:
        where, args = ["1=1"], []
        _scope(where, args, zone, group)
        rows = conn.execute(
            f"""SELECT substr(date,1,7) AS month,
                       SUM(CASE WHEN matched=1 THEN detections ELSE 0 END) AS matched,
                       SUM(CASE WHEN matched=0 THEN detections ELSE 0 END) AS unmatched,
                       SUM(CASE WHEN matched=1 AND flag='CHN' THEN detections ELSE 0 END) AS matched_chn,
                       SUM(CASE WHEN matched=1 AND flag='TWN' THEN detections ELSE 0 END) AS matched_twn,
                       COUNT(DISTINCT date) AS pass_days
                FROM maritime_sar_daily WHERE {' AND '.join(where)}
                GROUP BY month ORDER BY month DESC LIMIT ?""", args + [months]).fetchall()
        out = []
        for r in reversed(rows):
            d = dict(r)
            tot = d["matched"] + d["unmatched"]
            d["dark_share"] = round(d["unmatched"] / tot, 3) if tot else None
            out.append(d)
        return {"rows": out}


@router.get("/sar/daily")
def sar_daily(zone: Optional[str] = None, group: Optional[str] = None, days: int = Query(90, ge=7, le=3660)):
    with db_conn() as conn:
        latest = _latest(conn, "maritime_sar_daily")
        if not latest:
            return {"latest_date": None, "rows": []}
        end = date.fromisoformat(latest)
        start = end - timedelta(days=days - 1)
        where, args = ["date BETWEEN ? AND ?"], [start.isoformat(), end.isoformat()]
        _scope(where, args, zone, group)
        rows = conn.execute(
            f"""SELECT date, SUM(CASE WHEN matched=1 THEN detections ELSE 0 END) AS matched,
                       SUM(CASE WHEN matched=0 THEN detections ELSE 0 END) AS unmatched
                FROM maritime_sar_daily WHERE {' AND '.join(where)} GROUP BY date ORDER BY date""", args).fetchall()
        return {"latest_date": latest, "start": start.isoformat(), "rows": [dict(r) for r in rows]}
