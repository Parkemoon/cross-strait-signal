"""
Direct-question arm aggregates — deterministic, read-only, re-runnable
(companion to alt_model_aggregates.py; same conventions).

Outputs, per the brief:
  - refusal + deflection rate by arm, by band, by language
  - Band A next to the published literature's reported rates (placeholders
    until transcribed from the papers — corpora and generations differ, the
    table says so explicitly)
  - Band A/B vs Band C within the same model (THE core comparison)
  - Chinese vs English divergence on identical items
  - per-cell outcome variance across the n runs (systematic vs sampling noise)
  - control-band (D) rates as the floor
  - content-label table over the hand-labelled answered sample (what the
    answers SAY, not just whether they came — state_line / state_framed /
    deflection / substantive; migration 0007)
  - plain-text tables suitable for pasting into a draft

Counts and proportions only. No significance tests — n is small.

--examples writes the hand-review JSONL: EVERY row classified as anything
other than 'answered', plus a seeded 10% sample of 'answered' rows as the
false-negative check. No refusal number goes into a write-up unread.

Usage:
    python scripts/direct_question_aggregates.py --db /path/to/prod.db
    python scripts/direct_question_aggregates.py --db ... --examples /path/review.jsonl
"""
import argparse
import json
import os
import random
import sqlite3
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Literature reference (Band A side-by-side). TRANSCRIBE FROM THE PAPERS
# before the write-up — do not guess. Left as explicit placeholders so a
# missing number reads as missing, never as zero.
LITERATURE = {
    "source_1": "arXiv 2505.12625 (R1dacted) — R1-generation, curated CCP-sensitive prompts",
    "source_1_rate": None,   # TODO transcribe
    "source_2": "Promptfoo CCP-sensitive dataset",
    "source_2_rate": None,   # TODO transcribe
    "note": ("Corpora, model generations and serving stacks differ from ours; "
             "this column calibrates DIRECTION, not magnitude."),
}

OUTCOMES = ("answered", "answered_with_caveat", "deflected", "refused", "empty_or_error")


def _outcome(row):
    """Hand-review verdict wins once folded back; auto-classification else."""
    return row["reviewed_outcome"] or row["outcome"]


def _rate_table(rows, key_fn, title):
    groups = defaultdict(lambda: defaultdict(int))
    for r in rows:
        groups[key_fn(r)][_outcome(r)] += 1
    print(f"\n== {title} ==")
    header = f"{'cell':<44}{'n':>5}" + "".join(f"{o[:9]:>11}" for o in OUTCOMES)
    print(header)
    for cell in sorted(groups):
        counts = groups[cell]
        n = sum(counts.values())
        line = f"{str(cell):<44}{n:>5}"
        for o in OUTCOMES:
            c = counts.get(o, 0)
            line += f"{c:>4} ({c / n:>4.0%})" if n else f"{'-':>11}"
        print(line)
    return groups


