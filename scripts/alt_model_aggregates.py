"""Agreement aggregates for the alt-model comparison experiment.

Companion to audit_terminology_markers.py (which covers terminology/framing):
this script covers classification agreement between each alt_model_analysis
arm and the production ai_analysis row for the same article —

  - outcome counts per (model, arm)
  - topic agreement: overall, conditional on the model saying RELEVANT, and
    on the paired set (articles every model completed ok)
  - disagreement decomposition: NOT_RELEVANT-verdict share vs genuine topic
    confusion, with the top confusion pairs (prod -> alt)
  - sentiment deltas: mean |dScore| and mean signed bias (alt - prod), split
    by source side (tw / prc / intl via sources.place)
  - urgency match and escalation-flag behaviour

Articles with duplicate ai_analysis rows would double-count in the joins;
verified 2026-08-02 that none intersect the alt-model set (the script warns
if that changes).

Usage: python scripts/alt_model_aggregates.py [--db path]
(--db targets another worktree's DB, e.g. prod — same convention as the
other maintenance scripts. Read-only.)
"""

import argparse
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent.parent

NR = "NOT_RELEVANT"


def fetch(cur, model):
    cur.execute(
        """SELECT a.article_id, a.topic_primary AS alt_topic, a.sentiment_score AS alt_score,
                  a.urgency AS alt_urg, a.is_escalation_signal AS alt_esc,
                  p.topic_primary AS prod_topic, p.sentiment_score AS prod_score,
                  p.urgency AS prod_urg, p.is_escalation_signal AS prod_esc,
                  CASE s.place WHEN 'TW' THEN 'tw' WHEN 'PRC' THEN 'prc' ELSE 'intl' END AS side
           FROM alt_model_analysis a
           JOIN ai_analysis p ON p.article_id = a.article_id
           JOIN articles art ON art.id = a.article_id
           JOIN sources s ON s.id = art.source_id
           WHERE a.model = ? AND a.outcome = 'ok'""",
        (model,),
    )
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(REPO / "db" / "cross_strait_signal.db"))
    args = ap.parse_args()

    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    cur.execute(
        """SELECT COUNT(DISTINCT a.article_id) FROM alt_model_analysis a
           JOIN (SELECT article_id FROM ai_analysis GROUP BY article_id HAVING COUNT(*) > 1) d
             ON d.article_id = a.article_id"""
    )
    dupes = cur.fetchone()[0]
    if dupes:
        print(f"WARNING: {dupes} alt-model articles have duplicate ai_analysis rows — joins double-count them\n")

    print("=== Outcome counts by (model, arm) ===")
    cur.execute("SELECT model, arm, outcome, COUNT(*) c FROM alt_model_analysis GROUP BY 1,2,3 ORDER BY 1,2,3")
    for r in cur.fetchall():
        print(f"  {r['model']:30s} {r['arm']:10s} {r['outcome']:12s} {r['c']}")

    cur.execute("SELECT DISTINCT model FROM alt_model_analysis ORDER BY model")
    models = [r[0] for r in cur.fetchall()]

    cur.execute(
        """SELECT article_id FROM alt_model_analysis WHERE outcome='ok'
           GROUP BY article_id HAVING COUNT(DISTINCT model) = ?""",
        (len(models),),
    )
    paired_ids = {r[0] for r in cur.fetchall()}

    for m in models:
        rows = fetch(cur, m)
        n = len(rows)
        if not n:
            continue
        rel = [r for r in rows if r["alt_topic"] != NR]
        agree = sum(r["alt_topic"] == r["prod_topic"] for r in rows)
        agree_rel = sum(r["alt_topic"] == r["prod_topic"] for r in rel)
        pair = [r for r in rows if r["article_id"] in paired_ids]
        pair_agree = sum(r["alt_topic"] == r["prod_topic"] for r in pair)
        disagree = [r for r in rows if r["alt_topic"] != r["prod_topic"]]
        dis_nr = sum(r["alt_topic"] == NR for r in disagree)

        print(f"\n=== {m}  (n={n} ok rows joined to prod) ===")
        print(f"  NOT_RELEVANT verdicts: {n - len(rel)} ({(n - len(rel)) / n:.1%})")
        print(f"  topic agreement overall:              {agree / n:.1%}")
        if rel:
            print(f"  topic agreement | model says relevant: {agree_rel / len(rel):.1%}  (n={len(rel)})")
        if pair:
            print(f"  topic agreement, paired set:          {pair_agree / len(pair):.1%}  (n={len(pair)})")
        print(f"  disagreements: {len(disagree)}, of which NR verdicts: {dis_nr} ({dis_nr / max(len(disagree), 1):.0%})")
        conf = Counter((r["prod_topic"], r["alt_topic"]) for r in disagree if r["alt_topic"] != NR)
        print("  top genuine confusions (prod->alt): "
              + ", ".join(f"{p}->{a}:{c}" for (p, a), c in conf.most_common(6)))

        scored = [r for r in rel if r["alt_score"] is not None and r["prod_score"] is not None]
        if scored:
            deltas = [r["alt_score"] - r["prod_score"] for r in scored]
            by_side = defaultdict(list)
            for r in scored:
                by_side[r["side"]].append(r["alt_score"] - r["prod_score"])
            sides = "  ".join(f"{s}: {sum(d)/len(d):+.3f} (n={len(d)})" for s, d in sorted(by_side.items()))
            print(f"  sentiment: |dScore|={sum(abs(d) for d in deltas)/len(deltas):.3f}  "
                  f"signed={sum(deltas)/len(deltas):+.3f} (n={len(deltas)})   by side: {sides}")

        urg = [(r["alt_urg"], r["prod_urg"]) for r in rel if r["alt_urg"] and r["prod_urg"]]
        esc_match = sum((r["alt_esc"] or 0) == (r["prod_esc"] or 0) for r in rel)
        if urg:
            print(f"  urgency match={sum(a == p for a, p in urg)/len(urg):.1%} (n={len(urg)})  "
                  f"esc-flag match={esc_match/len(rel):.1%}  "
                  f"esc flags: alt={sum(1 for r in rel if r['alt_esc'])} prod={sum(1 for r in rel if r['prod_esc'])}")

    db.close()


if __name__ == "__main__":
    main()
