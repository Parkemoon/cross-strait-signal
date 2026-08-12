"""
Direct-question sweep — the prompt-shape arm of the alt-model experiment.

The article sweep (sweep_alt_models.py) found ZERO refusals in ~13k
structured analytical tasks on Chinese open-weight models; the published
literature reports substantial refusal on DIRECT interrogatives over the
same weights. This sweep sends the battery in data/direct_questions.json
(bands A literature-calibration / B cross-strait-direct / C same content
in the production Tier-1 scaffold / D neutral controls) to the same
provider-pinned arms, n runs per cell, and stores one direct_question_runs
row per call whatever the outcome.

Regime rules (the brief's "measuring default behaviour"):
  - fresh request per call, no conversation history
  - NO system prompt for bands A/B/D (bare interrogative, as the literature)
  - band C uses the byte-identical production _tier1_prompt over an article
    both models already analysed without refusing; prompt_sha256 recorded
  - no jailbreaks, no adversarial prefixes, no system-prompt manipulation
  - temperature 0.1 (matched to the article sweep); recorded per row

Classification is conservative (scraper/utils/direct_questions.py) and
NOTHING classified 'refused' is publishable unread — export the hand-review
JSONL with scripts/direct_question_aggregates.py --examples.

Arms (all Western-hosted; provider pinning as the article sweep):
  deepseek/deepseek-v4-flash  neutral   (the article sweep's headline model)
  moonshotai/kimi-k3          neutral
  deepseek/deepseek-r1-0528   neutral   (R1-generation: prompt-shape vs
                                         generation disambiguation; DeepInfra
                                         serves it at fp4 — see RUN_NOTES.md)
  gemini-control              control   (production model; floor/reference)

Usage:
    python scripts/sweep_direct_questions.py --print-battery --db <prod.db>
    python scripts/sweep_direct_questions.py --probe
    python scripts/sweep_direct_questions.py --db <prod.db> --dry-run
    python scripts/sweep_direct_questions.py --db <prod.db> --n 5

Long runs: launch detached (setsid nohup venv/bin/python -u ...).
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.utils.db import get_connection, DB_PATH
from scraper.utils.direct_questions import (classify_direct_response,
                                            classify_direct_text, load_battery)
from scraper.utils.openrouter import (ARMS, MAX_TOKENS, DEFAULT_MAX_TOKENS,
                                      build_request_body, chat_completion,
                                      classify_outcome, log_openrouter_usage)

BATTERY_PATH = os.path.join(os.path.dirname(__file__), '..', 'data',
                            'direct_questions.json')
RUN_NOTES_PATH = os.path.join(os.path.dirname(__file__), '..', 'RUN_NOTES.md')

GEMINI_CONTROL = 'gemini-control'
TEMPERATURE = 0.1  # matched to the article sweep / production Tier 1

# (model, arm) cells this experiment runs. Neutral/Western-hosted only —
# the originator arms stay dropped (account data-policy 404, see 07-2x log).
DIRECT_ARMS = [
    ("deepseek/deepseek-v4-flash", "neutral"),
    ("moonshotai/kimi-k3", "neutral"),
    ("deepseek/deepseek-r1-0528", "neutral"),
    (GEMINI_CONTROL, "control"),
]


def _connect(db_path):
    if not db_path:
        return get_connection()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 300000")
    return conn


def _require_table(conn):
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                       "AND name='direct_question_runs'").fetchone()
    if not row:
        sys.exit("direct_question_runs table missing — run scripts/migrate.py "
                 "(or apply db/migrations/0006_direct_question_runs.sql) on this DB first.")


def _band_c_prompt(conn, item):
    """The byte-identical production Tier-1 prompt over the item's article.
    Imported lazily (ai_pipeline needs GEMINI_API_KEY at import)."""
    from scraper.processors.ai_pipeline import _tier1_prompt
    r = conn.execute(
        """SELECT a.title_original, a.content_original, a.language,
                  a.published_at, s.name AS source_name
           FROM articles a JOIN sources s ON s.id = a.source_id
           WHERE a.id = ?""", (item['article_id'],)).fetchone()
    if not r:
        sys.exit(f"Band C article {item['article_id']} not in this DB "
                 f"({item['id']}) — point --db at the prod DB.")
    return _tier1_prompt(r['title_original'], r['content_original'],
                         r['language'], r['source_name'], r['published_at'])


def _classify_c_openrouter(raw):
    """Band C responses are Tier-1 JSON — classify with the ARTICLE sweep's
    classifier (post-9b108df) for comparability, then map onto the direct
    scheme. parse/api errors land in 'empty_or_error' (hand review sees them)."""
    outcome, parsed, refusal, err = classify_outcome(raw)
    mapping = {"ok": "answered", "refused": "refused",
               "parse_error": "empty_or_error", "api_error": "empty_or_error"}
    message = ((raw.get('choices') or [{}])[0].get('message') or {}) if isinstance(raw, dict) else {}
    content = (message.get('content') or '').strip() or None
    reasoning = (message.get('reasoning') or '').strip() or None
    return mapping[outcome], content, reasoning, refusal, err


def _gemini_generate(prompt, band):
    """One Gemini call. Bands A/B/D: bare content, minimal config (temp
    matched, no JSON MIME, no thinking override — default model behaviour,
    mirroring the bare-interrogative regime). Band C: the production Tier-1
    config, exactly as the article sweep's control arm."""
    from scraper.processors import ai_pipeline as ap
    from scraper.utils.usage_log import log_usage
    config = ap._TIER1_GEN_CONFIG if band == 'C' else {
        "temperature": TEMPERATURE, "max_output_tokens": 8000,
    }
    start = time.monotonic()
    try:
        resp = ap.client.models.generate_content(
            model=ap._TIER1_MODEL, contents=prompt, config=config)
        log_usage('direct_q_control', ap._TIER1_MODEL, resp)
        text = (resp.text or '').strip()
        raw = {"text": text}
    except Exception as e:
        return (ap._TIER1_MODEL, 'empty_or_error', None, None, None,
                f'{type(e).__name__}: {e}', {"error": str(e)},
                int((time.monotonic() - start) * 1000))
    latency = int((time.monotonic() - start) * 1000)

    if band == 'C':
        try:
            ap._parse_tier1_json(text)
            return ap._TIER1_MODEL, 'answered', text, None, None, None, raw, latency
        except Exception as e:
            outcome, refusal = classify_direct_text(text) if text else ('empty_or_error', None)
            if outcome == 'refused':
                return ap._TIER1_MODEL, 'refused', text, None, refusal, None, raw, latency
            return (ap._TIER1_MODEL, 'empty_or_error', text or None, None, None,
                    f'tier1 parse: {type(e).__name__}: {e}', raw, latency)

    if not text:
        return (ap._TIER1_MODEL, 'empty_or_error', None, None, None,
                'empty response text', raw, latency)
    outcome, refusal = classify_direct_text(text)
    return ap._TIER1_MODEL, outcome, text, None, refusal, None, raw, latency


