"""Aggregate the Gemini usage JSONL (written by scraper/utils/usage_log.py)
into per-stage / per-model token totals, so the monthly bill can be
attributed and optimisation targeted.

Usage:
    python scripts/usage_report.py                 # all-time, by stage
    python scripts/usage_report.py --days 7        # last 7 days
    python scripts/usage_report.py --by model      # group by model
    python scripts/usage_report.py --by day        # daily totals
    python scripts/usage_report.py --log /path/to/gemini-usage.jsonl

Cost column is only shown for models whose price is filled into PRICES
below — VERIFY current Google Gemini pricing before trusting the figures.
Token totals are always exact. Thinking ("thoughts") tokens are billed at
the output rate; cached input tokens are a discounted subset of prompt
tokens (this report bills them at the full input rate, so the estimate is
a slight UPPER bound until you wire the cached discount in).
"""
import os
import sys
import json
import argparse
from collections import defaultdict
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DEFAULT_LOG = os.environ.get("GEMINI_USAGE_LOG", "/var/log/gemini-usage.jsonl")

# Fill in current per-1M-token prices (in your billing currency) to get a
# cost column. Leave as None to show tokens only. Verify against Google's
# current Gemini price sheet — these change.
PRICES = {
    "gemini-3.1-flash-lite": {"in_per_1m": None, "out_per_1m": None},
    "gemini-3.5-flash":      {"in_per_1m": None, "out_per_1m": None},
}


def _cost(model, prompt, output, thoughts):
    p = PRICES.get(model)
    if not p or p.get("in_per_1m") is None or p.get("out_per_1m") is None:
        return None
    return (prompt / 1e6) * p["in_per_1m"] + ((output + thoughts) / 1e6) * p["out_per_1m"]


def main():
    ap = argparse.ArgumentParser(description="Aggregate Gemini usage JSONL")
    ap.add_argument("--log", default=DEFAULT_LOG, help=f"JSONL path (default {DEFAULT_LOG})")
    ap.add_argument("--days", type=int, default=None, help="Only count the last N days")
    ap.add_argument("--by", choices=["stage", "model", "day"], default="stage")
    args = ap.parse_args()

    if not os.path.exists(args.log):
        print(f"No usage log at {args.log} yet — has the pipeline run since instrumentation landed?")
        return

    cutoff = None
    if args.days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    agg = defaultdict(lambda: {"calls": 0, "prompt": 0, "cached": 0,
                               "thoughts": 0, "output": 0, "total": 0})
    skipped = 0
    for line in open(args.log, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if cutoff:
            try:
                if datetime.fromisoformat(rec["ts"]) < cutoff:
                    continue
            except (KeyError, ValueError):
                pass
        if args.by == "day":
            key = (rec.get("ts") or "")[:10]
        else:
            key = rec.get(args.by) or "(unknown)"
        a = agg[key]
        a["calls"] += 1
        for f in ("prompt", "cached", "thoughts", "output", "total"):
            a[f] += rec.get(f) or 0

    if not agg:
        print("No records in window.")
        return

    window = f"last {args.days}d" if args.days else "all-time"
    print(f"Gemini usage by {args.by} ({window}) — {args.log}\n")
    hdr = f"{args.by:16} {'calls':>7} {'prompt':>12} {'thoughts':>10} {'output':>10} {'total':>12} {'est_cost':>10}"
    print(hdr)
    print("-" * len(hdr))

    grand = {"calls": 0, "prompt": 0, "thoughts": 0, "output": 0, "total": 0, "cost": 0.0}
    cost_known = False
    for key in sorted(agg, key=lambda k: agg[k]["total"], reverse=True):
        a = agg[key]
        # cost only computable per-model
        c = _cost(key, a["prompt"], a["output"], a["thoughts"]) if args.by == "model" else None
        cstr = f"{c:>10.2f}" if c is not None else f"{'—':>10}"
        if c is not None:
            cost_known = True
            grand["cost"] += c
        print(f"{key:16} {a['calls']:>7} {a['prompt']:>12,} {a['thoughts']:>10,} "
              f"{a['output']:>10,} {a['total']:>12,} {cstr}")
        for f in ("calls", "prompt", "thoughts", "output", "total"):
            grand[f] += a[f]

    print("-" * len(hdr))
    gcost = f"{grand['cost']:>10.2f}" if cost_known else f"{'—':>10}"
    print(f"{'TOTAL':16} {grand['calls']:>7} {grand['prompt']:>12,} {grand['thoughts']:>10,} "
          f"{grand['output']:>10,} {grand['total']:>12,} {gcost}")
    if skipped:
        print(f"\n({skipped} malformed line(s) skipped)")
    if not cost_known:
        print("\nTip: fill PRICES + run `--by model` for an estimated cost column.")


if __name__ == "__main__":
    main()
