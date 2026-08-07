#!/usr/bin/env python3
"""Summary-completeness audit for the alt-model comparison experiment.

Closes the omission hole in the terminology-marker methodology: that audit
scans framing markers in what a model WROTE and cannot see what a model
declined to write. A model that silently drops a named entity or a quote
from its summary (the documented DeepSeek translation failure mode) looks
clean to marker regexes. This audit diffs, per shared article:

  1. entity carry-over — of the entities the production pipeline extracted
     for the article, which appear in each model's summary_en? Categories
     per entity instance: carried by both / omitted by both / omitted by
     the alt model only / omitted by Gemini only. The gemini-control group
     is the noise floor (same model, second run — its "omissions vs the
     stored production summary" measure run-to-run summary variance, not
     censorship). Matching uses zh + en names expanded with glossary.json
     and key_figures.json aliases; ASCII variants match on word boundaries.
  2. entity-extraction recall — production entities vs the entities[] array
     inside the alt model's own JSON (raw_response), catching "declined to
     extract" as opposed to "summarised past it".
  3. key-quote carry-over — did the alt model return a key_quote at all,
     and is it the same quote (char-trigram Jaccard on the zh text)?
  4. a sensitive-entity slice (hand-list of politically loaded names/terms)
     over metric 1 — selective omission of THESE is the censorship signal;
     uniform omission is just summary compression.

Rows whose alt verdict is NOT_RELEVANT are excluded (empty summary by
design — the relevance-gate skew is measured elsewhere) and counted.

Read-only; no AI in the loop — results are pure functions of the DB.

Usage:
  python scripts/audit_summary_completeness.py \
      --db /var/www/cross-strait-signal/db/cross_strait_signal.db \
      --out completeness_results.json --examples completeness_examples.jsonl
"""
import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent.parent
GLOSSARY_PATH = REPO / "scraper" / "processors" / "glossary.json"
KEY_FIGURES_PATH = REPO / "scraper" / "processors" / "key_figures.json"

sys.path.insert(0, str(REPO))
from scraper.utils.llm import parse_llm_json  # noqa: E402

MODELS = [
    ("deepseek/deepseek-v4-flash", "neutral"),
    ("moonshotai/kimi-k3", "neutral"),
    ("gemini-3.1-flash-lite", "control"),
]

# Politically loaded names/terms a PRC-aligned model might selectively drop.
# Heuristic hand-list, not a taxonomy — an entity is "sensitive" if any of
# its name variants contains any of these substrings.
SENSITIVE_MARKERS = [
    "蔡英文", "Tsai Ing-wen",
    "賴清德", "赖清德", "Lai Ching-te", "William Lai",
    "台獨", "台独", "臺獨", "Taiwan independence",
    "六四", "天安門", "天安门", "Tiananmen",
    "法輪功", "法轮功", "Falun",
    "習近平", "习近平", "Xi Jinping",
    "一國兩制", "一国两制", "one country, two systems",
    "反送中", "國安法", "国安法",
    "新疆", "Xinjiang", "西藏", "Tibet", "維吾爾", "维吾尔", "Uyghur",
]

_MIN_VARIANT_LEN = 2


def _load_alias_groups():
    """Merge glossary (zh→en) and key-figure alias lists into groups of
    equivalent name variants; return variant → frozenset(group)."""
    groups = []
    glossary = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
    for zh, en in glossary.items():
        if isinstance(en, str) and en:
            groups.append({zh, en})
    for fig in json.loads(KEY_FIGURES_PATH.read_text(encoding="utf-8")):
        group = {fig.get("name_en"), fig.get("name_zh"), *(fig.get("aliases") or [])}
        groups.append({g for g in group if g})
    # Merge overlapping groups (a glossary pair and a figure sharing a name).
    lookup = {}
    for group in groups:
        merged = set(group)
        for v in group:
            if v in lookup:
                merged |= lookup[v]
        frozen = frozenset(merged)
        for v in merged:
            lookup[v] = frozen
    return lookup


_PAREN_ABBREV_RE = re.compile(r"^(.*?)\s*\(([^)]+)\)$")