def _fetch_endpoint_provenance(model):
    """Live provider metadata for RUN_NOTES (model revision, quantisation).
    Best-effort; the sweep proceeds without it."""
    import httpx
    try:
        r = httpx.get(f"https://openrouter.ai/api/v1/models/{model}/endpoints",
                      timeout=30)
        eps = (r.json().get('data') or {}).get('endpoints') or []
        wanted = set(sum((ARMS[model][a] for a in ARMS[model]), []))
        return [
            {"provider": e.get('provider_name'), "name": e.get('name'),
             "quantization": e.get('quantization'),
             "context_length": e.get('context_length')}
            for e in eps if e.get('provider_name') in wanted
        ]
    except Exception as e:
        return [{"error": f"{type(e).__name__}: {e}"}]


def _append_run_notes(args, plan_counts):
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    lines = [
        f"\n## Direct-question sweep — {stamp}\n",
        f"- DB: `{args.db or DB_PATH}` · battery `{args.battery}` (v"
        f"{json.load(open(args.battery, encoding='utf-8')).get('version')}) · "
        f"n={args.n} per cell · temperature {TEMPERATURE} (sent; endpoints may "
        f"ignore — see per-run variance in the aggregates) · endpoint "
        f"{('https://openrouter.ai/api/v1/chat/completions')} + Gemini API (control)\n",
        f"- Planned calls by arm: {plan_counts}\n",
        "- Provider endpoint metadata at run time (revision / quantisation):\n",
    ]
    for model, arm in DIRECT_ARMS:
        if model == GEMINI_CONTROL:
            from scraper.processors import ai_pipeline as ap
            lines.append(f"  - {GEMINI_CONTROL}: `{ap._TIER1_MODEL}` via Gemini API; "
                         f"bands A/B/D config `{{temperature: {TEMPERATURE}, "
                         f"max_output_tokens: 8000}}` (no JSON MIME, no thinking "
                         f"override); band C = production _TIER1_GEN_CONFIG\n")
        else:
            for ep in _fetch_endpoint_provenance(model):
                lines.append(f"  - {model} [{arm}]: {json.dumps(ep, ensure_ascii=False)}\n")
    with open(RUN_NOTES_PATH, 'a', encoding='utf-8') as f:
        f.writelines(lines)
    print(f"provenance appended to {RUN_NOTES_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Direct-question sweep (prompt-shape arm)")
    parser.add_argument('--db', type=str, default=None)
    parser.add_argument('--battery', type=str, default=BATTERY_PATH)
    parser.add_argument('--n', type=int, default=5, help="runs per cell (brief: 5)")
    parser.add_argument('--bands', type=str, default='ABCD',
                        help="subset of bands, e.g. AB")
    parser.add_argument('--arms', type=str, default=None,
                        help="comma-separated model slugs (default: all four)")
    parser.add_argument('--sleep', type=float, default=1.0)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--probe', action='store_true',
                        help="one ~4-token call per OpenRouter arm; no DB writes")
    parser.add_argument('--print-battery', action='store_true',
                        help="print the battery for approval (band C resolved "
                             "against --db); no calls, no writes")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

    items = load_battery(args.battery)
    items = [it for it in items if it['band'] in set(args.bands)]

    arms = DIRECT_ARMS
    if args.arms:
        chosen = set(args.arms.split(','))
        arms = [(m, a) for m, a in DIRECT_ARMS if m in chosen]

    if args.print_battery:
        conn = _connect(args.db) if any(i['band'] == 'C' for i in items) else None
        print(f"Battery: {args.battery}\n")
        for it in items:
            if it['band'] == 'C':
                prompt = _band_c_prompt(conn, it)
                sha = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
                print(f"  {it['id']} [{it['band']}/{it['lang']}] ← {it['maps_to']}  "
                      f"art {it['article_id']} · {it['passage_title']}\n"
                      f"        tier1 prompt {len(prompt)} chars · sha256 {sha[:16]}…")
            else:
                print(f"  {it['id']} [{it['band']}/{it['lang']}] {it['text']}")
        n_cells = len(items) * len(arms)
        print(f"\n{len(items)} item-variants × {len(arms)} arms × n={args.n} "
              f"= {n_cells * args.n} calls")
        print("Arms: " + ", ".join(f"{m} ({a})" for m, a in arms))
        return

    if args.probe:
        import httpx
        for model, arm in arms:
            if model == GEMINI_CONTROL:
                continue
            body = build_request_body(model, "Reply with the word OK and nothing else.", arm)
            # Reasoning models spend budget on thought even for 'OK' — give
            # them modest headroom; 4 would exhaust mid-thought and the probe
            # would falsely read as broken. Non-reasoning models stay at 4.
            body["max_tokens"] = 2000 if model in MAX_TOKENS else 4
            resp = httpx.post("https://openrouter.ai/api/v1/chat/completions",
                              headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
                              json=body, timeout=120)
            data = resp.json()
            if "error" in data:
                print(f"  {model:<28} [{arm}] BLOCKED  HTTP {resp.status_code}: "
                      f"{json.dumps(data['error'])[:140]}")
            else:
                print(f"  {model:<28} [{arm}] ok via {data.get('provider')}")
        return

    conn = _connect(args.db)
    _require_table(conn)
    print(f"DB: {args.db or DB_PATH}")

    # Build the run plan: (item, model, arm, run_idx) minus existing rows.
    plan = []
    for it in items:
        for model, arm in arms:
            row_model = model  # resolved below for gemini-control
            if model == GEMINI_CONTROL:
                from scraper.processors import ai_pipeline as ap
                row_model = ap._TIER1_MODEL
            done = {r['run_idx'] for r in conn.execute(
                """SELECT run_idx FROM direct_question_runs
                   WHERE question_id=? AND lang=? AND model=? AND arm=?""",
                (it['id'], it['lang'], row_model, arm))}
            for k in range(1, args.n + 1):
                if k not in done:
                    plan.append((it, model, arm, row_model, k))

    by_arm = {}
    for _, model, arm, _, _ in plan:
        by_arm[f"{model}[{arm}]"] = by_arm.get(f"{model}[{arm}]", 0) + 1
    print(f"Plan: {len(plan)} calls ({by_arm})")

    if args.dry_run:
        for it, model, arm, _, k in plan[:30]:
            print(f"  {it['id']}/{it['lang']} run{k} → {model} [{arm}]")
        if len(plan) > 30:
            print(f"  ... and {len(plan) - 30} more")
        print("\nDRY RUN — nothing called, nothing written.")
        return

    if plan:
        _append_run_notes(args, by_arm)

    c_prompts = {}  # article prompts generated once per item
    tallies = {}
    for i, (it, model, arm, row_model, k) in enumerate(plan, 1):
        if it['band'] == 'C':
            if it['id'] not in c_prompts:
                c_prompts[it['id']] = _band_c_prompt(conn, it)
            prompt = c_prompts[it['id']]
        else:
            prompt = it['text']
        sha = hashlib.sha256(prompt.encode('utf-8')).hexdigest()

        if model == GEMINI_CONTROL:
            (row_model, outcome, content, reasoning, refusal, err,
             raw, latency) = _gemini_generate(prompt, it['band'])
            finish = provider_used = providers_req = None
            usage = {}
        else:
            raw, latency = chat_completion(model, prompt, arm)
            if it['band'] == 'C':
                outcome, content, reasoning, refusal, err = _classify_c_openrouter(raw)
            else:
                outcome, content, reasoning, refusal, err = classify_direct_response(raw)
            log_openrouter_usage('direct_q', model, raw)
            choice = (raw.get('choices') or [{}])[0] if isinstance(raw, dict) else {}
            finish = choice.get('finish_reason')
            provider_used = raw.get('provider') if isinstance(raw, dict) else None
            usage = (raw.get('usage') or {}) if isinstance(raw, dict) else {}
            providers_req = json.dumps(ARMS[model][arm])

        conn.execute(
            """INSERT INTO direct_question_runs
               (question_id, band, lang, run_idx, model, arm, outcome,
                response_text, reasoning_content, finish_reason, refusal_text,
                error_text, provider_requested, provider_used, prompt_sha256,
                temperature_sent, raw_response, prompt_tokens,
                completion_tokens, total_tokens, latency_ms)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (it['id'], it['band'], it['lang'], k, row_model, arm, outcome,
             content, reasoning, finish, refusal, err,
             providers_req, provider_used, sha, TEMPERATURE,
             json.dumps(raw, ensure_ascii=False)[:200000],
             usage.get('prompt_tokens'), usage.get('completion_tokens'),
             usage.get('total_tokens'), latency))
        conn.commit()
        tallies[outcome] = tallies.get(outcome, 0) + 1
        print(f"[{i}/{len(plan)}] {it['id']}/{it['lang']} run{k} "
              f"{model.split('/')[-1]}[{arm}]: {outcome}"
              f" ({provider_used or 'gemini'}, {usage.get('total_tokens', '-')} tok)")
        time.sleep(args.sleep)

    print(f"\nDone. Outcomes: {tallies}")
    print("Next: scripts/direct_question_aggregates.py --db <same db> --examples "
          "<jsonl> — hand-review everything non-'answered' before any write-up.")


if __name__ == '__main__':
    main()
