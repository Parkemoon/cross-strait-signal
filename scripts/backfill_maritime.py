#!/usr/bin/env python3
"""Resumable backfill for the Maritime civilian-fleet + SAR layer (Phase 2g).

Two kinds, both monthly windows per zone, both skipping (kind, zone, period)
pairs already logged ok in maritime_pulls:

  civil  re-requests the SAME 4Wings presence report the coast-guard backfill
         used and keeps the non-CG rows (maritime_civil_daily / _presence /
         _vessels). The CG rows are NOT re-upserted (coast_guard_presence is
         left alone) — this run only fills the civilian tables.
  sar    Sentinel-1 detections per zone (maritime_sar_daily).

Launch big runs detached (setsid nohup … &) — ~1 request per zone-month per
kind, ~20–40 s each, and GFW allows one concurrent 4Wings report per token,
so the 6-hourly pipeline tick will see 429s while this runs (its client
retries with backoff).

  scripts/backfill_maritime.py --start 2023-01-01                 # both kinds, all zones
  scripts/backfill_maritime.py --start 2017-01-01 --kinds sar      # SAR only
  scripts/backfill_maritime.py --start 2020-01-01 --zones taiwan_bank --db /var/www/cross-strait-signal/db/cross_strait_signal.db
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from scraper.scrapers.gfw_civil import ingest_civil_rows, pull_sar_zone  # noqa: E402
from scraper.scrapers.gfw_coast_guard import (  # noqa: E402
    FORCE_FLAGS, UNFILTERED_ZONES, GFWClient, _extra_ccg_flags, classify, load_zones, month_windows,
)
from scraper.utils.db import get_connection  # noqa: E402


def _done(conn, kind: str, zone_id: str, start: str, end: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM maritime_pulls WHERE kind=? AND zone_id=? AND period_start=? AND period_end=? AND status='ok' LIMIT 1",
        (kind, zone_id, start, end)).fetchone() is not None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (default: 6 days ago — GFW lag)")
    ap.add_argument("--kinds", default="civil,sar", help="comma list of civil,sar")
    ap.add_argument("--zones", default=None, help="comma list of zone ids (default all)")
    ap.add_argument("--db", default=None)
    ap.add_argument("--force", action="store_true", help="re-pull periods already logged ok")
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args()

    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]
    for k in kinds:
        if k not in ("civil", "sar"):
            ap.error(f"unknown kind {k}")
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=6)
    zone_ids = {z.strip() for z in args.zones.split(",")} if args.zones else None

    conn = get_connection(args.db)
    client = GFWClient(sleep=args.sleep)
    extra = _extra_ccg_flags(conn)
    is_cg = lambda n, f, t: classify(n, f, t)[0] is not None  # noqa: E731
    windows = month_windows(start, end)
    zones = [z for z in load_zones() if not zone_ids or z["id"] in zone_ids]
    total = len(windows) * len(zones) * len(kinds)
    print(f"[maritime-backfill] {len(zones)} zones × {len(windows)} months × {kinds} = {total} pulls", flush=True)

    n = 0
    for kind in kinds:
        for z in zones:
            flags = None if z["id"] in UNFILTERED_ZONES else (set(FORCE_FLAGS.values()) | extra)
            for s, e in windows:
                n += 1
                if not args.force and _done(conn, kind, z["id"], s, e):
                    continue
                try:
                    if kind == "civil":
                        rows = client.presence_report(z["geometry"], s, e, flags)
                        d, h = ingest_civil_rows(conn, z["id"], s, e, rows, is_cg)
                        conn.commit()
                        print(f"  [{n}/{total}] civil {z['id']:20s} {s}..{e}: {len(rows)} cell-rows → {d} day/class rows, {h} hull rows", flush=True)
                    else:
                        r, k = pull_sar_zone(conn, client, z, s, e)
                        print(f"  [{n}/{total}] sar   {z['id']:20s} {s}..{e}: {r} cell-rows → {k} day/class rows", flush=True)
                except Exception as ex:  # noqa: BLE001
                    conn.commit()
                    print(f"  [{n}/{total}] {kind} {z['id']:20s} {s}..{e}: ERROR {type(ex).__name__}: {str(ex)[:200]}", flush=True)
    conn.close()
    print("[maritime-backfill] done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
