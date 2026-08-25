"""Backfill cga_enforcement from the CGA yearbooks + the 護永專案 summary page.

  * Yearbooks (海巡統計年報, 110–114年 linked from the homepage): 表8-1 gives
    annual national rows back to 2013 in EVERY edition (newest edition wins),
    表8-3 gives that year's per-county split.
  * Every monthly report currently linked from the homepage (recent ~5 months).
  * The 護永專案 summary table (image on ct?xItem=101246, transcribed by eye
    2026-08-25 — see COAST_GUARD_TRACKER_SCOPE.md Part B): PRC fishing vessels
    2016H2 → 2026H1 with 裁罰 / 罰鍰 / 沒入, which the tables above don't carry.
    Stored as source='manual' with the page URL as source_url.

Flags: --db, --skip-yearbooks, --skip-monthly, --skip-manual.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scraper.scrapers.cga_stats_scraper import _client, discover_reports, ingest_report  # noqa: E402
from scraper.utils.db import get_connection  # noqa: E402

HUYONG_URL = "https://www.cga.gov.tw/GipOpen/wSite/ct?xItem=101246&ctNode=9609&mp=safsee"
# (period, granularity, expelled, detained, fined_vessels, fines_ntd_m, confiscated) — PRC fishing vessels
HUYONG = [
    ("2016-H2", "half", 488, 53, 47, 45.9, 5),
    ("2017", "year", 718, 77, 49, 43.0, 22),
    ("2018", "year", 1293, 86, 61, 60.9, 23),
    ("2019", "year", 1003, 81, 67, 54.8, 20),
    ("2020", "year", 1697, 19, 13, 14.9, 6),
    ("2021", "year", 1786, 28, 23, 36.1, 5),
    ("2022", "year", 1271, 20, 19, 16.5, 1),
    ("2023", "year", 1009, 28, 26, 22.0, 2),
    ("2024", "year", 1135, 9, 7, 7.0, 1),
    ("2025", "year", 907, 15, 4, 4.0, 10),
    ("2026-H1", "half", 385, 11, 3, 2.7, 8),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db")
    ap.add_argument("--skip-yearbooks", action="store_true")
    ap.add_argument("--skip-monthly", action="store_true")
    ap.add_argument("--skip-manual", action="store_true")
    args = ap.parse_args()
    conn = get_connection(args.db)

    if not args.skip_manual:
        for period, gran, exp, det, fined, fines, conf in HUYONG:
            conn.execute(
                """INSERT INTO cga_enforcement (period, granularity, region, category, expelled, detained,
                                                fined_vessels, fines_ntd_m, confiscated, source, source_ref, source_url)
                   VALUES (?, ?, 'TW', 'fishing_prc', ?, ?, ?, ?, ?, 'manual', '護永專案查處非法越界大陸漁船成效 (image table, transcribed 2026-08-25)', ?)
                   ON CONFLICT(period, granularity, region, category, source) DO UPDATE SET
                     expelled=excluded.expelled, detained=excluded.detained, fined_vessels=excluded.fined_vessels,
                     fines_ntd_m=excluded.fines_ntd_m, confiscated=excluded.confiscated, scraped_at=datetime('now')""",
                (period, gran, exp, det, fined, fines, conf, HUYONG_URL),
            )
        conn.commit()
        print(f"  manual 護永專案 rows: {len(HUYONG)}")

    with _client() as client:
        monthly, yearbooks = discover_reports(client)
        print(f"  discovered {len(monthly)} monthly reports, {len(yearbooks)} yearbooks")
        if not args.skip_yearbooks:
            for yb in sorted(yearbooks, key=lambda y: y["year"]):   # oldest first so the newest edition wins
                try:
                    n = ingest_report(conn, client, yb, "yearbook")
                    print(f"  yearbook {yb['roc_year']}年: {n} rows")
                except Exception as e:  # noqa: BLE001
                    print(f"  yearbook {yb['roc_year']}年 FAILED: {type(e).__name__}: {e}")
        if not args.skip_monthly:
            for rep in sorted(monthly, key=lambda m: (m["year"], m["month"])):
                try:
                    n = ingest_report(conn, client, rep, "monthly")
                    print(f"  monthly {rep['roc_year']}年{rep['month']:02d}月: {n} rows")
                except Exception as e:  # noqa: BLE001
                    print(f"  monthly {rep['roc_year']}年{rep['month']:02d}月 FAILED: {type(e).__name__}: {e}")
    tot = conn.execute("SELECT source, count(*) FROM cga_enforcement GROUP BY source").fetchall()
    print("  totals:", [tuple(t) for t in tot])


if __name__ == "__main__":
    main()
