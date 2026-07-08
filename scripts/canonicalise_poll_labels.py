"""
Canonicalise poll_results option labels.

Reads scraper/processors/poll_labels_canonical.json — a config of
(variant → canonical) mappings per question_key scope — and applies
them to poll_results. Idempotent: running on already-canonical data
is a no-op.

Why this exists: across waves, the AI sometimes translates the same
Chinese option ("未明確回答") differently ("No response", "No opinion",
"Unspecified", "No opinion/Other", etc.). Each variant becomes a
separate line on the cross-pollster trend chart. The fix is two-
layered: the AI extraction prompt instructs the model to emit
canonical labels (see _POLL_ONLY_PROMPT in ai_pipeline.py), and this
script catches any historical drift or future model regression.

Usage:
    python scripts/canonicalise_poll_labels.py             # dry-run (default)
    python scripts/canonicalise_poll_labels.py --apply     # write changes
    python scripts/canonicalise_poll_labels.py --config <path>

Run after a poll-review queue session if you suspect new variants
landed, or on a schedule (it's safe to run every pipeline tick).
"""
import sys
import os
import json
import argparse

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.utils.db import get_connection


DEFAULT_CONFIG = os.path.join(
    os.path.dirname(__file__), '..',
    'scraper', 'processors', 'poll_labels_canonical.json',
)


# Mirror of the family enum polls.py enforces on approve. Used only to warn
# on config typos — a misspelt family in a scope would otherwise silently
# widen (exclude_families) or empty (families) the rule's range.
_KNOWN_FAMILIES = {'identity', 'unification', 'approval', 'attitude',
                   'vote_intent', 'issue'}


def _resolve_scope(conn, scope):
    """Resolve a rule's scope to a set of question_ids.

    Include axes (intersected when both are present):
      `scope.question_keys` — only these keys.
      `scope.families`      — only questions whose poll_questions.family
                              is in this list. Family scoping is what lets
                              a rule cover FUTURE keys (e.g. every new
                              2026 race) without re-enumerating.
    Exclude axes (applied after):
      `scope.exclude_question_keys`, `scope.exclude_families`.
    Empty/missing scope => all question_keys are eligible.
    """
    scope = scope or {}
    include_keys = set(scope.get("question_keys") or [])
    include_fams = set(scope.get("families") or [])
    exclude_keys = set(scope.get("exclude_question_keys") or [])
    exclude_fams = set(scope.get("exclude_families") or [])

    unknown = (include_fams | exclude_fams) - _KNOWN_FAMILIES
    if unknown:
        print(f"    WARN: scope references unknown families {sorted(unknown)} "
              f"(known: {sorted(_KNOWN_FAMILIES)}) — typo in the config?")

    rows = conn.execute(
        "SELECT id, question_key, family FROM poll_questions").fetchall()
    qids = set()
    for r in rows:
        if include_keys and r['question_key'] not in include_keys:
            continue
        if include_fams and r['family'] not in include_fams:
            continue
        if r['question_key'] in exclude_keys or r['family'] in exclude_fams:
            continue
        qids.add(r['id'])
    return qids


def _apply_mapping(conn, mapping, qids, apply):
    """Return (matched_count, list of sample old → new pairs).

    The match condition AND-s `from_zh` and `from_en` when both are
    given. If only one is given, match on that field alone. A mapping
    with both `to_zh` and `to_en` always writes both columns; this is
    a deliberate choice — paired (zh, en) canonicalisation is what
    keeps the chart labels consistent in both languages.
    """
    if not qids:
        return 0, []

    qid_placeholders = ','.join('?' * len(qids))
    clauses = []
    params = list(qids)
    if "from_zh" in mapping:
        clauses.append("option_label_zh = ?")
        params.append(mapping["from_zh"])
    if "from_en" in mapping:
        clauses.append("option_label_en = ?")
        params.append(mapping["from_en"])
    if not clauses:
        raise ValueError(f"mapping has neither from_zh nor from_en: {mapping}")

    # Don't update rows that are already canonical. Saves write traffic
    # and makes the script trivially safe to re-run.
    clauses.append("(option_label_zh != ? OR option_label_en != ?)")
    params.extend([mapping["to_zh"], mapping["to_en"]])

    where = f"question_id IN ({qid_placeholders}) AND " + " AND ".join(clauses)
    matched = conn.execute(
        f"SELECT COUNT(*) FROM poll_results WHERE {where}", params,
    ).fetchone()[0]

    if not matched or not apply:
        return matched, []

    conn.execute(
        f"UPDATE poll_results SET option_label_zh = ?, option_label_en = ? WHERE {where}",
        [mapping["to_zh"], mapping["to_en"], *params],
    )
    return matched, []


def main():
    parser = argparse.ArgumentParser(description="Canonicalise poll_results option labels")
    parser.add_argument('--config', default=DEFAULT_CONFIG,
                        help=f"Path to canonicalisation rules JSON (default: {DEFAULT_CONFIG})")
    parser.add_argument('--apply', action='store_true',
                        help="Actually write changes. Without this flag, runs in dry-run mode (default).")
    args = parser.parse_args()

    with open(args.config, encoding='utf-8') as f:
        config = json.load(f)

    rules = config.get("rules") or []
    if not rules:
        print(f"No rules in {args.config}.")
        return

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Canonicalise poll labels [{mode}] ===")
    print(f"Config: {args.config}")
    print(f"Rules:  {len(rules)}\n")

    conn = get_connection()
    try:
        if args.apply:
            conn.execute("BEGIN")
        total_matched = 0
        try:
            for i, rule in enumerate(rules, 1):
                desc = rule.get("description") or f"(rule {i})"
                print(f"[{i}] {desc[:90]}")
                qids = _resolve_scope(conn, rule.get("scope") or {})
                print(f"    scope: {len(qids)} question_keys in range")
                rule_total = 0
                for mapping in rule.get("mappings", []):
                    n, _ = _apply_mapping(conn, mapping, qids, args.apply)
                    if n:
                        arrow = "→"
                        src = (mapping.get("from_zh") or "*") + " / " + (mapping.get("from_en") or "*")
                        dst = mapping["to_zh"] + " / " + mapping["to_en"]
                        action = "updated" if args.apply else "would update"
                        print(f"    {action} {n:>3}  {src}  {arrow}  {dst}")
                        rule_total += n
                if rule_total == 0:
                    print(f"    no rows {'updated' if args.apply else 'to update'} for this rule")
                print()
                total_matched += rule_total
            if args.apply:
                conn.commit()
        except Exception:
            if args.apply:
                conn.rollback()
                print("ROLLBACK — no changes written")
            raise
    finally:
        conn.close()

    verb = "Updated" if args.apply else "Would update"
    print(f"=== {verb} {total_matched} row(s) total ===")
    if not args.apply and total_matched:
        print("Re-run with --apply to write changes.")


if __name__ == '__main__':
    main()
