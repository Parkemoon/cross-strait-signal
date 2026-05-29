#!/usr/bin/env python3
"""Weekly editorial digest for the Cross-Strait Signal Substack.

Builds a Markdown + HTML brief of the week's signal from the dashboard DB and
emails it (Gmail SMTP). Deterministic SQL — it hands the writer vetted *raw
material* (headlines, quotes, sentiment, deltas), not finished prose.

Sections:
  1. Lead split-screen — the week's biggest cluster carried by BOTH sides of
     the strait, with each side's headlines / key quotes / sentiment / entity
     emphasis. This is the project's differentiator (the verification angle as
     narrative), so it leads.
  2. Sentiment divergence — per-side weekly tone toward the other side, this
     window vs the previous one, plus the topics that moved most.
  3. Social pulse — top Weibo (by heat) and PTT (by pushes) cross-strait items.
  4. By the numbers — top clusters and most-mentioned entities.
  5. Watch-list — new-formulation / escalation-flagged articles and any poll
     wave fielded in the window. Low-frequency signals worth a standing eye.

Every digest is also archived to a `weekly_digests` table so nothing is lost
and a future dashboard view is trivial to add.

Usage:
    python3 scripts/weekly_digest.py                 # build + email, last 7d
    python3 scripts/weekly_digest.py --no-email      # build + print only
    python3 scripts/weekly_digest.py --days 7 --to me@x.com
    python3 scripts/weekly_digest.py --env-file /path/.env --db /path/db.sqlite

The DB path defaults to this worktree's db/ (so a prod cron hits the prod DB);
override with --db for testing against another worktree's data.
"""
import argparse
import os
import smtplib
import sqlite3
import sys
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scraper.processors.keyword_filter import PRC_MUST_MENTION_TAIWAN  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.join(os.path.dirname(__file__), "..")
DEFAULT_DB = os.path.join(ROOT, "db", "cross_strait_signal.db")
DEFAULT_ENV = os.path.join(ROOT, ".env")

# place → which "side" of the strait a source sits on. PRC vs TW is the
# contrast that matters; everything else is context/international.
SIDE_LABEL = {"PRC": "Mainland (PRC)", "TW": "Taiwan", "HK": "Hong Kong"}
INTL_PLACES = {"SG", "UK", "US", "JP"}


def fmt_score(v):
    """Signed sentiment score with a hostile/cooperative gloss."""
    if v is None:
        return "—"
    tag = "hostile" if v <= -0.3 else "cooperative" if v >= 0.3 else "neutral"
    return f"{v:+.2f} ({tag})"


def side_of(place):
    if place in SIDE_LABEL:
        return SIDE_LABEL[place]
    return "International"


# ── data ───────────────────────────────────────────────────────────────────

def lead_splitscreen(conn, start, end):
    """Largest in-window cluster carrying both a PRC and a TW source."""
    row = conn.execute(
        """
        SELECT a.event_cluster_id,
               SUM(s.place='PRC') AS prc_n,
               SUM(s.place='TW')  AS tw_n,
               COUNT(*)           AS total
        FROM articles a JOIN sources s ON s.id = a.source_id
        WHERE a.published_at >= ? AND a.published_at < ?
          AND a.analyst_approved = 1 AND a.event_cluster_id IS NOT NULL
        GROUP BY a.event_cluster_id
        HAVING prc_n >= 1 AND tw_n >= 1
        ORDER BY total DESC LIMIT 1
        """,
        (start, end),
    ).fetchone()
    if not row:
        return None

    cluster_id, prc_n, tw_n, total = row
    arts = conn.execute(
        """
        SELECT s.place, s.name, a.title_en, an.key_quote_en, an.sentiment_score,
               an.topic_primary, a.url
        FROM articles a
        JOIN sources s ON s.id = a.source_id
        LEFT JOIN ai_analysis an ON an.article_id = a.id
        WHERE a.event_cluster_id = ? AND a.analyst_approved = 1
        ORDER BY s.place, a.published_at
        """,
        (cluster_id,),
    ).fetchall()

    sides = {}
    for place, sname, title, quote, score, _topic, url in arts:
        sd = side_of(place)
        b = sides.setdefault(sd, {"articles": [], "scores": []})
        b["articles"].append({"source": sname, "title": title, "quote": quote, "url": url})
        if score is not None:
            b["scores"].append(score)

    ents = conn.execute(
        """
        SELECT s.place, e.entity_name_en, COUNT(*) c
        FROM entities e
        JOIN articles a ON a.id = e.article_id
        JOIN sources s ON s.id = a.source_id
        WHERE a.event_cluster_id = ? AND a.analyst_approved = 1
          AND e.entity_name_en IS NOT NULL
        GROUP BY s.place, e.entity_name_en ORDER BY c DESC
        """,
        (cluster_id,),
    ).fetchall()
    side_ents = {}
    for place, name, c in ents:
        side_ents.setdefault(side_of(place), []).append((name, c))

    # arts rows are plain tuples (no Row factory); a[2] is title_en.
    title = next((a[2] for a in arts if a[2]), cluster_id)
    return {"cluster_id": cluster_id, "headline": title, "total": total,
            "sides": sides, "side_entities": side_ents}