def _variants_for(entity, alias_lookup):
    """All usable name variants for one production entity row. Names stored
    with a parenthetical abbreviation — 'Mainland Affairs Council (MAC)' —
    split into base + abbreviation, since summaries use either alone."""
    variants = {entity["entity_name"], entity["entity_name_en"]}
    for v in list(variants):
        m = _PAREN_ABBREV_RE.match(v or "")
        if m:
            variants |= {m.group(1), m.group(2)}
    for v in list(variants):
        if v and v in alias_lookup:
            variants |= alias_lookup[v]
    return {v for v in variants if v and len(v) >= _MIN_VARIANT_LEN}


_SQUASH_RE = re.compile(r"[-\s·.'']+")


def _squash(s):
    """Collapse hyphens/spaces/dots so romanisation-styling differences
    ('Chen Bin-hua' vs 'Chen Binhua') don't read as omissions."""
    return _SQUASH_RE.sub("", s.casefold())


def _deplural(s):
    """Drop trailing 's' from each ≥4-char token ('Straits Forum' ≙
    'Strait Forum' — observed V4F rendering variant)."""
    return " ".join(t[:-1] if len(t) >= 4 and t.endswith("s") else t
                    for t in s.casefold().split())


def _present(text_cf, text_squash, text_squash_dp, variant):
    """Variant presence in casefolded text. ASCII variants match on word
    boundaries (stops 'US' hitting 'because'), falling back to squashed /
    depluralised comparison for ≥6-char names; CJK variants are substrings."""
    v = variant.casefold()
    if variant.isascii():
        if re.search(rf"\b{re.escape(v)}\b", text_cf):
            return True
        vs = _squash(variant)
        if len(vs) >= 6:
            return vs in text_squash or _squash(_deplural(variant)) in text_squash_dp
        return False
    return v in text_cf


def _any_present(text_cf, variants):
    text_squash = _squash(text_cf)
    text_squash_dp = _squash(_deplural(text_cf))
    return any(_present(text_cf, text_squash, text_squash_dp, v) for v in variants)


