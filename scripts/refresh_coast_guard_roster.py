"""Refresh the coast-guard hull roster from Global Fishing Watch's identity index.

Queries the identity index with SQL-ish `where` filters per force, classifies
each self-reported identity with the same rules the presence ingest uses
(scraper/scrapers/gfw_coast_guard.py::classify), and upserts
coast_guard_vessels (source='gfw_identity'). Flags anomalies:

  mid_mismatch   MMSI's MID prefix (first 3 digits) is not one of the force's
                 national MIDs — the CCG spoof signature (14513 under 766…,
                 14057 under 431…).
  flag_mismatch  self-reported flag != the force's flag.
  name_change    the same MMSI has carried a different coast-guard name.

Rows an analyst has set status='confirmed'/'rejected' keep that status; only
'auto' rows are rewritten. Run monthly (or after a big backfill) — it also
widens the flag filter the big-zone presence pulls use, so newly seen spoofed
MIDs start being kept.

Flags: --db (target another worktree's DB), --dry-run, --force CCG|CGA|JCG|USCG.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from scraper.scrapers.gfw_coast_guard import GFWClient, FORCE_FLAGS, ROSTER_SEED_PATH, classify  # noqa: E402, triage_roster
from scraper.utils.db import get_connection  # noqa: E402

# National MIDs (ITU). Taiwan 416; China 412/413/414; Japan 431/432; US 303 (Alaska), 338, 366–369.
FORCE_MIDS = {
    "CCG": {"412", "413", "414"},
    "CGA": {"416"},
    "JCG": {"431", "432"},
    "USCG": {"303", "338", "366", "367", "368", "369"},
}

# Prefix-anchored LIKEs only: a leading-wildcard LIKE ('%COAST%') over the
# whole identity index takes 60–100 s PER PAGE at GFW (measured 2026-08-25);
# the prefix forms below return in <1 s. The CCG list is several queries
# because the fleet broadcasts under several spellings, and deliberately
# has no flag clause — MID spoofing is what we're trying to catch.
WHERE = {
    "CCG": [
        "shipname LIKE 'CHINACOASTGUARD%'", "shipname LIKE 'CHINA COAST%'", "shipname LIKE 'CHINAGUARDCOAST%'",
        "shipname LIKE 'ZHONGGUO%HAIJING%'", "shipname LIKE 'HAIJING%'", "shipname LIKE 'HAI JING%'",
        "shipname LIKE 'CCG%'",
    ],
    "CGA": ["flag = 'TWN' AND shipname LIKE 'CG%'"],
    "USCG": ["flag = 'USA' AND shipname LIKE 'USCGC%'", "flag = 'USA' AND shipname LIKE 'CGC %'",
             "flag = 'USA' AND shipname LIKE 'CG %'"],
}


def jcg_wheres() -> list[str]:
    # GFW's `where` parser rejects IN(...) ("SCALAR functions are not
    # supported") — one equality query per JCG name (<1 s each).
    seed = json.loads(ROSTER_SEED_PATH.read_text())
    return [f"flag = 'JPN' AND shipname = '{n}'" for n in seed["JCG"]["names"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", choices=sorted(FORCE_FLAGS))
    args = ap.parse_args()

    client = GFWClient(sleep=0.5)
    conn = get_connection(args.db)
    existing = {r["mmsi"]: dict(r) for r in conn.execute("SELECT * FROM coast_guard_vessels")}
    seed = json.loads(ROSTER_SEED_PATH.read_text())
    pennants = seed["JCG"].get("pennants", {})

    forces = [args.force] if args.force else ["CCG", "CGA", "JCG", "USCG"]
    upserts, anomalies = [], 0
    for force in forces:
        wheres = jcg_wheres() if force == "JCG" else WHERE[force]
        idents = []
        for where in wheres:
            idents += client.identity_where(where)
        best: dict[str, dict] = {}
        for s in idents:
            name = (s.get("shipname") or "").strip()
            cls, hull = classify(name, s.get("flag"))
            if cls != force:
                continue
            mmsi = str(s.get("ssvid") or "")
            if not mmsi:
                continue
            rec = {
                "mmsi": mmsi, "vessel_id": s.get("id"), "name": name, "flag": s.get("flag"), "force": force,
                "hull_no": hull or (pennants.get(name.upper()) if force == "JCG" else None),
                "imo": (s.get("imo") or None), "callsign": (s.get("callsign") or None),
                "first_seen": (s.get("transmissionDateFrom") or "")[:10] or None,
                "last_seen": (s.get("transmissionDateTo") or "")[:10] or None,
            }
            prev = best.get(mmsi)
            if prev is None:
                best[mmsi] = rec
            else:
                # keep the latest identity, but extend the seen window and note renames
                if (rec["last_seen"] or "") > (prev["last_seen"] or ""):
                    if prev["name"] != rec["name"]:
                        rec.setdefault("_names", set()).update({prev["name"], rec["name"]})
                    rec["first_seen"] = min(filter(None, [prev["first_seen"], rec["first_seen"]]), default=None)
                    rec["_names"] = rec.get("_names", set()) | prev.get("_names", set())
                    best[mmsi] = rec
                else:
                    if prev["name"] != rec["name"]:
                        prev.setdefault("_names", set()).update({prev["name"], rec["name"]})
                    prev["last_seen"] = max(filter(None, [prev["last_seen"], rec["last_seen"]]), default=None)
        for rec in best.values():
            flags = []
            if rec["mmsi"][:3] not in FORCE_MIDS[force]:
                flags.append("mid_mismatch")
            if rec["flag"] and rec["flag"] != FORCE_FLAGS[force]:
                flags.append("flag_mismatch")
            if len(rec.pop("_names", set())) > 1:
                flags.append("name_change")
            rec["anomaly_flags"] = json.dumps(flags) if flags else None
            anomalies += bool(flags)
            upserts.append(rec)
        print(f"  {force}: {len(idents)} identity records -> {len(best)} hulls")

    if args.dry_run:
        for r in upserts[:40]:
            print("   ", r["force"], r["mmsi"], r["name"], r["flag"], r["hull_no"], r["first_seen"], "->", r["last_seen"], r["anomaly_flags"] or "")
        print(f"dry-run: {len(upserts)} hulls, {anomalies} with anomalies (nothing written)")
        return

    n_new = n_upd = 0
    for r in upserts:
        prev = existing.get(r["mmsi"])
        if prev and prev["status"] != "auto":
            # analyst-reviewed: only refresh the seen window + anomaly flags
            conn.execute("UPDATE coast_guard_vessels SET last_seen=?, anomaly_flags=?, updated_at=datetime('now') WHERE mmsi=?",
                         (r["last_seen"], r["anomaly_flags"], r["mmsi"]))
            n_upd += 1
            continue
        conn.execute(
            """INSERT INTO coast_guard_vessels (mmsi, vessel_id, name, flag, force, hull_no, imo, callsign, first_seen, last_seen, source, anomaly_flags)
               VALUES (:mmsi, :vessel_id, :name, :flag, :force, :hull_no, :imo, :callsign, :first_seen, :last_seen, 'gfw_identity', :anomaly_flags)
               ON CONFLICT(mmsi) DO UPDATE SET vessel_id=excluded.vessel_id, name=excluded.name, flag=excluded.flag,
                 force=excluded.force, hull_no=coalesce(excluded.hull_no, coast_guard_vessels.hull_no), imo=excluded.imo,
                 callsign=excluded.callsign, first_seen=excluded.first_seen, last_seen=excluded.last_seen,
                 source='gfw_identity', anomaly_flags=excluded.anomaly_flags, updated_at=datetime('now')""",
            r,
        )
        n_new += prev is None
        n_upd += prev is not None
    conn.commit()
    total = conn.execute("SELECT force, count(*) FROM coast_guard_vessels GROUP BY force").fetchall()
    print(f"roster: {n_new} new, {n_upd} updated, {anomalies} with anomaly flags; totals: {[tuple(t) for t in total]}")
    t = triage_roster(conn)
    print(f"triage: confirmed {t['confirmed']}, rejected {t['rejected']} (purged {t['purged_presence']} presence rows), left auto {t['left']}")


if __name__ == "__main__":
    main()