def sentiment_divergence(conn, start, end, prior_start):
    """Per-side avg sentiment this window vs prior, plus biggest topic movers."""
    def by_side(s, e):
        out = {}
        for place, avg, n in conn.execute(
            """
            SELECT s.place, AVG(an.sentiment_score), COUNT(*)
            FROM articles a JOIN sources s ON s.id = a.source_id
            JOIN ai_analysis an ON an.article_id = a.id
            WHERE a.published_at >= ? AND a.published_at < ? AND a.analyst_approved = 1
              AND an.sentiment_score IS NOT NULL
            GROUP BY s.place
            """,
            (s, e),
        ):
            # PRC and TW are unique places → unique side labels (the only sides
            # side_delta reads). HK/intl can collide here but go unused.
            out[side_of(place)] = {"avg": avg, "n": n}
        return out

    cur, prev = by_side(start, end), by_side(prior_start, start)
    side_delta = []
    for label in ("Mainland (PRC)", "Taiwan"):
        if label in cur:
            c = cur[label]["avg"]
            p = prev.get(label, {}).get("avg")
            side_delta.append({"side": label, "cur": c, "n": cur[label]["n"],
                               "delta": (c - p) if p is not None else None})

    # topic movers (PRC+TW only), ranked by |delta|
    def topic_avgs(s, e):
        return {(t, side_of(pl)): a for t, pl, a, n in conn.execute(
            """
            SELECT an.topic_primary, s.place, AVG(an.sentiment_score), COUNT(*)
            FROM articles a JOIN sources s ON s.id = a.source_id
            JOIN ai_analysis an ON an.article_id = a.id
            WHERE a.published_at >= ? AND a.published_at < ? AND a.analyst_approved = 1
              AND an.sentiment_score IS NOT NULL AND s.place IN ('PRC','TW')
            GROUP BY an.topic_primary, s.place
            """,
            (s, e),
        )}

    tc, tp = topic_avgs(start, end), topic_avgs(prior_start, start)
    movers = []
    for key, cval in tc.items():
        pval = tp.get(key)
        if pval is not None:
            movers.append({"topic": key[0], "side": key[1],
                           "cur": cval, "delta": cval - pval})
    movers.sort(key=lambda m: abs(m["delta"]), reverse=True)
    return {"sides": side_delta, "movers": movers[:5]}


def social_pulse(conn, start):
    def top(platform, order_col, limit):
        return conn.execute(
            f"""
            SELECT title_en, title, MAX({order_col}) m, url
            FROM social_pulse
            WHERE platform = ? AND scraped_at >= ? AND {order_col} IS NOT NULL
              AND item_key != '__none__'
            GROUP BY item_key ORDER BY m DESC LIMIT ?
            """,
            (platform, start, limit),
        ).fetchall()

    # Weibo is a general hot-search; keep only cross-strait-relevant items by
    # matching the original (Chinese) title against the same keyword list the
    # /api/social route uses, then take the top 8 by heat. PTT is already
    # board-scoped to cross-strait content, so no keyword filter there.
    def is_cross_strait(title):
        return title and any(kw.lower() in title.lower() for kw in PRC_MUST_MENTION_TAIWAN)

    weibo_pool = top("weibo", "heat_index", 200)
    weibo = [r for r in weibo_pool if is_cross_strait(r[1])][:8]
    return {"weibo": weibo, "ptt": top("ptt", "push_count", 5)}


