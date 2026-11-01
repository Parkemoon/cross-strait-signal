"""Recalibrate ai_analysis sentiment scores and populate Source x Topic baselines.

De-heaps ai_analysis.sentiment_score within its editorial label band, preserves
the original LLM float in sentiment_score_raw, and populates sentiment_baseline
and sentiment_excess across all analysed articles.

Dry-run by default; pass --apply to write changes (and emit a JSONL revert
manifest to /root/db-backups/ when present). Idempotent: repeated runs always
read from sentiment_score_raw (or analyst score_override when set).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.sentiment_calibration import calibrate_sentiment_score  # noqa: E402

DEFAULT_DB = ROOT / "db" / "cross_strait_signal.db"
DEFAULT_PREDS = Path("/tmp/historical_continuous_preds.json")


def _revert_from_manifest(conn: sqlite3.Connection, manifest_path: Path) -> None:
    rows = []
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    with conn:
        conn.executemany(
            """
            UPDATE ai_analysis
            SET sentiment_score = ?,
                sentiment_score_raw = ?,
                sentiment_baseline = ?,
                sentiment_excess = ?
            WHERE id = ?
            """,
            [
                (
                    r["old_score"],
                    r["old_raw"],
                    r["old_baseline"],
                    r["old_excess"],
                    r["ai_id"],
                )
                for r in rows
            ],
        )
    print(f"Reverted {len(rows):,} ai_analysis rows from {manifest_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="Target SQLite DB path")
    ap.add_argument(
        "--preds-json",
        type=Path,
        default=DEFAULT_PREDS,
        help="Optional precomputed historical continuous predictions JSON",
    )
    ap.add_argument("--apply", action="store_true", help="Write updates to DB")
    ap.add_argument("--revert", type=Path, help="Revert from a JSONL manifest file")
    ap.add_argument("--show", type=int, default=10, help="Sample rows to print")
    args = ap.parse_args()

    conn = sqlite3.connect(str(args.db), timeout=60.0)
    conn.row_factory = sqlite3.Row

    if args.revert:
        _revert_from_manifest(conn, args.revert)
        conn.close()
        return

    hist_preds: dict[str, float] = {}
    if args.preds_json and args.preds_json.exists():
        with open(args.preds_json, encoding="utf-8") as f:
            hist_preds = json.load(f)
        print(f"Loaded {len(hist_preds):,} precomputed continuous scores from {args.preds_json}")

    has_notes = (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='analyst_notes'"
        ).fetchone()
        is not None
    )
    if has_notes:
        notes_join = """
        LEFT JOIN (
            SELECT article_id, topic_override, score_override
            FROM analyst_notes
            WHERE id IN (SELECT MAX(id) FROM analyst_notes GROUP BY article_id)
        ) an ON an.article_id = a.id
        """
        topic_expr = "COALESCE(an.topic_override, ai.topic_primary)"
        ovr_expr = "an.score_override"
    else:
        notes_join = ""
        topic_expr = "ai.topic_primary"
        ovr_expr = "NULL"

    rows = conn.execute(
        f"""
        SELECT
            ai.id AS ai_id,
            ai.article_id,
            a.url AS article_url,
            ai.sentiment,
            ai.sentiment_score,
            ai.sentiment_score_raw,
            ai.sentiment_baseline,
            ai.sentiment_excess,
            {topic_expr} AS eff_topic,
            {ovr_expr} AS score_override,
            s.name AS source_name,
            s.bias AS source_bias,
            COALESCE(a.title_en_override, a.title_en, '') AS title_en,
            COALESCE(a.summary_en_override, ai.summary_en, '') AS summary_en,
            COALESCE(a.key_quote_override, ai.key_quote_en, '') AS key_quote_en
        FROM ai_analysis ai
        JOIN articles a ON a.id = ai.article_id
        LEFT JOIN sources s ON s.id = a.source_id
        {notes_join}
        WHERE ai.sentiment_score IS NOT NULL
        ORDER BY ai.id
        """
    ).fetchall()

    print(f"Scanning {len(rows):,} ai_analysis rows in {args.db} ...")
    t0 = time.perf_counter()

    updates = []
    manifest_rows = []
    cal_vals = []
    base_vals = []
    exc_vals = []
    overridden_kept = 0

    for r in rows:
        raw_base = (
            r["sentiment_score_raw"]
            if r["sentiment_score_raw"] is not None
            else r["sentiment_score"]
        )
        has_ovr = r["score_override"] is not None
        if has_ovr:
            overridden_kept += 1

        cont_pred = hist_preds.get(r["article_url"] or "")
        res = calibrate_sentiment_score(
            raw_score=float(r["score_override"]) if has_ovr else float(raw_base),
            sentiment_label=r["sentiment"],
            source_name=r["source_name"],
            source_bias=r["source_bias"],
            topic_primary=r["eff_topic"],
            title_en=r["title_en"],
            summary_en=r["summary_en"],
            key_quote_en=r["key_quote_en"],
            continuous_pred=cont_pred,
            preserve_exact_score=has_ovr,
        )
        if res is None:
            continue

        # Always preserve the original pre-override/pre-calibration LLM score in sentiment_score_raw
        stored_raw = round(float(raw_base), 2)
        cal_vals.append(res.sentiment_score)
        base_vals.append(res.sentiment_baseline)
        exc_vals.append(res.sentiment_excess)

        if (
            r["sentiment_score"] != res.sentiment_score
            or r["sentiment_score_raw"] != stored_raw
            or r["sentiment_baseline"] != res.sentiment_baseline
            or r["sentiment_excess"] != res.sentiment_excess
        ):
            updates.append(
                (
                    res.sentiment_score,
                    stored_raw,
                    res.sentiment_baseline,
                    res.sentiment_excess,
                    r["ai_id"],
                )
            )
            manifest_rows.append(
                {
                    "ai_id": r["ai_id"],
                    "article_id": r["article_id"],
                    "old_score": r["sentiment_score"],
                    "old_raw": r["sentiment_score_raw"],
                    "old_baseline": r["sentiment_baseline"],
                    "old_excess": r["sentiment_excess"],
                    "new_score": res.sentiment_score,
                    "new_raw": stored_raw,
                    "new_baseline": res.sentiment_baseline,
                    "new_excess": res.sentiment_excess,
                }
            )

    dt = time.perf_counter() - t0
    n_tot = len(cal_vals)
    mean_cal = sum(cal_vals) / n_tot if n_tot else 0.0
    mean_base = sum(base_vals) / n_tot if n_tot else 0.0
    mean_exc = sum(exc_vals) / n_tot if n_tot else 0.0
    notable_20 = sum(1 for x in exc_vals if abs(x) >= 0.20)
    print(
        f"Computed {n_tot:,} rows in {dt:.2f}s | to update: {len(updates):,} | "
        f"analyst score_override preserved: {overridden_kept:,}"
    )
    print(
        f"Means: calibrated={mean_cal:+.4f}, baseline={mean_base:+.4f}, "
        f"excess={mean_exc:+.4f} | |excess|>=0.20: {notable_20:,} ({notable_20*100.0/max(1, n_tot):.1f}%)"
    )

    for sample in manifest_rows[: args.show]:
        print(
            f"  article {sample['article_id']:>6}: raw={sample['new_raw']:+.2f} -> "
            f"cal={sample['new_score']:+.2f} | base={sample['new_baseline']:+.3f} | "
            f"excess={sample['new_excess']:+.3f}"
        )

    if not args.apply:
        print("Dry-run complete. Re-run with --apply to write changes.")
        conn.close()
        return

    if not updates:
        print("All rows already up to date.")
        conn.close()
        return

    backup_dir = Path("/root/db-backups")
    if not backup_dir.exists():
        backup_dir = ROOT
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    db_tag = args.db.parent.parent.name or "db"
    manifest_path = backup_dir / f"sentiment-recalibrate-{db_tag}-{stamp}.manifest.jsonl"
    with open(manifest_path, "w", encoding="utf-8") as f:
        for item in manifest_rows:
            f.write(json.dumps(item) + "\n")
    print(f"Wrote revert manifest: {manifest_path}")

    with conn:
        conn.executemany(
            """
            UPDATE ai_analysis
            SET sentiment_score = ?,
                sentiment_score_raw = ?,
                sentiment_baseline = ?,
                sentiment_excess = ?
            WHERE id = ?
            """,
            updates,
        )
    conn.close()
    print(f"Applied updates to {len(updates):,} rows in {args.db}.")


if __name__ == "__main__":
    main()
