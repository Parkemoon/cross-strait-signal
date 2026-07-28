"""
Alt-model comparison sweep (Chinese LLMs via OpenRouter).

Re-runs already-APPROVED articles through an alternate model using the
byte-identical production Tier-1 prompt (_tier1_prompt — including
glossary/officials injection and content truncation) and records one
alt_model_analysis row per (article, model, arm) WHATEVER the outcome:
ok / refused / parse_error / api_error. Refusals are findings.

Arms (see scraper/utils/openrouter.py): 'neutral' pins OpenRouter to
Western hosts running the public weights (data never touches PRC);
'originator' pins to the model creator's own endpoint (censorship
isolation). --model gemini-control re-runs the CURRENT production Gemini
path on the same articles (arm 'control') so alt-vs-stored divergence
can be attributed to the model rather than prompt drift — stored
ai_analysis rows were produced by older prompt revisions.

The Tier-1 JSON also contains side-extract arrays (polls / exercises /
diplomacy / key-figure statements). They stay inside raw_response ONLY —
this script must never call the _insert_* helpers. Alt-model output
never touches the editorial queues.

Idempotent: skips (article, model, arm) rows that exist. Re-try failures
with --retry-errors (deletes api_error/parse_error rows for the
selection first; ok/refused rows are never clobbered).

Usage:
    python scripts/sweep_alt_models.py --model deepseek/deepseek-v4-flash --arm neutral --limit 10 --dry-run
    python scripts/sweep_alt_models.py --model deepseek/deepseek-v4-flash --arm neutral --days 365 --limit 2000
    python scripts/sweep_alt_models.py --model moonshotai/kimi-k3 --arm neutral --per-topic 9 --match-model deepseek/deepseek-v4-flash
    python scripts/sweep_alt_models.py --model gemini-control --match-model moonshotai/kimi-k3

Long runs: launch detached (setsid nohup venv/bin/python ...) — see the
session-log convention; hotel-wifi disconnects kill session-owned tasks.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.utils.db import get_connection, DB_PATH
from scraper.utils.openrouter import (ARMS, build_request_body, chat_completion,
                                      classify_outcome, log_openrouter_usage)

GEMINI_CONTROL = 'gemini-control'


def _connect(db_path):
    if not db_path:
        return get_connection()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _eligible(conn, args, model, arm):
    """Approved, visible, review-settled, relevant articles in the window
    without a row for this (model, arm). Stratified with --per-topic."""
    params = []
    where = """a.analyst_approved = 1 AND a.is_hidden = 0
        AND (ai.needs_human_review = 0 OR ai.review_resolved = 1)
        AND ai.topic_primary != 'NOT_RELEVANT'
        AND a.content_original IS NOT NULL AND length(a.content_original) > 200
        AND NOT EXISTS (SELECT 1 FROM alt_model_analysis x
                        WHERE x.article_id = a.id AND x.model = ? AND x.arm = ?)"""
    params += [model, arm]

    if args.article_ids:
        ids = [int(i) for i in args.article_ids.split(',')]
        where += f" AND a.id IN ({','.join('?' * len(ids))})"
        params += ids
    else:
        where += " AND a.published_at >= datetime('now', ?)"
        params.append(f'-{args.days} days')

    if args.match_model:
        where += """ AND EXISTS (SELECT 1 FROM alt_model_analysis m
                     WHERE m.article_id = a.id AND m.model = ?)"""
        params.append(args.match_model)

    base = f"""SELECT a.id, a.title_original, a.content_original, a.language,
        a.published_at, s.name AS source_name, ai.topic_primary
        FROM articles a
        JOIN ai_analysis ai ON ai.article_id = a.id
        JOIN sources s ON s.id = a.source_id
        WHERE {where}"""

    if args.per_topic:
        sql = f"""SELECT * FROM (
            SELECT b.*, ROW_NUMBER() OVER (
                PARTITION BY b.topic_primary ORDER BY b.published_at DESC) AS rn
            FROM ({base}) b) WHERE rn <= ? ORDER BY topic_primary, published_at DESC"""
        params.append(args.per_topic)
    else:
        sql = f"{base} ORDER BY a.published_at DESC LIMIT ?"
        params.append(args.limit)

    return conn.execute(sql, params).fetchall()


def _analyse_gemini_control(prompt):
    """Current production Gemini interactive path on the given prompt.
    Imported lazily — ai_pipeline builds a Gemini client at import."""
    from scraper.processors import ai_pipeline as ap
    from scraper.utils.usage_log import log_usage
    response = ap.client.models.generate_content(
        model=ap._TIER1_MODEL, contents=prompt, config=ap._TIER1_GEN_CONFIG)
    log_usage('alt_control', ap._TIER1_MODEL, response)
    raw = {"text": response.text}
    try:
        parsed = ap._parse_tier1_json(response.text)
        return ap._TIER1_MODEL, 'ok', parsed, None, None, raw
    except Exception as e:
        return ap._TIER1_MODEL, 'parse_error', None, None, f'{type(e).__name__}: {e}', raw


def main():
    parser = argparse.ArgumentParser(description="Alt-model comparison sweep")
    parser.add_argument('--model', required=True, choices=list(ARMS) + [GEMINI_CONTROL])
    parser.add_argument('--arm', choices=['neutral', 'originator'],
                        help="Hosting arm (required unless --model gemini-control)")
    parser.add_argument('--days', type=int, default=90)
    parser.add_argument('--limit', type=int, default=25,
                        help="Max articles this run (default 25 — cost-safe)")
    parser.add_argument('--per-topic', type=int, default=None,
                        help="Stratified: N most-recent eligible per topic_primary (overrides --limit)")
    parser.add_argument('--match-model', type=str, default=None,
                        help="Only articles already swept by this model (pairs subsets)")
    parser.add_argument('--article-ids', type=str, default=None,
                        help="Comma-separated explicit article ids (overrides --days)")
    parser.add_argument('--db', type=str, default=None)
    parser.add_argument('--dry-run', action='store_true',
                        help="List eligibles + print the first request body; no calls, no writes")
    parser.add_argument('--probe', action='store_true',
                        help="Send one ~4-token request per arm of --model to verify routing "
                             "(account data-policy settings can silently block an arm); no DB writes")
    parser.add_argument('--retry-errors', action='store_true',
                        help="Delete ALL api_error/parse_error rows for this (model, arm) first "
                             "(they then re-sweep when eligible; ok/refused rows never touched)")
    parser.add_argument('--sleep', type=float, default=1.0)
    args = parser.parse_args()

    if args.probe:
        if args.model == GEMINI_CONTROL:
            parser.error("--probe applies to OpenRouter models, not gemini-control")
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
        import httpx as _httpx
        for arm_name in ARMS[args.model]:
            body = build_request_body(
                args.model, "Reply with the word OK and nothing else.", arm_name)
            body["max_tokens"] = 4
            resp = _httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
                json=body, timeout=60)
            data = resp.json()
            if "error" in data:
                print(f"  {arm_name:<11} BLOCKED  HTTP {resp.status_code}: "
                      f"{json.dumps(data['error'])[:140]}")
            else:
                print(f"  {arm_name:<11} ok via {data.get('provider')}")
        return

    control = args.model == GEMINI_CONTROL
    if control:
        arm = 'control'
    elif not args.arm:
        parser.error("--arm is required unless --model gemini-control")
    else:
        arm = args.arm

    conn = _connect(args.db)
    print(f"DB: {args.db or DB_PATH}")
    # Row key uses the resolved model name so control rows record the real
    # Gemini model; eligibility must use the same key.
    if control:
        from scraper.processors import ai_pipeline as ap
        row_model = ap._TIER1_MODEL
    else:
        row_model = args.model
    print(f"Model: {row_model}  arm: {arm}"
          + ("" if control else f"  providers: {ARMS[args.model][arm]}"))

    if args.retry_errors and not args.dry_run:
        n = conn.execute(
            """DELETE FROM alt_model_analysis WHERE model = ? AND arm = ?
               AND outcome IN ('api_error','parse_error')""",
            (row_model, arm)).rowcount
        conn.commit()
        print(f"retry-errors: cleared {n} error rows")

    # Prompt builder imported after arg validation: pulls in ai_pipeline,
    # which needs GEMINI_API_KEY at import (fine on the worktrees).
    from scraper.processors.ai_pipeline import _tier1_prompt

    articles = _eligible(conn, args, row_model, arm)
    print(f"Eligible: {len(articles)} articles")

    if args.dry_run:
        for r in articles[:40]:
            print(f"  {r['id']}  [{r['topic_primary']}] {(r['title_original'] or '')[:60]}")
        if len(articles) > 40:
            print(f"  ... and {len(articles) - 40} more")
        if articles and not control:
            r = articles[0]
            prompt = _tier1_prompt(r['title_original'], r['content_original'],
                                   r['language'], r['source_name'], r['published_at'])
            body = build_request_body(args.model, prompt, arm)
            body['messages'][0]['content'] = (
                prompt[:400] + f"... [{len(prompt)} chars total]")
            print("\nFirst request body (prompt truncated for display):")
            print(json.dumps(body, indent=2, ensure_ascii=False))
        print("\nDRY RUN — nothing called, nothing written.")
        return

    tallies = {'ok': 0, 'refused': 0, 'parse_error': 0, 'api_error': 0}
    for i, r in enumerate(articles, 1):
        prompt = _tier1_prompt(r['title_original'], r['content_original'],
                               r['language'], r['source_name'], r['published_at'])
        sha = hashlib.sha256(prompt.encode('utf-8')).hexdigest()

        if control:
            model_used, outcome, parsed, refusal, err, raw = _analyse_gemini_control(prompt)
            finish = provider_used = None
            usage = {}
            latency = None
            providers_req = None
        else:
            raw, latency = chat_completion(args.model, prompt, arm)
            outcome, parsed, refusal, err = classify_outcome(raw)
            log_openrouter_usage('alt_tier1', args.model, raw, article_id=r['id'])
            choice = (raw.get('choices') or [{}])[0] if isinstance(raw, dict) else {}
            finish = choice.get('finish_reason')
            provider_used = raw.get('provider') if isinstance(raw, dict) else None
            usage = (raw.get('usage') or {}) if isinstance(raw, dict) else {}
            model_used = args.model
            providers_req = json.dumps(ARMS[args.model][arm])

        p = parsed or {}
        conn.execute(
            """INSERT INTO alt_model_analysis
               (article_id, model, arm, outcome, topic_primary, topic_secondary,
                sentiment, sentiment_score, sentiment_reasoning, urgency, summary_en,
                is_escalation_signal, finish_reason, refusal_text, error_text,
                provider_requested, provider_used, prompt_sha256, raw_response,
                prompt_tokens, completion_tokens, total_tokens, latency_ms)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r['id'], model_used, arm, outcome,
             p.get('topic_primary'), p.get('topic_secondary'),
             p.get('sentiment'), p.get('sentiment_score'), p.get('sentiment_reasoning'),
             p.get('urgency'), p.get('summary_en'),
             1 if p.get('is_escalation_signal') else (0 if parsed else None),
             finish, refusal, err,
             providers_req, provider_used, sha,
             json.dumps(raw, ensure_ascii=False)[:200000],
             usage.get('prompt_tokens'), usage.get('completion_tokens'),
             usage.get('total_tokens'), latency))
        conn.commit()
        tallies[outcome] += 1
        tok = usage.get('total_tokens', '-')
        print(f"[{i}/{len(articles)}] art {r['id']}: {outcome}"
              f" ({provider_used or 'gemini'}, {tok} tok)")
        time.sleep(args.sleep)

    print(f"\nDone. Outcomes: {tallies}")

    # Quick agreement read-out for the ok rows of this (model, arm)
    row = conn.execute(
        """SELECT COUNT(*) n,
                  AVG(x.topic_primary = ai.topic_primary) topic_agree,
                  AVG(ABS(COALESCE(x.sentiment_score,0) - COALESCE(ai.sentiment_score,0))) score_delta
           FROM alt_model_analysis x JOIN ai_analysis ai ON ai.article_id = x.article_id
           WHERE x.model = ? AND x.arm = ? AND x.outcome = 'ok'""",
        (row_model, arm)).fetchone()
    if row['n']:
        print(f"vs stored analysis (all {row['n']} ok rows this model/arm): "
              f"topic agreement {row['topic_agree']:.1%}, mean |Δscore| {row['score_delta']:.3f}")


if __name__ == '__main__':
    main()