def main():
    parser = argparse.ArgumentParser(description="Direct-question aggregates (read-only)")
    parser.add_argument('--db', required=True)
    parser.add_argument('--examples', type=str, default=None,
                        help="write the hand-review JSONL here")
    parser.add_argument('--sample-seed', type=int, default=20260812,
                        help="seed for the 10%% answered sample (deterministic)")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM direct_question_runs").fetchall()
    if not rows:
        sys.exit("no direct_question_runs rows in this DB")

    n_reviewed = sum(1 for r in rows if r["reviewed_outcome"])
    print(f"direct_question_runs: {len(rows)} rows "
          f"({n_reviewed} carry a hand-review verdict; verdicts win)")

    models = sorted({r['model'] for r in rows})

    # --- by arm ---------------------------------------------------------
    _rate_table(rows, lambda r: f"{r['model']} [{r['arm']}]", "By arm (all bands)")

    # --- by arm × band --------------------------------------------------
    _rate_table(rows, lambda r: (r['model'].split('/')[-1], r['band']),
                "By arm × band")

    # --- by arm × band × language --------------------------------------
    _rate_table(rows, lambda r: (r['model'].split('/')[-1], r['band'], r['lang']),
                "By arm × band × language")

    # --- core comparison: A/B (direct) vs C (task-framed) per model ----
    print("\n== CORE: direct (A+B) vs task-framed (C), same model ==")
    print(f"{'model':<34}{'A+B n':>7}{'A+B refuse':>12}{'A+B non-ans':>12}"
          f"{'C n':>6}{'C refuse':>10}{'C non-ans':>11}")
    for m in models:
        ab = [r for r in rows if r['model'] == m and r['band'] in 'AB']
        c = [r for r in rows if r['model'] == m and r['band'] == 'C']

        def _stats(subset):
            n = len(subset)
            if not n:
                return n, "-", "-"
            refuse = sum(1 for r in subset if _outcome(r) == 'refused')
            nonans = sum(1 for r in subset if _outcome(r) != 'answered')
            return n, f"{refuse / n:.0%}", f"{nonans / n:.0%}"

        (abn, abr, abna), (cn, cr, cna) = _stats(ab), _stats(c)
        print(f"{m:<34}{abn:>7}{abr:>12}{abna:>12}{cn:>6}{cr:>10}{cna:>11}")
    print("(If A/B refuse and C doesn't: prompt shape is the trigger. If A/B "
          "also ~0: the divergence from the literature is generational, "
          "serving-related, or corpus-driven — equally publishable.)")

    # --- zh vs en on identical items (bands A/B/D) ---------------------
    print("\n== ZH vs EN divergence on identical items (A/B/D) ==")
    print(f"{'model':<34}{'item':>6}   en-outcomes → zh-outcomes   (differs?)")
    for m in models:
        per_item = defaultdict(lambda: defaultdict(list))
        for r in rows:
            if r['model'] == m and r['band'] in 'ABD':
                per_item[r['question_id']][r['lang']].append(_outcome(r))
        for qid in sorted(per_item):
            en = sorted(per_item[qid].get('en', []))
            zh = sorted(per_item[qid].get('zh', []))
            if en and zh and en != zh:
                print(f"{m:<34}{qid:>6}   {','.join(set(en))} → {','.join(set(zh))}   DIFFERS")
    print("(only items whose outcome sets differ are listed; silence = parity)")

    # --- per-cell variance across the n runs ---------------------------
    print("\n== Cells whose n runs DISAGREE (sampling noise vs systematic) ==")
    cells = defaultdict(list)
    for r in rows:
        cells[(r['model'], r['question_id'], r['lang'])].append(_outcome(r))
    unstable = 0
    for (m, qid, lang), outs in sorted(cells.items()):
        if len(set(outs)) > 1:
            unstable += 1
            print(f"  {m.split('/')[-1]:<26} {qid}/{lang}: {dict((o, outs.count(o)) for o in set(outs))}")
    print(f"{unstable} unstable cells of {len(cells)} "
          f"({unstable / len(cells):.0%}) — stable cells are systematic behaviour")

    # --- control floor --------------------------------------------------
    print("\n== Control floor (Band D) ==")
    for m in models:
        d = [r for r in rows if r['model'] == m and r['band'] == 'D']
        if d:
            nonans = sum(1 for r in d if _outcome(r) != 'answered')
            print(f"  {m:<34} n={len(d)}  non-answered {nonans / len(d):.0%}")

    # --- content labels (hand-reviewed answered sample, bands A/B) ------
    CONTENT_LABELS = ("state_line", "state_framed", "deflection", "substantive")
    labelled = [r for r in rows if r['content_label']]
    if labelled:
        print("\n== Content of ANSWERS (hand-labelled sample, bands A/B) ==")
        print(f"{'model':<34}{'n':>4}" + "".join(f"{l:>13}" for l in CONTENT_LABELS))
        for m in models:
            sub = [r for r in labelled if r['model'] == m]
            if not sub:
                continue
            line = f"{m:<34}{len(sub):>4}"
            for l in CONTENT_LABELS:
                c = sum(1 for r in sub if r['content_label'] == l)
                line += f"{c:>6} ({c / len(sub):>3.0%})"
            print(line)
        n_ab_answered = sum(1 for r in rows if r['band'] in 'AB'
                            and _outcome(r) == 'answered')
        print(f"(labels cover the reviewed sample only — {len(labelled)} of "
              f"{n_ab_answered} answered A/B rows; unlabelled rows are NOT "
              f"substantive-by-default. state_line/deflection show why refusal "
              f"counts alone mislead: 'answered' ≠ engaged.)")

    # --- literature side-by-side ---------------------------------------
    print("\n== Band A vs published literature ==")
    for m in models:
        a = [r for r in rows if r['model'] == m and r['band'] == 'A']
        if a:
            refuse = sum(1 for r in a if _outcome(r) == 'refused')
            print(f"  {m:<34} n={len(a)}  refusal {refuse / len(a):.0%}")
    for k in ("source_1", "source_2"):
        rate = LITERATURE[f"{k}_rate"]
        print(f"  {LITERATURE[k]:<60} {'NOT YET TRANSCRIBED' if rate is None else f'{rate:.0%}'}")
    print(f"  NOTE: {LITERATURE['note']}")

    # --- hand-review JSONL ----------------------------------------------
    if args.examples:
        non_answered = [r for r in rows if _outcome(r) != 'answered']
        answered = [r for r in rows if _outcome(r) == 'answered']
        rng = random.Random(args.sample_seed)
        sample = rng.sample(answered, max(1, len(answered) // 10)) if answered else []
        with open(args.examples, 'w', encoding='utf-8') as f:
            for tag, batch in (("review", non_answered), ("answered_sample", sample)):
                for r in batch:
                    f.write(json.dumps({
                        "why": tag, "id": r['id'], "question_id": r['question_id'],
                        "band": r['band'], "lang": r['lang'], "run_idx": r['run_idx'],
                        "model": r['model'], "arm": r['arm'],
                        "auto_outcome": r['outcome'],
                        "reviewed_outcome": r['reviewed_outcome'],
                        "content_label": r['content_label'],
                        "finish_reason": r['finish_reason'],
                        "provider_used": r['provider_used'],
                        "response_text": (r['response_text'] or '')[:4000],
                        "reasoning_content": (r['reasoning_content'] or '')[:4000],
                        "error_text": r['error_text'],
                    }, ensure_ascii=False) + "\n")
        print(f"\nHand-review JSONL: {args.examples} "
              f"({len(non_answered)} non-answered + {len(sample)} answered sample). "
              f"Fold verdicts back into direct_question_runs.reviewed_outcome; "
              f"this script prefers the verdict wherever set.")


if __name__ == '__main__':
    main()
