"""Deterministic roster triage for the Coast Guard tracker.

The roster review only has ONE answerable question — "is this hull a
coast-guard vessel?" — and for almost every row the evidence settles it
without an analyst: an explicit "CHINA COAST GUARD" / "ZHONGGUO HAIJING"
name, or a Maritime Identification Digit prefix that matches the force
(412/413/414 China, 416 Taiwan, 431/432 Japan, 3xx US). Anomaly flags
(MID/flag mismatch, name change) are recorded facts about the AIS stream,
NOT something anyone can verify from a desk, so they are never a review
criterion here — a spoofed-MID hull with an explicit CCG name is confirmed
as coast guard, flag intact.

Rules (in order, first match wins):
  reject   — the current classifier no longer accepts (name, flag) as any
             force (e.g. a Taiwanese "HAI JING NO.7"); its presence rows are
             purged, since they were produced by the old classification.
  confirm  — explicit force name, or MID prefix matches the force.
  leave    — everything else stays 'auto' (weak name + foreign/junk MID);
             the residual is small and, as of 2026-08-26, has no presence.

Only rows with status='auto' are touched; analyst decisions are never
overwritten. Idempotent. Runs after every roster refresh
(refresh_coast_guard_roster.py) and after the nightly presence pull;
also safe by hand:  python scripts/triage_coast_guard_roster.py [--db …] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scraper.scrapers.gfw_coast_guard import triage_roster  # noqa: E402
from scraper.utils.db import get_connection  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    conn = get_connection(args.db)
    res = triage_roster(conn, dry_run=args.dry_run, verbose=True)
    print(f"{'dry-run: ' if args.dry_run else ''}confirmed {res['confirmed']}, rejected {res['rejected']} "
          f"(purged {res['purged_presence']} presence rows), left auto {res['left']}")


if __name__ == "__main__":
    main()