def by_numbers(conn, start, end):
    clusters = conn.execute(
        """
        SELECT MAX(cluster_size), MAX(title_en)
        FROM articles
        WHERE published_at >= ? AND published_at < ? AND analyst_approved = 1
          AND event_cluster_id IS NOT NULL
        GROUP BY event_cluster_id ORDER BY MAX(cluster_size) DESC LIMIT 6
        """,
        (start, end),
    ).fetchall()
    entities = conn.execute(
        """
        SELECT e.entity_name_en, e.entity_type, COUNT(*) c
        FROM entities e JOIN articles a ON a.id = e.article_id
        WHERE a.published_at >= ? AND a.published_at < ? AND a.analyst_approved = 1
          AND e.entity_name_en IS NOT NULL
        GROUP BY e.entity_name_en ORDER BY c DESC LIMIT 10
        """,
        (start, end),
    ).fetchall()
    return {"clusters": clusters, "entities": entities}


def watchlist(conn, start, end):
    flagged = conn.execute(
        """
        SELECT a.title_en, an.is_new_formulation, an.is_escalation_signal,
               an.escalation_note, a.url
        FROM articles a JOIN ai_analysis an ON an.article_id = a.id
        WHERE a.published_at >= ? AND a.published_at < ? AND a.analyst_approved = 1
          AND (an.is_new_formulation = 1 OR an.is_escalation_signal = 1)
        ORDER BY a.published_at DESC LIMIT 10
        """,
        (start, end),
    ).fetchall()
    polls = conn.execute(
        """
        SELECT pl.name_en, p.fielded_start, p.fielded_end, COUNT(DISTINCT pr.question_id)
        FROM polls p
        JOIN pollsters pl ON pl.id = p.pollster_id
        LEFT JOIN poll_results pr ON pr.poll_id = p.id
        WHERE p.approval_status = 'approved'
          AND COALESCE(p.fielded_end, p.fielded_start) >= ?
          AND COALESCE(p.fielded_end, p.fielded_start) < ?
        GROUP BY p.id ORDER BY p.fielded_start DESC
        """,
        (start[:10], end[:10]),
    ).fetchall()
    return {"flagged": flagged, "polls": polls}


# ── rendering ────────────────────────────────────────────────────────────────

def render(data, start, end):
    """Return (markdown, html). Built side by side from the same structures."""
    md, html = [], []

    def h(level, text):
        md.append(f"\n{'#' * level} {text}\n")
        html.append(f"<h{level}>{escape(text)}</h{level}>")

    def p(text):
        md.append(text + "\n")
        html.append(f"<p>{escape(text)}</p>")

    def ul(items):
        for it in items:
            md.append(f"- {it}")
        md.append("")
        html.append("<ul>" + "".join(f"<li>{escape(it)}</li>" for it in items) + "</ul>")

    span = f"{start[:10]} → {end[:10]}"
    h(1, "Cross-Strait Signal — Weekly Brief")
    p(f"Window: {span}")

    # 1. Lead split-screen
    lead = data["lead"]
    h(2, "1 · Lead: the split-screen")
    if not lead:
        p("No cluster this week carried both a PRC and a Taiwan source — no split-screen. "
          "See the by-the-numbers section for the dominant single-side stories.")
    else:
        p(f"“{lead['headline']}” — {lead['total']} articles clustered.")
        for label in ("Mainland (PRC)", "Taiwan", "Hong Kong", "International"):
            b = lead["sides"].get(label)
            if not b:
                continue
            avg = sum(b["scores"]) / len(b["scores"]) if b["scores"] else None
            h(3, f"{label} — {len(b['articles'])} article(s), tone {fmt_score(avg)}")
            lines = []
            for a in b["articles"][:4]:
                line = f"**{a['source']}:** {a['title']}"
                if a["quote"]:
                    line += f" — “{a['quote']}”"
                lines.append(line)
            ul(lines)
            ents = lead["side_entities"].get(label, [])
            if ents:
                p("Entity emphasis: " + ", ".join(f"{n} ({c})" for n, c in ents[:6]))

    # 2. Sentiment divergence
    sd = data["sentiment"]
    h(2, "2 · Sentiment divergence")
    sl = []
    for s in sd["sides"]:
        d = "" if s["delta"] is None else f", {s['delta']:+.2f} vs last week"
        sl.append(f"{s['side']}: {fmt_score(s['cur'])} over {s['n']} articles{d}")
    ul(sl or ["No sentiment data in window."])
    if sd["movers"]:
        p("Biggest topic moves (this week vs last):")
        ul([f"{m['topic']} · {m['side']}: {fmt_score(m['cur'])} ({m['delta']:+.2f})"
            for m in sd["movers"]])

    # 3. Social pulse
    sp = data["social"]
    h(2, "3 · Social pulse")
    if sp["weibo"]:
        h(3, "Weibo (by heat)")
        ul([f"{(t_en or t_zh)} — heat {int(m):,}" for t_en, t_zh, m, _ in sp["weibo"]])
    if sp["ptt"]:
        h(3, "PTT (by pushes)")
        ul([f"{(t_en or t_zh)} — {int(m)} pushes" for t_en, t_zh, m, _ in sp["ptt"]])
    if not sp["weibo"] and not sp["ptt"]:
        p("No social items in window.")

    # 4. By the numbers
    bn = data["numbers"]
    h(2, "4 · By the numbers")
    h(3, "Top clusters")
    ul([f"{size} articles — {title}" for size, title in bn["clusters"]] or ["—"])
    h(3, "Most-mentioned entities")
    ul([f"{name} ({etype}) — {c}" for name, etype, c in bn["entities"]] or ["—"])

    # 5. Watch-list
    wl = data["watch"]
    h(2, "5 · Watch-list")
    flags = []
    for title, newf, esc, note, _ in wl["flagged"]:
        tags = []
        if newf:
            tags.append("NEW FORMULATION")
        if esc:
            tags.append("ESCALATION")
        line = f"[{' / '.join(tags)}] {title}"
        if note:
            line += f" — {note}"
        flags.append(line)
    ul(flags or ["No new-formulation or escalation flags this week."])
    if wl["polls"]:
        p("Poll waves fielded this window:")
        ul([f"{name} — {fs}{(' → ' + fe) if fe and fe != fs else ''} ({q} questions)"
            for name, fs, fe, q in wl["polls"]])

    return "\n".join(md), "<body style='font-family:sans-serif;max-width:720px'>" + "".join(html) + "</body>"


