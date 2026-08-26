"""Coast Guard tracker endpoints (Phase 2e).

Serves coast_guard_presence / coast_guard_vessels / coast_guard_pulls
(built by scraper/scrapers/gfw_coast_guard.py from Global Fishing Watch's
presence report) and the zone polygons in data/coast_guard_zones.geojson.

Numbers are "hull-days": one row per (day, zone, hull) with the hours of AIS
presence inside the zone polygon. They are a FLOOR — AIS is self-reported
and the CCG switches it off during some Kinmen incursions (per the CGA) — and
the zone polygons are a uniform-buffer approximation of the MND 公告 bands.
Both caveats belong in the UI copy.

No editorial gate on presence (deterministic third-party aggregate); the
roster carries an analyst status so mis-classified hulls can be rejected —
rejected hulls are excluded from every aggregate here.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from api.auth import require_admin
from api.database import db_conn

router = APIRouter(prefix="/api/military/coast-guard", tags=["coast-guard"])

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ZONES_PATH = os.path.join(_ROOT, "data", "coast_guard_zones.geojson")
FORCES = ("CCG", "CGA", "JCG", "USCG")
FORCE_LABELS = {"CCG": "China Coast Guard", "CGA": "Taiwan Coast Guard", "JCG": "Japan Coast Guard", "USCG": "US Coast Guard"}

# Presence rows for hulls an analyst rejected are excluded everywhere.
_NOT_REJECTED = "p.mmsi NOT IN (SELECT mmsi FROM coast_guard_vessels WHERE status='rejected')"
# Distinct-hull key. Several CCG hulls broadcast under TWO MMSIs (the old
# 412/413-7xx series and the 2023+ 41387-5xxx series — 2301–2305, 2501/2502,
# 3301/3302, 3501, 8026 …), so COUNT(DISTINCT mmsi) overstates hulls by ~10%.
# Key on force + hull number where the roster parsed one, else the AIS name
# (JCG hulls carry no number), else the MMSI. Every query counting hulls must
# carry _VESSEL_JOIN.
_VESSEL_JOIN = "LEFT JOIN coast_guard_vessels v ON v.mmsi = p.mmsi"
_HULL_KEY = "COALESCE(p.force || ':' || v.hull_no, p.force || ':' || NULLIF(TRIM(p.name), ''), p.mmsi)"

# Data caveats the UI must render next to the series — structured so the
# frontend can't draw the chart without them. Derived from the 2020→ backfill
# audit (2026-08-26, SESSION_LOG); re-check when the backfill extends to 2017.
CAVEATS = [
    {"key": "ais_floor", "scope": "all",
     "en": "Counts are AIS-visible presence only — a floor, not activity. AIS is self-reported; the CCG "
           "switches transponders off on some Kinmen runs and Taiwan's CGA broadcasts only ~38 of its hulls.",
     "zh": "所有數字僅計入 AIS 可見的存在，為下限而非實際活動量。AIS 為船舶自行播報；海警部分金門航次關閉應答器，海巡署亦僅約 38 艘船播報。"},
    {"key": "kinmen_go_dark", "scope": "kinmen",
     "en": "Kinmen: the AIS-visible CCG series falls from ~15–23 hull-days/month (H1 2024) to 2–8/month (2025–26) "
           "while the CGA reports a steady ~4 incursions/month. Read the gap as go-dark behaviour, not de-escalation.",
     "zh": "金門：AIS 可見的海警船日從 2024 上半年每月約 15–23 降至 2025–26 年每月 2–8，而海巡署通報每月約 4 次侵擾未減。差距應解讀為關閉應答器，而非降溫。"},
    {"key": "ccg_pre_2023", "scope": "CCG",
     "en": "CCG hull-days step up ~5× in 2023 as GFW's satellite-AIS coverage and CCG east-of-Taiwan patrols both "
           "grew; pre-2023 CCG figures are unreliably low and not comparable.",
     "zh": "2023 年海警船日躍升約 5 倍，同時反映 GFW 衛星 AIS 覆蓋擴大與海警東部巡航增加；2023 年前的海警數字偏低且不可比較。"},
    {"key": "uscg_absent", "scope": "USCG",
     "en": "US Coast Guard cutters do not broadcast AIS in theatre — 2 hull-days since 2020. Not a signal.",
     "zh": "美國海岸防衛隊船艦在此海域不播報 AIS，2020 年以來僅 2 船日，不具訊號意義。"},
    {"key": "jcg_east_only", "scope": "JCG",
     "en": "Japan Coast Guard presence is almost entirely the east-coast box — Yonaguni/Senkaku patrols brushing the "
           "polygon, not Taiwan-related activity.",
     "zh": "日本海上保安廳的存在幾乎全在東部海域框，屬與那國／尖閣巡航掠過多邊形，非涉台活動。"},
    {"key": "cga_home_waters", "scope": "CGA",
     "en": "Most CGA hull-days are routine patrols inside Taiwan's own contiguous zone; only the Kinmen, Matsu, "
           "Pratas and median-line zones carry meaning.",
     "zh": "海巡署船日多為本國鄰接區內例行巡邏；僅金門、馬祖、東沙與海峽中線區域具分析意義。"},
    {"key": "hours_coarse", "scope": "all",
     "en": "Hours are GFW's integer hour-cells (floor 1 h per hull-day); data lags ~5 days.",
     "zh": "小時數為 GFW 整數小時格（每船日下限 1 小時）；資料延遲約 5 天。"},
]


def _zones_fc() -> dict:
    with open(_ZONES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _latest_date(conn) -> Optional[str]:
    r = conn.execute("SELECT MAX(date) FROM coast_guard_presence").fetchone()
    return r[0] if r else None


@router.get("/zones")
def zones(geometry: bool = Query(False, description="include polygon geometry")):
    fc = _zones_fc()
    out = []
    for f in fc["features"]:
        p = dict(f["properties"])
        if geometry:
            p["geometry"] = f["geometry"]
        out.append(p)
    return {"zones": out}


@router.get("/summary")
def summary(days: int = Query(30, ge=7, le=365)):
    """Headline numbers: per-force hull-days this window vs the previous one,
    per-zone breakdown for the window, data freshness, roster + anomaly counts."""
    with db_conn() as conn:
        latest = _latest_date(conn)
        if not latest:
            return {"latest_date": None, "days": days, "forces": [], "zones": [], "roster": {}, "anomalies": 0}
        end = date.fromisoformat(latest)
        start = end - timedelta(days=days - 1)
        prev_start = start - timedelta(days=days)
        prev_end = start - timedelta(days=1)

        def window(a: date, b: date):
            rows = conn.execute(
                f"""SELECT p.force, COUNT(*) AS hull_days, ROUND(SUM(p.hours),1) AS hours, COUNT(DISTINCT {_HULL_KEY}) AS hulls
                    FROM coast_guard_presence p {_VESSEL_JOIN} WHERE p.date BETWEEN ? AND ? AND {_NOT_REJECTED}
                    GROUP BY p.force""", (a.isoformat(), b.isoformat())).fetchall()
            return {r["force"]: dict(r) for r in rows}

        cur, prev = window(start, end), window(prev_start, prev_end)
        forces = []
        for f in FORCES:
            c, p = cur.get(f, {}), prev.get(f, {})
            forces.append({"force": f, "label": FORCE_LABELS[f],
                           "hull_days": c.get("hull_days", 0), "hours": c.get("hours", 0.0), "hulls": c.get("hulls", 0),
                           "prev_hull_days": p.get("hull_days", 0)})
        zrows = conn.execute(
            f"""SELECT p.zone_id, p.force, COUNT(*) AS hull_days, COUNT(DISTINCT {_HULL_KEY}) AS hulls
                FROM coast_guard_presence p {_VESSEL_JOIN} WHERE p.date BETWEEN ? AND ? AND {_NOT_REJECTED}
                GROUP BY p.zone_id, p.force""", (start.isoformat(), end.isoformat())).fetchall()
        by_zone: dict[str, dict] = {}
        for r in zrows:
            z = by_zone.setdefault(r["zone_id"], {"zone_id": r["zone_id"], "forces": {}})
            z["forces"][r["force"]] = {"hull_days": r["hull_days"], "hulls": r["hulls"]}
        labels = {f["properties"]["id"]: f["properties"] for f in _zones_fc()["features"]}
        zones_out = []
        for zid, props in labels.items():
            z = by_zone.get(zid, {"zone_id": zid, "forces": {}})
            z["label_en"], z["label_zh"], z["group"] = props["label_en"], props["label_zh"], props["group"]
            zones_out.append(z)
        roster = {r["force"]: r["n"] for r in conn.execute(
            "SELECT force, COUNT(*) AS n FROM coast_guard_vessels WHERE status != 'rejected' GROUP BY force")}
        anomalies = conn.execute(
            "SELECT COUNT(*) FROM coast_guard_vessels WHERE anomaly_flags IS NOT NULL AND status != 'rejected'").fetchone()[0]
        # Hulls the deterministic triage could not settle AND that carry presence
        # in the window — the only rows an analyst actually needs to look at.
        unreviewed = conn.execute(
            """SELECT COUNT(*) FROM coast_guard_vessels v WHERE v.status='auto'
               AND EXISTS (SELECT 1 FROM coast_guard_presence p WHERE p.mmsi=v.mmsi AND p.date BETWEEN ? AND ?)""",
            (start.isoformat(), end.isoformat())).fetchone()[0]
        pull = conn.execute("SELECT MAX(pulled_at) FROM coast_guard_pulls WHERE status='ok'").fetchone()[0]
        # Mirror KPI: PRC vessels the CGA expelled / detained, trailing 12 reported months.
        enf = conn.execute(
            """SELECT MAX(period) AS latest, SUM(expelled) AS expelled, SUM(detained) AS detained, COUNT(*) AS n
               FROM (SELECT period, expelled, detained FROM cga_enforcement
                     WHERE region='TW' AND category='fishing_prc' AND granularity='month' AND source='monthly'
                     ORDER BY period DESC LIMIT 12)""").fetchone()
        enforcement = {"latest_month": enf["latest"], "months": enf["n"], "expelled": enf["expelled"] or 0,
                       "detained": enf["detained"] or 0} if enf and enf["n"] else None
        first_date = conn.execute("SELECT MIN(date) FROM coast_guard_presence").fetchone()[0]
        return {"latest_date": latest, "window_start": start.isoformat(), "days": days, "forces": forces,
                "zones": zones_out, "roster": roster, "anomalies": anomalies, "unreviewed": unreviewed, "last_pull_at": pull,
                "enforcement": enforcement, "coverage_start": first_date, "caveats": CAVEATS}


@router.get("/daily")
def daily(
    zone: Optional[str] = Query(None, description="zone id; omit for all zones combined (a hull in two zones counts twice)"),
    group: Optional[str] = Query(None, description="zone group (kinmen/matsu/contiguous/...) — sums its zones"),
    force: Optional[str] = Query(None),
    days: int = Query(90, ge=7, le=3660),
):
    """Per-day, per-force hull-days (+ hours, distinct hulls) for a chart."""
    if force and force not in FORCES:
        raise HTTPException(400, f"force must be one of {FORCES}")
    with db_conn() as conn:
        latest = _latest_date(conn)
        if not latest:
            return {"latest_date": None, "rows": []}
        end = date.fromisoformat(latest)
        start = end - timedelta(days=days - 1)
        where, args = [f"p.date BETWEEN ? AND ?", _NOT_REJECTED], [start.isoformat(), end.isoformat()]
        if zone:
            where.append("p.zone_id = ?"); args.append(zone)
        if group:
            ids = [f["properties"]["id"] for f in _zones_fc()["features"] if f["properties"]["group"] == group]
            if not ids:
                raise HTTPException(400, "unknown group")
            where.append(f"p.zone_id IN ({','.join('?' * len(ids))})"); args += ids
        if force:
            where.append("p.force = ?"); args.append(force)
        rows = conn.execute(
            f"""SELECT p.date, p.force, COUNT(*) AS hull_days, ROUND(SUM(p.hours),1) AS hours, COUNT(DISTINCT {_HULL_KEY}) AS hulls
                FROM coast_guard_presence p {_VESSEL_JOIN} WHERE {' AND '.join(where)}
                GROUP BY p.date, p.force ORDER BY p.date""", args).fetchall()
        return {"latest_date": latest, "start": start.isoformat(), "rows": [dict(r) for r in rows]}


@router.get("/monthly")
def monthly(zone: Optional[str] = None, group: Optional[str] = None, force: Optional[str] = None,
            months: int = Query(60, ge=1, le=200)):
    """Per-month hull-days by force — the long-series view (backfill runs to 2017)."""
    with db_conn() as conn:
        where, args = [_NOT_REJECTED], []
        if zone:
            where.append("p.zone_id = ?"); args.append(zone)
        if group:
            ids = [f["properties"]["id"] for f in _zones_fc()["features"] if f["properties"]["group"] == group]
            where.append(f"p.zone_id IN ({','.join('?' * len(ids))})"); args += ids
        if force:
            where.append("p.force = ?"); args.append(force)
        rows = conn.execute(
            f"""SELECT substr(p.date,1,7) AS month, p.force, COUNT(*) AS hull_days, ROUND(SUM(p.hours),1) AS hours,
                       COUNT(DISTINCT {_HULL_KEY}) AS hulls
                FROM coast_guard_presence p {_VESSEL_JOIN} WHERE {' AND '.join(where)}
                GROUP BY month, p.force ORDER BY month DESC LIMIT ?""", args + [months * len(FORCES)]).fetchall()
        return {"rows": [dict(r) for r in reversed(rows)]}


@router.get("/vessels")
def vessels(force: Optional[str] = None, status: Optional[str] = None, anomalies: bool = False,
            days: int = Query(30, ge=1, le=3660), limit: int = Query(300, ge=1, le=2000)):
    """Roster with activity in the trailing window (hull-days across all zones)."""
    with db_conn() as conn:
        latest = _latest_date(conn)
        end = date.fromisoformat(latest) if latest else date.today()
        start = (end - timedelta(days=days - 1)).isoformat()
        where, args = ["1=1"], []
        if force:
            where.append("v.force = ?"); args.append(force)
        if status:
            where.append("v.status = ?"); args.append(status)
        if anomalies:
            where.append("v.anomaly_flags IS NOT NULL")
        rows = conn.execute(
            f"""SELECT v.*, COALESCE(a.hull_days,0) AS hull_days, COALESCE(a.hours,0) AS hours, a.zones
                FROM coast_guard_vessels v
                LEFT JOIN (SELECT mmsi, COUNT(*) AS hull_days, ROUND(SUM(hours),1) AS hours,
                                  GROUP_CONCAT(DISTINCT zone_id) AS zones
                           FROM coast_guard_presence WHERE date >= ? GROUP BY mmsi) a ON a.mmsi = v.mmsi
                WHERE {' AND '.join(where)}
                ORDER BY hull_days DESC, v.last_seen DESC LIMIT ?""", [start] + args + [limit]).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["anomaly_flags"] = json.loads(d["anomaly_flags"]) if d.get("anomaly_flags") else []
            d["zones"] = d["zones"].split(",") if d.get("zones") else []
            out.append(d)
        return {"latest_date": latest, "window_start": start, "vessels": out}


@router.get("/vessels/{mmsi}")
def vessel(mmsi: str, days: int = Query(365, ge=1, le=3660)):
    with db_conn() as conn:
        v = conn.execute("SELECT * FROM coast_guard_vessels WHERE mmsi = ?", (mmsi,)).fetchone()
        if not v:
            raise HTTPException(404, "unknown hull")
        latest = _latest_date(conn)
        end = date.fromisoformat(latest) if latest else date.today()
        start = (end - timedelta(days=days - 1)).isoformat()
        rows = conn.execute(
            """SELECT date, zone_id, hours, cells, lat, lon, entry_ts, exit_ts FROM coast_guard_presence
               WHERE mmsi = ? AND date >= ? ORDER BY date""", (mmsi, start)).fetchall()
        d = dict(v)
        d["anomaly_flags"] = json.loads(d["anomaly_flags"]) if d.get("anomaly_flags") else []
        return {"vessel": d, "presence": [dict(r) for r in rows]}


@router.get("/encounters")
def encounters(days: int = Query(30, ge=1, le=3660), zone: Optional[str] = None):
    """v1 encounter = a CCG hull and a CGA/JCG/USCG hull present in the SAME
    zone on the SAME day. Daily/1-km data can't show a 5-nm intercept, so this
    is 'co-presence', not 'interaction' — label it that way."""
    with db_conn() as conn:
        latest = _latest_date(conn)
        if not latest:
            return {"rows": []}
        end = date.fromisoformat(latest)
        start = (end - timedelta(days=days - 1)).isoformat()
        where, args = ["p.date >= ?", _NOT_REJECTED], [start]
        if zone:
            where.append("p.zone_id = ?"); args.append(zone)
        rows = conn.execute(
            f"""SELECT p.date, p.zone_id,
                       SUM(p.force='CCG') AS ccg, SUM(p.force='CGA') AS cga, SUM(p.force='JCG') AS jcg, SUM(p.force='USCG') AS uscg,
                       GROUP_CONCAT(CASE WHEN p.force='CCG' THEN p.name END, '|') AS ccg_names,
                       GROUP_CONCAT(CASE WHEN p.force!='CCG' THEN p.force||':'||p.name END, '|') AS other_names
                FROM coast_guard_presence p {_VESSEL_JOIN} WHERE {' AND '.join(where)}
                GROUP BY p.date, p.zone_id
                HAVING ccg > 0 AND (cga + jcg + uscg) > 0
                ORDER BY p.date DESC, p.zone_id""", args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["ccg_names"] = [x for x in (d["ccg_names"] or "").split("|") if x]
            d["other_names"] = [x for x in (d["other_names"] or "").split("|") if x]
            out.append(d)
        return {"latest_date": latest, "start": start, "rows": out}


@router.get("/enforcement")
def enforcement(region: str = Query("TW", description="'TW' national, or a county name e.g. 金門縣 / 連江縣 / 澎湖縣"),
                category: str = Query("fishing_prc"), months: int = Query(60, ge=1, le=240)):
    """The mirror series: vessels Taiwan's CGA expelled / detained for trespass
    fishing (official CGA statistics — cga_enforcement). Returns three
    series so the chart can choose: monthly national (表8-1, monthly reports merged
    over the yearbooks' month tables), annual national
    (表8-1 / yearbooks, plus the 護永專案 manual rows with fines/confiscations),
    and the county year-to-date snapshots (表8-3, newest report wins)."""
    with db_conn() as conn:
        # One row per month: the monthly report wins where it exists (recent ~12
        # months on the CGA site), the yearbooks' 表8-1 fill the back-history.
        monthly = conn.execute(
            """SELECT period, expelled, detained, cases, source, source_ref FROM cga_enforcement e
               WHERE region='TW' AND category=? AND granularity='month' AND source IN ('monthly','yearbook')
                 AND NOT EXISTS (SELECT 1 FROM cga_enforcement m WHERE m.period=e.period AND m.region=e.region
                                   AND m.category=e.category AND m.granularity='month'
                                   AND m.source='monthly' AND e.source='yearbook')
               ORDER BY period DESC LIMIT ?""", (category, months)).fetchall()
        annual = conn.execute(
            """SELECT period, granularity, expelled, detained, fined_vessels, fines_ntd_m, confiscated, source, source_ref
               FROM cga_enforcement WHERE region='TW' AND category=? AND granularity IN ('year','half')
               ORDER BY period, CASE source WHEN 'yearbook' THEN 0 WHEN 'monthly' THEN 1 ELSE 2 END""",
            (category,)).fetchall()
        county = conn.execute(
            """SELECT period, granularity, region, expelled, detained, source, source_ref FROM cga_enforcement
               WHERE region=? AND category=? ORDER BY period""", (region, category)).fetchall() if region != "TW" else []
        latest = conn.execute("SELECT MAX(period) FROM cga_enforcement WHERE granularity='month'").fetchone()[0]
        return {"latest_month": latest, "region": region, "category": category,
                "monthly": [dict(r) for r in reversed(monthly)],
                "annual": [dict(r) for r in annual],
                "county": [dict(r) for r in county]}


@router.patch("/vessels/{mmsi}")
def patch_vessel(mmsi: str, payload: dict = Body(...), _admin: None = Depends(require_admin)):
    """Analyst roster review: status (auto/confirmed/rejected), force, hull_no, notes."""
    allowed = {"status", "force", "hull_no", "notes"}
    fields = {k: v for k, v in payload.items() if k in allowed}
    if not fields:
        raise HTTPException(400, f"nothing to update; allowed: {sorted(allowed)}")
    if "status" in fields and fields["status"] not in ("auto", "confirmed", "rejected"):
        raise HTTPException(400, "bad status")
    if "force" in fields and fields["force"] not in FORCES:
        raise HTTPException(400, "bad force")
    with db_conn() as conn:
        if not conn.execute("SELECT 1 FROM coast_guard_vessels WHERE mmsi=?", (mmsi,)).fetchone():
            raise HTTPException(404, "unknown hull")
        sets = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE coast_guard_vessels SET {sets}, updated_at = datetime('now') WHERE mmsi = ?",
                     [*fields.values(), mmsi])
        if "force" in fields:
            conn.execute("UPDATE coast_guard_presence SET force = ? WHERE mmsi = ?", (fields["force"], mmsi))
        conn.commit()
        v = conn.execute("SELECT * FROM coast_guard_vessels WHERE mmsi = ?", (mmsi,)).fetchone()
        return dict(v)
