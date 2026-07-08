"""
Off-axis audit for approved diplomacy_statements.

Promotes the 2026-07-01 scratchpad two-pass detector (offaxis_detector.py,
tag `offaxis-audit-20260701`, 98 rows dismissed on prod) to a repeatable
maintenance script. "Off-axis" = a statement whose subject has NO explicit
Taiwan / cross-strait / one-China nexus — Xinjiang/Tibet human-rights
critiques, WWII anti-militarism, generic freedom-of-navigation, or
semiconductor/AI supply-chain positions that flash-lite extracted anyway
(measured over-extraction rate ~11%, skewing the map pro-Taipei). The
Tier-1 prompt has carried a SCOPE GATE since 2026-07-01 (`_DIPLOMACY_RULES`),
so this audit mops up drift from before the gate and any future regression.

Two passes, both on --model (default gemini-3.5-flash — deliberately a
stronger model than the flash-lite extractor being audited):
  1. DETECT — statements batched ~20/call; the model returns the ids that
     look off-axis.
  2. CONFIRM — each flagged row re-checked individually with a
     conservative KEEP-biased prompt; only confirmed rows are dismissed.
Rows that are their country's ONLY approved statement are held back
regardless (a wrong dismissal there erases the country from the map).

Dry-run by default; --apply dismisses with tag `offaxis-audit-YYYYMMDD`
(reversible: flip approval_status back to 'approved' by tag). Cadence:
quarterly, or after approving a large historical backfill — NOT wired
into the 6-hourly pipeline (it re-reads the whole approved corpus).

Usage:
    python scripts/audit_diplomacy_offaxis.py                 # dry-run
    python scripts/audit_diplomacy_offaxis.py --db /var/www/cross-strait-signal/db/cross_strait_signal.db
    python scripts/audit_diplomacy_offaxis.py --apply
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import scraper.utils.db as dbmod
from scraper.utils.usage_log import log_usage

DETECT_BATCH = 20

_DETECT_PROMPT = """You are auditing a database of third-country diplomatic \
statements about TAIWAN / cross-strait relations / the one-China question.

A statement belongs in the database ONLY if its subject has an EXPLICIT \
Taiwan nexus. Statements about PRC domestic human-rights policy \
(Xinjiang/Uyghurs/Tibet), WWII history or anti-militarism, generic freedom \
of navigation, semiconductor/AI supply chains, or bilateral matters with no \
Taiwan reference are OFF-AXIS and must be flagged — a loose anti-PRC or \
pro-PRC sentiment with no Taiwan nexus is NOT a Taiwan stance.

Below are numbered statements. Return JSON: {"off_axis_ids": [<id>, ...]} \
listing ONLY the ids that are off-axis. If all are on-axis return \
{"off_axis_ids": []}.

STATEMENTS:
"""

_CONFIRM_PROMPT = """You are double-checking whether ONE diplomatic statement \
belongs in a database of third-country positions on TAIWAN / cross-strait \
relations / the one-China question.

Be CONSERVATIVE: when in doubt, KEEP. Only answer "remove" when the \
statement clearly has NO explicit Taiwan / Taiwan Strait / cross-strait / \
one-China nexus (e.g. it is about Xinjiang/Tibet human rights, WWII \
history, generic freedom of navigation, or chip supply chains). An indirect \
but explicit Taiwan reference — Taiwan Strait transit, Taiwan's \
international participation, arms for Taiwan — means KEEP.

Return JSON: {"verdict": "keep" | "remove", "reason": "<one sentence>"}