# ── delivery ─────────────────────────────────────────────────────────────────

def archive(conn, generated_at, start, end, markdown, html, to):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS weekly_digests (
            id INTEGER PRIMARY KEY,
            generated_at TEXT NOT NULL,
            window_start TEXT NOT NULL,
            window_end   TEXT NOT NULL,
            markdown TEXT NOT NULL,
            html TEXT NOT NULL,
            emailed_to TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO weekly_digests (generated_at, window_start, window_end, markdown, html, emailed_to) "
        "VALUES (?,?,?,?,?,?)",
        (generated_at, start, end, markdown, html, to),
    )
    conn.commit()


def send_email(subject, markdown, html, to):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    pw = os.environ["SMTP_PASS"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText(markdown, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(user, pw)
        s.sendmail(user, [to], msg.as_string())


def main():
    ap = argparse.ArgumentParser(description="Weekly Substack digest from the dashboard DB.")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--env-file", default=DEFAULT_ENV)
    ap.add_argument("--to", default=None, help="override DIGEST_TO recipient")
    ap.add_argument("--no-email", action="store_true", help="build + print only, don't send")
    ap.add_argument("--no-archive", action="store_true", help="don't write weekly_digests row")
    args = ap.parse_args()

    load_dotenv(args.env_file)

    now = datetime.now()
    end = now.replace(microsecond=0).isoformat()
    start = (now - timedelta(days=args.days)).replace(microsecond=0).isoformat()
    prior_start = (now - timedelta(days=2 * args.days)).replace(microsecond=0).isoformat()

    conn = sqlite3.connect(args.db)
    data = {
        "lead": lead_splitscreen(conn, start, end),
        "sentiment": sentiment_divergence(conn, start, end, prior_start),
        "social": social_pulse(conn, start),
        "numbers": by_numbers(conn, start, end),
        "watch": watchlist(conn, start, end),
    }
    markdown, html = render(data, start, end)

    if not args.no_archive:
        archive(conn, end, start, end, markdown, html, args.to or os.environ.get("DIGEST_TO"))
    conn.close()

    subject = f"Cross-Strait Signal — Weekly Brief ({start[:10]} → {end[:10]})"
    if args.no_email:
        print(markdown)
        return

    to = args.to or os.environ.get("DIGEST_TO")
    if not to:
        sys.exit("No recipient: set DIGEST_TO in .env or pass --to")
    send_email(subject, markdown, html, to)
    print(f"Sent digest to {to} ({start[:10]} → {end[:10]}).")


if __name__ == "__main__":
    main()
