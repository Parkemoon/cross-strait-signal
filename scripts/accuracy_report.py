"""
Editorial accuracy snapshot — analyst-AI agreement metrics.

Computes how often the analyst overrode the AI's classification, sentiment
label, or English translation, broken down by topic. Intended as the data
source for the Accuracy section of README.md — run with `--markdown` to
emit a paste-ready block.

Important caveat the script prints with every run: these are
analyst-AI *disagreement* rates, not analyst-truth agreement rates. The
analyst can be wrong too. Where the metric is meaningful: relative
weakness across topic categories (e.g. HK_MAC override rate vs
MIL_HARDWARE) tells you where the model is most uncertain.

Denominator: articles `analyst_approved=1 AND ai_processed=1` with
`published_at` inside the window. Dismissed articles (`is_hidden=1`)
are excluded — they were rejected outright, not corrected. Articles
still in the review queue (`needs_human_review=1 AND
review_resolved=0`) are excluded — not yet ground-truthed.

Usage:
    python scripts/accuracy_report.py
    python scripts/accuracy_report.py --days 90
    python scripts/accuracy_report.py --markdown   # README block
"""
import sys
import os
import argparse
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.utils.db import get_connection


def _fetch_metrics(conn, days):
    """Return a dict of metric values for the given window.

    Override counting note: stored topic_override / sentiment_override
    values are always equal to ai_analysis.<field> after the write,
    because `notes.py` and `review.py` propagate the override into
    ai_analysis at save time. So an inequality check (override !=
    ai.<field>) catches zero real overrides — only audit-trail
    anomalies where ai_analysis drifted post-write. The UI also only
    transmits override fields when the analyst explicitly chose
    "override" (ReviewQueue.js:51) or typed into the dropdown
    (ArticleCard.jsx:207-208 starts the state empty). So every stored
    non-empty override is a real reclassification by the analyst —
    count them directly.

    Translation overrides are also counted directly (they're free
    text, set only when the analyst typed something)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()

    # Approved-and-finalised denominator (analyst-touched, not in review queue).
    base = """
        FROM articles a
        JOIN ai_analysis ai ON ai.article_id = a.id
        LEFT JOIN analyst_notes n ON n.article_id = a.id
        WHERE a.analyst_approved = 1
          AND a.ai_processed = 1
          AND a.is_hidden = 0
          AND (ai.needs_human_review = 0 OR ai.review_resolved = 1)
          AND a.published_at >= ?
    """
    total = conn.execute(f"SELECT COUNT(*) {base}", (cutoff,)).fetchone()[0]

    if total == 0:
        return {"total": 0, "cutoff": cutoff}

    overrides = conn.execute(f"""
        SELECT
          SUM(CASE WHEN n.topic_override IS NOT NULL AND n.topic_override != '' THEN 1 ELSE 0 END) AS topic_n,
          SUM(CASE WHEN n.sentiment_override IS NOT NULL AND n.sentiment_override != '' THEN 1 ELSE 0 END) AS sentiment_n,
          SUM(CASE WHEN a.title_en_override IS NOT NULL AND a.title_en_override != '' THEN 1 ELSE 0 END) AS title_n,
          SUM(CASE WHEN a.summary_en_override IS NOT NULL AND a.summary_en_override != '' THEN 1 ELSE 0 END) AS summary_n,
          SUM(CASE WHEN a.key_quote_override IS NOT NULL AND a.key_quote_override != '' THEN 1 ELSE 0 END) AS quote_n,
          SUM(CASE WHEN ai.needs_human_review = 1 THEN 1 ELSE 0 END) AS flagged_n,
          SUM(CASE WHEN ai.needs_human_review = 1 AND ai.review_resolved = 1 THEN 1 ELSE 0 END) AS resolved_n
        {base}
    """, (cutoff,)).fetchone()

    # Override target distribution: what category does the analyst
    # reclassify articles INTO most often? Reveals where the AI misses
    # framings — clustering on US_PRC / US_TAIWAN / POL_TONGDU / HK_MAC
    # in practice. Only counts overrides within the window (joined via
    # the same base so the same approved/processed filters apply).
    override_targets = conn.execute(f"""
        SELECT n.topic_override AS target, COUNT(*) AS n
        {base}
          AND n.topic_override IS NOT NULL AND n.topic_override != ''
        GROUP BY n.topic_override
        ORDER BY n DESC
    """, (cutoff,)).fetchall()

    # Complementary signal: dismissal rate. is_hidden=1 means the analyst
    # rejected the article outright. This is the more common form of
    # disagreement in practice — analysts dismiss rather than relabel.
    # Denominator here is approved + dismissed (i.e., articles the analyst
    # engaged with), not the full processed set.
    dismissed_total = conn.execute("""
        SELECT COUNT(*) FROM articles a JOIN ai_analysis ai ON ai.article_id=a.id
        WHERE a.is_hidden = 1 AND a.ai_processed = 1
          AND a.published_at >= ?
    """, (cutoff,)).fetchone()[0]

    # Per-topic dismissal: of articles the analyst touched in a given
    # category, what fraction were dismissed? Surfaces categories where
    # the model is surfacing weakly-relevant articles.
    by_topic = conn.execute("""
        SELECT
          ai.topic_primary AS topic,
          SUM(CASE WHEN a.analyst_approved=1 THEN 1 ELSE 0 END) AS approved,
          SUM(CASE WHEN a.is_hidden=1 THEN 1 ELSE 0 END) AS dismissed
        FROM articles a
        JOIN ai_analysis ai ON ai.article_id = a.id
        WHERE (a.analyst_approved = 1 OR a.is_hidden = 1)
          AND a.published_at >= ?
          AND ai.topic_primary != 'NOT_RELEVANT'
        GROUP BY ai.topic_primary
        HAVING (approved + dismissed) >= 20
        ORDER BY (approved + dismissed) DESC
    """, (cutoff,)).fetchall()

    return {
        "total": total,
        "dismissed_total": dismissed_total,
        "cutoff": cutoff,
        "window_end": datetime.now(timezone.utc).date().isoformat(),
        "topic_n": overrides["topic_n"] or 0,
        "sentiment_n": overrides["sentiment_n"] or 0,
        "title_n": overrides["title_n"] or 0,
        "summary_n": overrides["summary_n"] or 0,
        "quote_n": overrides["quote_n"] or 0,
        "flagged_n": overrides["flagged_n"] or 0,
        "resolved_n": overrides["resolved_n"] or 0,
        "by_topic": [dict(r) for r in by_topic],
        "override_targets": [dict(r) for r in override_targets],
    }


def _pct(n, d):
    return 0.0 if not d else 100.0 * n / d


def _format_console(m, days):
    if m["total"] == 0:
        return f"No articles in scope for the last {days} days (cutoff {m['cutoff']})."

    touched = m["total"] + m["dismissed_total"]
    dismiss_pct = _pct(m["dismissed_total"], touched)
    lines = []
    lines.append(f"=== Cross-Strait Signal: Editorial Accuracy Snapshot ===")
    lines.append(f"Window:           last {days} days ({m['cutoff']} → {m['window_end']})")
    lines.append(f"Articles approved: {m['total']:,}")
    lines.append(f"Articles dismissed: {m['dismissed_total']:,} ({dismiss_pct:.1f}% of touched)")
    lines.append("")
    lines.append("OVERRIDE RATES (analyst changed the AI's call)")
    lines.append(f"  Topic relabel:          {m['topic_n']:>4} of {m['total']:,} approved "
                 f"({_pct(m['topic_n'], m['total']):.1f}%)")
    lines.append(f"  Sentiment relabel:      {m['sentiment_n']:>4} of {m['total']:,} "
                 f"({_pct(m['sentiment_n'], m['total']):.1f}%)")
    lines.append(f"  Title translation:      {m['title_n']:>4} of {m['total']:,} "
                 f"({_pct(m['title_n'], m['total']):.1f}%)")
    lines.append(f"  Summary translation:    {m['summary_n']:>4} of {m['total']:,} "
                 f"({_pct(m['summary_n'], m['total']):.1f}%)")
    lines.append(f"  Key-quote translation:  {m['quote_n']:>4} of {m['total']:,} "
                 f"({_pct(m['quote_n'], m['total']):.1f}%)")
    lines.append("")
    lines.append("HUMAN REVIEW QUEUE (Tier 1 vs Tier 2 disagreement)")
    open_n = m["flagged_n"] - m["resolved_n"]
    lines.append(f"  Flagged:                {m['flagged_n']} "
                 f"({_pct(m['flagged_n'], m['total']):.1f}% of approved)")
    lines.append(f"  Resolved:               {m['resolved_n']} "
                 f"({_pct(m['resolved_n'], m['flagged_n']):.0f}% of flagged)")
    lines.append(f"  Open:                   {open_n}")
    lines.append("")
    lines.append("WHERE THE ANALYST RECLASSIFIES TO (most common override targets)")
    lines.append("Reveals where the AI misses framings. Only categories with ≥3 overrides shown.")
    for row in m["override_targets"]:
        if row["n"] < 3:
            continue
        lines.append(f"  {row['target']:<22} {row['n']:>4}")
    lines.append("")
    lines.append("PER-TOPIC DISMISSAL RATE (categories with ≥20 analyst-touched articles)")
    lines.append(f"  {'topic':<22} {'approved':>9}  {'dismissed':>10}  {'dismiss %':>10}")
    for row in m["by_topic"]:
        ttot = row["approved"] + row["dismissed"]
        pct = _pct(row["dismissed"], ttot)
        lines.append(f"  {row['topic']:<22} {row['approved']:>9}  {row['dismissed']:>10}  {pct:>9.1f}%")
    return "\n".join(lines)


def _format_markdown(m, days):
    if m["total"] == 0:
        return f"_No articles in scope for the last {days} days._"

    touched = m["total"] + m["dismissed_total"]
    dismiss_pct = _pct(m["dismissed_total"], touched)
    lines = []
    lines.append(f"<!-- Generated by scripts/accuracy_report.py — last {days} days,")
    lines.append(f"     {m['cutoff']} → {m['window_end']}. Re-run to refresh. -->")
    lines.append("")
    lines.append(f"Snapshot over the last {days} days. The analyst engaged with "
                 f"{touched:,} articles, approving {m['total']:,} and dismissing "
                 f"{m['dismissed_total']:,} ({dismiss_pct:.1f}%). This is post-filter "
                 "volume — the directional keyword pre-filter rejects ~80% of raw "
                 "scraped articles upstream, before any API calls — so this figure "
                 "represents the cross-strait-relevant subset, not total scraping "
                 "throughput.")
    lines.append("")
    lines.append("### Override rates on approved articles")
    lines.append("")
    lines.append("Every stored override is a real analyst reclassification — the admin "
                 "UI only transmits override fields when the analyst explicitly chose "
                 "to override (review-queue path) or typed into the dropdown "
                 "(article-card path).")
    lines.append("")
    lines.append("| Field                 | Override rate | Count |")
    lines.append("|-----------------------|---------------|-------|")
    lines.append(f"| Topic relabel         | {_pct(m['topic_n'], m['total']):.1f}% | {m['topic_n']} |")
    lines.append(f"| Sentiment relabel     | {_pct(m['sentiment_n'], m['total']):.1f}% | {m['sentiment_n']} |")
    lines.append(f"| Title translation     | {_pct(m['title_n'], m['total']):.1f}% | {m['title_n']} |")
    lines.append(f"| Summary translation   | {_pct(m['summary_n'], m['total']):.1f}% | {m['summary_n']} |")
    lines.append(f"| Key-quote translation | {_pct(m['quote_n'], m['total']):.1f}% | {m['quote_n']} |")
    lines.append("")
    open_n = m["flagged_n"] - m["resolved_n"]
    state = "all currently resolved" if open_n == 0 else f"{open_n} still open"
    lines.append(f"Tier 1 and Tier 2 disagree on **{_pct(m['flagged_n'], m['total']):.1f}% "
                 f"of approved articles** ({m['flagged_n']} of {m['total']:,} in window); "
                 f"{state}.")
    lines.append("")
    lines.append("### Where the analyst reclassifies TO")
    lines.append("")
    lines.append("Categories the analyst most often promotes articles INTO. Reveals "
                 "where the AI misses the framing on first pass. Only targets with ≥3 "
                 "overrides shown.")
    lines.append("")
    lines.append("| Target topic | Count |")
    lines.append("|--------------|-------|")
    for row in m["override_targets"]:
        if row["n"] < 3:
            continue
        lines.append(f"| {row['target']} | {row['n']} |")
    lines.append("")
    lines.append("### Per-topic dismissal rate")
    lines.append("")
    lines.append("Of articles the analyst touched in each category, what fraction was "
                 "dismissed? High dismissal = model surfacing weakly-relevant articles. "
                 "Categories with <20 touched articles in window are omitted.")
    lines.append("")
    lines.append("| Topic | Approved | Dismissed | Dismiss % |")
    lines.append("|-------|----------|-----------|-----------|")
    for row in m["by_topic"]:
        ttot = row["approved"] + row["dismissed"]
        pct = _pct(row["dismissed"], ttot)
        lines.append(f"| {row['topic']} | {row['approved']} | {row['dismissed']} | {pct:.1f}% |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Editorial accuracy snapshot")
    parser.add_argument('--days', type=int, default=180,
                        help="Look-back window in days (default: 180, matches AI pipeline filter)")
    parser.add_argument('--markdown', action='store_true',
                        help="Emit a Markdown block suitable for README.md instead of console output")
    args = parser.parse_args()

    conn = get_connection()
    try:
        metrics = _fetch_metrics(conn, args.days)
    finally:
        conn.close()

    print(_format_markdown(metrics, args.days) if args.markdown
          else _format_console(metrics, args.days))


if __name__ == '__main__':
    main()
