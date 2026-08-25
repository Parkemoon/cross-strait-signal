"""One-shot / resumable backfill of coast_guard_presence from Global Fishing Watch.

Pulls the 4Wings presence report month by month for every zone in
data/coast_guard_zones.geojson (or --zones a,b), classifies coast-guard
hulls, and upserts (date, zone, mmsi) rows. Periods already logged 'ok' in
coast_guard_pulls are skipped unless --force, so it can be re-run after an
interruption. GFW covers 2017-01-01 onward; data lags ~5 days.

Examples:
  python scripts/backfill_coast_guard.py --start 2024-03-01 --end 2024-03-31 --zones kinmen_prohibited,kinmen_restricted
  python scripts/backfill_coast_guard.py --start 2020-01-01            # full backfill, all zones
  python scripts/backfill_coast_guard.py --start 2017-01-01 --db /var/www/cross-strait-signal/db/cross_strait_signal.db

Launch long runs detached (setsid nohup …) — a full 2017→ backfill is
~11 zones × ~115 months ≈ 1,250 requests at a few seconds each.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from scraper.scrapers.gfw_coast_guard import GFWClient, _extra_ccg_flags, load_zones, month_windows, pull_zone  # noqa: E402
from scraper.utils.db import get_connection  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2017-01-01")
    ap.add_argument("--end", default=(date.today() - timedelta(days=1)).isoformat())
    ap.add_argument("--zones", help="comma-separated zone ids (default: all)")
    ap.add_argument("--db")
    ap.add_argument("--force", action="store_true", help="re-pull periods already logged ok")
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args()

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    zones = load_zones()
    if args.zones:
        want = set(args.zones.split(","))
        zones = [z for z in zones if z["id"] in want]
        missing = want - {z["id"] for z in zones}
        if missing:
            sys.exit(f"unknown zones: {sorted(missing)}")

    conn = get_connection(args.db)
    client = GFWClient(sleep=args.sleep)
    extra = _extra_ccg_flags(conn)
    done = set()
    if not args.force:
        done = {(r[0], r[1], r[2]) for r in conn.execute(
            "SELECT zone_id, period_start, period_end FROM coast_guard_pulls WHERE status='ok'")}

    windows = month_windows(start, end)
    total = len(zones) * len(windows)
    n = kept_total = 0
    t0 = datetime.now()
    for z in zones:
        for s, e in windows:
            n += 1
            if (z["id"], s, e) in done:
                continue
            try:
                rows, kept = pull_zone(conn, client, z, s, e, extra)
            except Exception as ex:  # noqa: BLE001 — logged in coast_guard_pulls; keep going
                print(f"  [{n}/{total}] {z['id']:20s} {s}..{e}: ERROR {ex}", flush=True)
                continue
            kept_total += kept
            print(f"  [{n}/{total}] {z['id']:20s} {s}..{e}: {rows:>7} rows -> {kept:>4} hull-days", flush=True)
    print(f"done: {kept_total} hull-days upserted in {datetime.now() - t0}")


if __name__ == "__main__":
    main()