COUNTRY: {country}
SPEAKER: {speaker}
STATEMENT (EN): {en}
STATEMENT (ZH): {zh}
"""


def _client():
    from google import genai
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        sys.exit('GEMINI_API_KEY not set')
    return genai.Client(api_key=key)


def _gen_json(client, model, prompt, stage):
    resp = client.models.generate_content(
        model=model, contents=prompt,
        config={"response_mime_type": "application/json",
                "max_output_tokens": 2000, "temperature": 0.0})
    log_usage(stage, model, resp)
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


def main():
    ap = argparse.ArgumentParser(description="Off-axis audit for approved diplomacy statements")
    ap.add_argument('--db', help="Path to another worktree's DB (e.g. prod)")
    ap.add_argument('--apply', action='store_true', help="Dismiss confirmed rows (default: dry-run)")
    ap.add_argument('--model', default='gemini-3.5-flash')
    ap.add_argument('--limit', type=int, help="Cap statements audited (debugging)")
    ap.add_argument('--country', help="Restrict to one country_iso")
    args = ap.parse_args()

    if args.db:
        dbmod.DB_PATH = args.db
    conn = dbmod.get_connection()
    tag = f"offaxis-audit-{datetime.now(timezone.utc).strftime('%Y%m%d')}"

    where = "approval_status = 'approved'"
    params = []
    if args.country:
        where += " AND country_iso = ?"
        params.append(args.country.upper())
    rows = conn.execute(f"""
        SELECT id, country_iso, country_name, speaker, stance,
               statement_en, statement_zh
        FROM diplomacy_statements WHERE {where} ORDER BY id
    """, params).fetchall()
    rows = [dict(r) for r in rows
            if (r['statement_en'] or r['statement_zh'] or '').strip()]
    if args.limit:
        rows = rows[:args.limit]
    print(f"{len(rows)} approved statements in scope "
          f"({'dry-run' if not args.apply else 'APPLY'}, model {args.model})")
    if not rows:
        return

    # Countries with a single approved statement are held back entirely.
    counts = {}
    for r in conn.execute(
            "SELECT country_iso, COUNT(*) n FROM diplomacy_statements "
            "WHERE approval_status='approved' GROUP BY country_iso"):
        counts[r['country_iso']] = r['n']

    client = _client()

    # Pass 1 — detect in batches.
    flagged = []
    for i in range(0, len(rows), DETECT_BATCH):
        chunk = rows[i:i + DETECT_BATCH]
        lines = "\n".join(
            f"[{r['id']}] ({r['country_name'] or r['country_iso']}; "
            f"{(r['speaker'] or 'unknown')[:60]}) "
            f"{(r['statement_en'] or r['statement_zh'])[:400]}"
            for r in chunk)
        try:
            out = _gen_json(client, args.model, _DETECT_PROMPT + lines,
                            'offaxis_detect')
        except Exception as e:
            print(f"  detect batch at offset {i} failed — {e} (skipping)")
            continue
        ids = {int(x) for x in out.get('off_axis_ids', []) if str(x).isdigit()}
        chunk_ids = {r['id'] for r in chunk}
        flagged.extend(r for r in chunk if r['id'] in (ids & chunk_ids))
        print(f"  detect {min(i + DETECT_BATCH, len(rows))}/{len(rows)} "
              f"— flagged so far: {len(flagged)}")

    print(f"\nPass 1 flagged {len(flagged)} candidate(s). Confirming individually...")

    # Pass 2 — conservative confirm.
    confirmed, held_back = [], []
    for r in flagged:
        if counts.get(r['country_iso'], 0) <= 1:
            held_back.append(r)
            continue
        prompt = (_CONFIRM_PROMPT
                  .replace('{country}', r['country_name'] or r['country_iso'])
                  .replace('{speaker}', r['speaker'] or 'unknown')
                  .replace('{en}', (r['statement_en'] or '')[:1200])
                  .replace('{zh}', (r['statement_zh'] or '')[:1200]))
        try:
            out = _gen_json(client, args.model, prompt, 'offaxis_confirm')
        except Exception as e:
            print(f"  confirm id {r['id']} failed — {e} (keeping)")
            continue
        if out.get('verdict') == 'remove':
            confirmed.append((r, out.get('reason', '')))
            print(f"  CONFIRMED off-axis id {r['id']} [{r['country_iso']}]: "
                  f"{out.get('reason', '')[:100]}")

    if args.apply and confirmed:
        now = datetime.now(timezone.utc).isoformat()
        for r, _reason in confirmed:
            conn.execute("""
                UPDATE diplomacy_statements
                SET approval_status='dismissed', reviewed_at=?, reviewed_by=?
                WHERE id=?
            """, (now, tag, r['id']))
        conn.commit()
    conn.close()

    verb = 'Dismissed' if args.apply else 'Would dismiss'
    print(f"\n=== {verb} {len(confirmed)} of {len(flagged)} flagged; "
          f"{len(held_back)} held back (sole statement for their country) ===")
    if args.apply and confirmed:
        print(f"Revert: UPDATE diplomacy_statements SET approval_status='approved', "
              f"reviewed_at=NULL, reviewed_by=NULL WHERE reviewed_by='{tag}';")


if __name__ == '__main__':
    main()