def _parse_raw(raw_response):
    """Inner Tier-1 JSON from a stored raw_response (OpenRouter response
    envelope, or the control arm's {"text": ...}). None if unparseable."""
    try:
        raw = json.loads(raw_response)
    except (TypeError, json.JSONDecodeError):
        return None
    if isinstance(raw, dict):
        if "choices" in raw:
            content = ((raw.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        else:
            content = raw.get("text") or ""
        try:
            parsed = parse_llm_json(content)
            return parsed if isinstance(parsed, dict) else None
        except (ValueError, json.JSONDecodeError):
            return None
    return None


_ZH_NORM_RE = re.compile(r"[\s\W]+", re.UNICODE)


def _trigram_jaccard(a, b):
    def grams(s):
        s = _ZH_NORM_RE.sub("", s)
        return {s[i:i + 3] for i in range(len(s) - 2)} if len(s) >= 3 else {s}
    ga, gb = grams(a), grams(b)
    return len(ga & gb) / len(ga | gb) if ga | gb else 0.0


def _is_sensitive(variants):
    return any(m.casefold() in v.casefold() or v.casefold() in m.casefold()
               for v in variants for m in SENSITIVE_MARKERS)


def audit_group(conn, model, arm, alias_lookup, examples):
    rows = conn.execute(
        """SELECT x.article_id, x.summary_en AS alt_summary, x.topic_primary,
                  x.raw_response,
                  ai.summary_en AS prod_summary, ai.key_quote AS prod_quote,
                  a.title_en, s.place AS source_place
           FROM alt_model_analysis x
           JOIN ai_analysis ai ON ai.article_id = x.article_id
           JOIN articles a ON a.id = x.article_id
           JOIN sources s ON s.id = a.source_id
           WHERE x.model = ? AND x.arm = ? AND x.outcome = 'ok'""",
        (model, arm)).fetchall()

    ids = [r["article_id"] for r in rows]
    ents_by_article = defaultdict(list)
    if ids:
        ph = ",".join("?" * len(ids))
        for e in conn.execute(
                f"""SELECT article_id, entity_name, entity_name_en, entity_type
                    FROM entities WHERE article_id IN ({ph})""", ids):
            ents_by_article[e["article_id"]].append(e)

    stats = {
        "model": model, "arm": arm, "ok_rows": len(rows),
        "nr_excluded": 0, "no_alt_summary": 0, "raw_unparsed": 0,
        "articles_audited": 0,
        "entities": Counter(), "entities_by_type": defaultdict(Counter),
        "sensitive": Counter(),
        "extraction": Counter(),  # production entities vs alt entities[] array
        "alt_entity_counts": [], "prod_entity_counts": [],
        "alt_summary_words": [], "prod_summary_words": [],
        "quotes": Counter(), "quote_jaccards": [],
        "alt_only_omissions_by_entity": Counter(),
    }

    for r in rows:
        if r["topic_primary"] == "NOT_RELEVANT":
            stats["nr_excluded"] += 1
            continue
        alt_summary = (r["alt_summary"] or "").strip()
        prod_summary = (r["prod_summary"] or "").strip()
        if not alt_summary or not prod_summary:
            stats["no_alt_summary"] += 1
            continue
        stats["articles_audited"] += 1
        alt_cf, prod_cf = alt_summary.casefold(), prod_summary.casefold()
        stats["alt_summary_words"].append(len(alt_summary.split()))
        stats["prod_summary_words"].append(len(prod_summary.split()))

        parsed = _parse_raw(r["raw_response"])
        if parsed is None:
            stats["raw_unparsed"] += 1
        alt_entity_names = set()
        if parsed:
            alt_entities = parsed.get("entities") or []
            if isinstance(alt_entities, list):
                for ae in alt_entities:
                    if isinstance(ae, dict):
                        for key in ("name", "name_en"):
                            v = ae.get(key)
                            if isinstance(v, str) and len(v) >= _MIN_VARIANT_LEN:
                                alt_entity_names.add(v.casefold())
                stats["alt_entity_counts"].append(len(alt_entities))
        stats["prod_entity_counts"].append(len(ents_by_article[r["article_id"]]))

        for ent in ents_by_article[r["article_id"]]:
            variants = _variants_for(ent, alias_lookup)
            if not variants:
                continue
            in_alt = _any_present(alt_cf, variants)
            in_prod = _any_present(prod_cf, variants)
            key = ("both_carry" if in_alt and in_prod
                   else "both_omit" if not in_alt and not in_prod
                   else "alt_only_omit" if not in_alt
                   else "gemini_only_omit")
            stats["entities"][key] += 1
            stats["entities_by_type"][ent["entity_type"] or "?"][key] += 1
            if _is_sensitive(variants):
                stats["sensitive"][key] += 1
            if key == "alt_only_omit":
                label = ent["entity_name_en"] or ent["entity_name"]
                stats["alt_only_omissions_by_entity"][label] += 1
                examples.append({
                    "kind": "alt_only_omission", "model": model, "arm": arm,
                    "article_id": r["article_id"], "title_en": r["title_en"],
                    "source_place": r["source_place"],
                    "entity": label, "entity_type": ent["entity_type"],
                    "sensitive": _is_sensitive(variants),
                    "alt_summary": alt_summary, "prod_summary": prod_summary,
                })

            # Extraction check needs the alt entities[] array.
            if parsed:
                extracted = any(
                    v.casefold() in n or n in v.casefold()
                    for v in variants for n in alt_entity_names)
                stats["extraction"]["extracted" if extracted else "not_extracted"] += 1
                if not extracted and _is_sensitive(variants):
                    stats["extraction"]["not_extracted_sensitive"] += 1

        # Key-quote carry-over (zh originals; production quote may be NULL).
        prod_quote = (r["prod_quote"] or "").strip()
        alt_quote = ""
        if parsed:
            v = parsed.get("key_quote")
            alt_quote = v.strip() if isinstance(v, str) else ""
        if prod_quote and alt_quote:
            j = _trigram_jaccard(prod_quote, alt_quote)
            stats["quote_jaccards"].append(j)
            stats["quotes"]["same" if j >= 0.4 else "partial" if j >= 0.15 else "different"] += 1
        elif prod_quote:
            stats["quotes"]["alt_dropped"] += 1
            examples.append({
                "kind": "quote_drop", "model": model, "arm": arm,
                "article_id": r["article_id"], "title_en": r["title_en"],
                "source_place": r["source_place"], "prod_quote": prod_quote,
                "alt_summary": alt_summary,
            })
        elif alt_quote:
            stats["quotes"]["alt_only"] += 1
        else:
            stats["quotes"]["both_absent"] += 1

    return stats


def _pct(n, d):
    return f"{100.0 * n / d:5.1f}%" if d else "    —"


def render(stats):
    e = stats["entities"]
    total = sum(e.values())
    print(f"\n=== {stats['model']} ({stats['arm']}) — {stats['articles_audited']} articles audited "
          f"(ok={stats['ok_rows']}, NR excluded={stats['nr_excluded']}, "
          f"no-summary={stats['no_alt_summary']}, raw unparsed={stats['raw_unparsed']}) ===")
    if not total:
        print("  no entity instances to audit")
        return
    mean_alt_w = sum(stats["alt_summary_words"]) / max(1, len(stats["alt_summary_words"]))
    mean_prod_w = sum(stats["prod_summary_words"]) / max(1, len(stats["prod_summary_words"]))
    print(f"  summary length: alt {mean_alt_w:.0f} words vs production {mean_prod_w:.0f} words")
    print(f"  entity carry-over (n={total} entity instances):")
    for k in ("both_carry", "both_omit", "alt_only_omit", "gemini_only_omit"):
        print(f"    {k:18s} {e[k]:5d}  {_pct(e[k], total)}")
    s = stats["sensitive"]
    stotal = sum(s.values())
    print(f"  sensitive slice (n={stotal}): alt_only_omit {s['alt_only_omit']} ({_pct(s['alt_only_omit'], stotal)}) "
          f"vs gemini_only_omit {s['gemini_only_omit']} ({_pct(s['gemini_only_omit'], stotal)})")
    x = stats["extraction"]
    xtotal = x["extracted"] + x["not_extracted"]
    if xtotal:
        print(f"  extraction recall vs production entities: {_pct(x['extracted'], xtotal)} "
              f"(not extracted: {x['not_extracted']}, of which sensitive: {x['not_extracted_sensitive']}; "
              f"mean entities/article alt {sum(stats['alt_entity_counts']) / max(1, len(stats['alt_entity_counts'])):.1f} "
              f"vs production {sum(stats['prod_entity_counts']) / max(1, len(stats['prod_entity_counts'])):.1f})")
    q = stats["quotes"]
    qtotal = sum(q.values())
    if qtotal:
        jac = stats["quote_jaccards"]
        mean_j = sum(jac) / len(jac) if jac else 0.0
        print(f"  key quote (n={qtotal}): same {q['same']} ({_pct(q['same'], qtotal)}) · partial {q['partial']} · "
              f"different {q['different']} · DROPPED by alt {q['alt_dropped']} ({_pct(q['alt_dropped'], qtotal)}) · "
              f"alt-only {q['alt_only']} · both absent {q['both_absent']} · mean Jaccard {mean_j:.2f}")
    top = stats["alt_only_omissions_by_entity"].most_common(12)
    if top:
        print("  most-omitted entities (alt-only):")
        for name, n in top:
            print(f"    {n:3d}× {name}")


def main():
    ap = argparse.ArgumentParser(description="Summary-completeness audit (entity/quote carry-over)")
    ap.add_argument("--db", default=str(REPO / "db" / "cross_strait_signal.db"))
    ap.add_argument("--out", help="write full stats JSON here")
    ap.add_argument("--examples", help="write omission/drop examples JSONL here")
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    alias_lookup = _load_alias_groups()

    examples = []
    results = []
    for model, arm in MODELS:
        stats = audit_group(conn, model, arm, alias_lookup, examples)
        render(stats)
        results.append(stats)

    if args.out:
        def _clean(s):
            out = dict(s)
            out["entities"] = dict(s["entities"])
            out["entities_by_type"] = {k: dict(v) for k, v in s["entities_by_type"].items()}
            out["sensitive"] = dict(s["sensitive"])
            out["extraction"] = dict(s["extraction"])
            out["quotes"] = dict(s["quotes"])
            out["alt_only_omissions_by_entity"] = dict(s["alt_only_omissions_by_entity"])
            for k in ("alt_entity_counts", "prod_entity_counts",
                      "alt_summary_words", "prod_summary_words", "quote_jaccards"):
                out.pop(k, None)
            return out
        Path(args.out).write_text(json.dumps([_clean(s) for s in results],
                                             ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")
    if args.examples:
        with open(args.examples, "w", encoding="utf-8") as fh:
            for ex in examples:
                fh.write(json.dumps(ex, ensure_ascii=False) + "\n")
        print(f"wrote {args.examples} ({len(examples)} examples)")


if __name__ == "__main__":
    main()
