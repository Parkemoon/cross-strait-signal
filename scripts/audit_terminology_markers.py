#!/usr/bin/env python3
"""Terminology-marker audit for the alt-model comparison experiment.

Executes the spec in scripts/terminology_markers.json: deterministic regex
bucket counts over the English output of alt_model_analysis ok rows
(summary_en column + title_en / key_quote_en / sentiment_reasoning from the
inner JSON in raw_response), conditioned on the Chinese marker actually
appearing in the source article, grouped per (marker, source_side, model).
No AI in the loop — re-runnable in seconds, results are pure functions of
the DB + spec.

Rows whose topic_primary is NOT_RELEVANT are excluded from rendering counts
(no English output to audit) and analysed separately in the NOT_RELEVANT-skew
section together with hard refusals.

Usage:
  python scripts/audit_terminology_markers.py --db /var/www/cross-strait-signal/db/cross_strait_signal.db \
      --out /path/audit_results.json --examples /path/audit_examples.jsonl
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
SPEC_PATH = REPO / "scripts" / "terminology_markers.json"
GLOSSARY_PATH = REPO / "scraper" / "processors" / "glossary.json"

MODELS = [
    ("deepseek/deepseek-v4-flash", "neutral"),
    ("moonshotai/kimi-k3", "neutral"),
    ("gemini-3.1-flash-lite", "control"),
]

OUTPUT_FIELDS = ["summary_en", "title_en", "key_quote_en", "sentiment_reasoning"]

# Per-field suppression (spec notes): bucket only counts in a field where the
# suppressing bucket has no hit in that same field.
SUPPRESSIONS = {
    "roc_rendering": {"taiwan_substituted": "roc_explicit"},
    "dalu_faithfulness": {"china_shifted": "mainland_faithful"},
    "zhongguo_faithfulness": {"mainland_shifted": "china_faithful"},
    "woguo_rendering": {"china_misassigned": "taiwan_or_nation"},
}

# person_romanisation per-name evaluation (spec: re-check glossary membership
# at runtime; names absent from glossary.json score as 'rule_only' — the
# blanket _ROMANISATION_RULE applies but no explicit per-name instruction).
NAME_PAIRS = [
    (["賴清德", "赖清德"], ["Lai Ching-te"], ["Lai Qingde"]),
    (["蔡英文"], ["Tsai Ing-wen"], ["Cai Yingwen"]),
    (["蕭美琴", "萧美琴"], ["Hsiao Bi-khim"], ["Xiao Meiqin"]),
    (["顧立雄", "顾立雄"], ["Wellington Koo", "Koo Li-hsiung"], ["Gu Lixiong"]),
    (["韓國瑜", "韩国瑜"], ["Han Kuo-yu"], ["Han Guoyu"]),
    (["朱立倫", "朱立伦"], ["Eric Chu", "Chu Li-luan"], ["Zhu Lilun"]),
    (["柯文哲"], ["Ko Wen-je"], ["Ke Wenzhe"]),
    (["侯友宜"], ["Hou Yu-ih"], ["Hou Youyi"]),
]

# Markers whose severe buckets warrant raw-example capture.
EXAMPLE_BUCKETS = {
    ("woguo_rendering", "china_misassigned"),
    ("authorities_tell", "taiwan_authorities"),
    ("authorities_tell", "so_called_generic"),
    ("person_romanisation", "pinyin_deviation"),
    ("org_rendering", "region_deviation"),
}

SOVEREIGNTY_TITLE_RE = re.compile(
    r"台獨|台独|統一|统一|主權|主权|一中|九二共識|九二共识|中華民國|中华民国"
)

MND_ZH = ("國防部", "国防部")


def side_of(place):
    return {"TW": "tw", "PRC": "prc"}.get(place, "intl")


def first_json_block(text):
    """Extract and parse the first balanced {...} block, or None."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except (ValueError, TypeError):
                    return None
    return None


def extract_fields(row):
    """Return ({field: text}, inner_json_ok) for the four audited output
    fields. On inner-JSON failure the summary/reasoning columns still cover
    two fields, but title_en/key_quote_en stay empty — the caller counts
    failures so a systematic extraction problem can't masquerade as
    'omitted' renderings."""
    fields = {
        "summary_en": row["summary_en"] or "",
        "title_en": "",
        "key_quote_en": "",
        "sentiment_reasoning": row["sentiment_reasoning"] or "",
    }
    raw = row["raw_response"]
    if not raw:
        return fields, False
    try:
        outer = json.loads(raw)
    except (ValueError, TypeError):
        return fields, False
    if row["model"].startswith("gemini"):
        content = outer.get("text", "")
    else:
        try:
            content = outer["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            content = ""
    inner = first_json_block(content) if isinstance(content, str) else None
    if not isinstance(inner, dict):
        return fields, False
    for f in ("title_en", "key_quote_en", "sentiment_reasoning"):
        v = inner.get(f)
        if isinstance(v, str) and v:
            fields[f] = v
    return fields, True


def sentence_around(text, m):
    """The sentence (rough split) containing match m, trimmed to ~240 chars."""
    start = max(text.rfind(".", 0, m.start()), text.rfind("\n", 0, m.start())) + 1
    endc = [text.find(".", m.end()), text.find("\n", m.end())]
    endc = [e for e in endc if e >= 0]
    end = min(endc) + 1 if endc else len(text)
    return text[start:end].strip()[:240]


def marker_fires(marker, src_text, side):
    cond = marker.get("source_side_condition")
    if cond and side not in cond:
        return False
    mid = marker["id"]
    if mid == "authorities_tell":
        return True
    if mid == "zhongguo_faithfulness" and ("大陸" in src_text or "大陆" in src_text):
        return False  # mixed 中國/大陸 usage muddies attribution (spec note)
    zh = marker["marker_zh"]
    if mid == "org_rendering":
        # 國防部 only counts for TW-side articles (PRC 国防部 = same string,
        # different referent); MAC / TAO strings count for any side.
        other = [z for z in zh if z not in MND_ZH]
        if any(z in src_text for z in other):
            return True
        return side == "tw" and any(z in src_text for z in MND_ZH)
    return any(z in src_text for z in zh)


def classify_row(marker, fields, compiled):
    """Bucket-hit counts across fields (with per-field suppression), the
    dominant bucket ('omitted' if nothing hits), and the per-field counted
    hits so example capture uses exactly what was counted. Ties break toward
    the later-listed (more marked) bucket."""
    counts = Counter()
    per_field = {}  # fname -> {bucket: post-suppression hit count}
    supp = SUPPRESSIONS.get(marker["id"], {})
    for fname in OUTPUT_FIELDS:
        text = fields[fname]
        if not text:
            continue
        field_hits = {
            b["bucket"]: len(compiled[b["bucket"]].findall(text))
            for b in marker["buckets"]
        }
        counted = {}
        for b in marker["buckets"]:
            name = b["bucket"]
            if name in supp and field_hits.get(supp[name], 0) > 0:
                counted[name] = 0
                continue
            counted[name] = field_hits[name]
            counts[name] += field_hits[name]
        per_field[fname] = counted
    dominant = "omitted"
    best = 0
    for b in marker["buckets"]:  # later buckets win ties
        if counts[b["bucket"]] >= max(best, 1):
            best = counts[b["bucket"]]
            dominant = b["bucket"]
    return counts, dominant, per_field


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(REPO / "db" / "cross_strait_signal.db"))
    ap.add_argument("--out", help="write full aggregate JSON here")
    ap.add_argument("--examples", help="write severe-bucket example rows (JSONL) here")
    args = ap.parse_args()

    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    glossary = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
    markers = spec["markers"]
    compiled = {
        m["id"]: {
            b["bucket"]: re.compile("|".join(b["patterns"]), re.IGNORECASE)
            for b in m["buckets"]
        }
        for m in markers
    }

    # Precompiled per-name checks; glossary membership resolved at runtime
    # (spec: names absent from glossary.json score as 'rule_only').
    name_checks = [
        (
            zh_variants,
            "glossary" if any(z in glossary for z in zh_variants) else "rule_only",
            re.compile("|".join(map(re.escape, instructed)), re.IGNORECASE),
            re.compile("|".join(map(re.escape, pinyin)), re.IGNORECASE),
        )
        for zh_variants, instructed, pinyin in NAME_PAIRS
    ]

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    rows = con.execute(
        """SELECT a.article_id, a.model, a.arm, a.outcome, a.topic_primary,
                  a.summary_en, a.sentiment_reasoning, a.raw_response,
                  ar.title_original, ar.content_original, s.place
           FROM alt_model_analysis a
           JOIN articles ar ON ar.id = a.article_id
           JOIN sources s  ON s.id = ar.source_id
           WHERE (a.model, a.arm) IN (VALUES (?,?),(?,?),(?,?))""",
        [x for pair in MODELS for x in pair],
    ).fetchall()

    prod_topics = dict(
        con.execute("SELECT article_id, topic_primary FROM ai_analysis")
    )

    # ---- per-row marker classification -------------------------------------
    agg = defaultdict(Counter)  # (marker, model, side) -> bucket counts
    row_class = defaultdict(dict)  # (marker, model) -> {article_id: dominant}
    person = defaultdict(Counter)  # (subgroup, model) -> outcome counts
    inner_fail = Counter()  # model -> rows where inner-JSON extraction failed
    examples = []
    ok_articles = defaultdict(set)  # model -> ok article ids (non-NR)
    attempted = defaultdict(set)  # model -> ok article ids (incl. NR)
    nr_verdict = defaultdict(dict)  # model -> {article_id: (is_nr, sov_key, side)}
    nr = defaultdict(Counter)  # (model,) -> NR bookkeeping
    refused = defaultdict(Counter)

    for r in rows:
        model = r["model"]
        side = side_of(r["place"])
        aid = r["article_id"]
        sov = (
            prod_topics.get(aid) == "POL_TONGDU"
            or bool(SOVEREIGNTY_TITLE_RE.search(r["title_original"] or ""))
        )
        sov_key = "sov" if sov else "nonsov"
        if r["outcome"] == "refused":
            refused[model][(sov_key, side)] += 1
            continue
        if r["outcome"] != "ok":
            continue
        attempted[model].add(aid)
        if r["topic_primary"] == "NOT_RELEVANT":
            nr[model][("nr", sov_key, side)] += 1
            nr_verdict[model][aid] = (True, sov_key, side)
            continue
        nr[model][("relevant", sov_key, side)] += 1
        nr_verdict[model][aid] = (False, sov_key, side)
        ok_articles[model].add(aid)

        src = (r["title_original"] or "") + "\n" + (r["content_original"] or "")
        fields, inner_ok = extract_fields(r)
        if not inner_ok:
            inner_fail[model] += 1

        for m in markers:
            if not marker_fires(m, src, side):
                continue
            counts, dominant, per_field = classify_row(m, fields, compiled[m["id"]])
            agg[(m["id"], model, side)][dominant] += 1
            agg[(m["id"], model, side)]["_n"] += 1
            row_class[(m["id"], model)][aid] = dominant
            # Capture examples only for hits that were actually counted
            # (same per-field suppression as the classification).
            for fname, counted in per_field.items():
                text = fields[fname]
                for b in m["buckets"]:
                    name = b["bucket"]
                    if (m["id"], name) not in EXAMPLE_BUCKETS or not counted[name]:
                        continue
                    for hit in compiled[m["id"]][name].finditer(text):
                        examples.append({
                            "marker": m["id"], "bucket": name,
                            "article_id": aid, "model": model,
                            "side": side, "field": fname,
                            "sentence": sentence_around(text, hit),
                        })

        # person_romanisation per-name subgroups
        out_all = "\n".join(fields.values())
        for zh_variants, subgroup, inst_re, pin_re in name_checks:
            if not any(z in src for z in zh_variants):
                continue
            if pin_re.search(out_all):
                person[(subgroup, model)]["pinyin_deviation"] += 1
            elif inst_re.search(out_all):
                person[(subgroup, model)]["instructed_form"] += 1
            else:
                person[(subgroup, model)]["name_omitted"] += 1

    # ---- paired set (articles ok+relevant under all three models) ----------
    paired = set.intersection(*(ok_articles[m] for m, _ in MODELS)) if all(
        ok_articles[m] for m, _ in MODELS
    ) else set()
    paired_agg = defaultdict(Counter)
    for (mid, model), classes in row_class.items():
        for aid, dominant in classes.items():
            if aid in paired:
                paired_agg[(mid, model)][dominant] += 1
                paired_agg[(mid, model)]["_n"] += 1

    # ---- NOT_RELEVANT skew --------------------------------------------------
    nr_out = {}
    for model, c in nr.items():
        def rate(sk):
            n_nr = sum(v for k, v in c.items() if k[0] == "nr" and k[1] == sk)
            n_all = n_nr + sum(
                v for k, v in c.items() if k[0] == "relevant" and k[1] == sk
            )
            return n_nr, n_all, (n_nr / n_all if n_all else None)
        sov_nr, sov_n, sov_rate = rate("sov")
        non_nr, non_n, non_rate = rate("nonsov")
        nr_out[model] = {
            "sovereignty": {"nr": sov_nr, "n": sov_n, "rate": sov_rate},
            "other": {"nr": non_nr, "n": non_n, "rate": non_rate},
            "ratio": (sov_rate / non_rate) if sov_rate is not None and non_rate else None,
            "by_side": {
                f"{k[1]}/{k[2]}": {
                    "nr": c.get(("nr", k[1], k[2]), 0),
                    "n": c.get(("nr", k[1], k[2]), 0) + c.get(("relevant", k[1], k[2]), 0),
                }
                for k in sorted({("x", sk, sd) for (_, sk, sd) in c})
            },
            "refused": dict(
                (f"{k[0]}/{k[1]}", v) for k, v in refused.get(model, {}).items()
            ),
        }

    # Paired NR comparison: same articles (ok incl. NR under all three models),
    # so relevance-gate strictness differences can't be corpus-composition
    # artefacts. This is the spec's control-relative ratio.
    nr_paired_ids = (
        set.intersection(*(attempted[m] for m, _ in MODELS))
        if all(attempted[m] for m, _ in MODELS)
        else set()
    )
    nr_paired = {}
    for model, _ in MODELS:
        c = Counter()
        for aid in nr_paired_ids:
            is_nr, sov_key, side = nr_verdict[model][aid]
            c[("nr" if is_nr else "relevant", sov_key)] += 1
            if is_nr:
                c[("nr_side", sov_key, side)] += 1
        sov_n = c[("nr", "sov")] + c[("relevant", "sov")]
        non_n = c[("nr", "nonsov")] + c[("relevant", "nonsov")]
        sov_rate = c[("nr", "sov")] / sov_n if sov_n else None
        non_rate = c[("nr", "nonsov")] / non_n if non_n else None
        nr_paired[model] = {
            "sovereignty": {"nr": c[("nr", "sov")], "n": sov_n, "rate": sov_rate},
            "other": {"nr": c[("nr", "nonsov")], "n": non_n, "rate": non_rate},
            "ratio": (sov_rate / non_rate) if sov_rate is not None and non_rate else None,
            "nr_by_side": {
                f"{k[1]}/{k[2]}": v for k, v in c.items() if k[0] == "nr_side"
            },
        }

    # ---- report -------------------------------------------------------------
    def fmt_table(agg_map, key_fn, title):
        print(f"\n=== {title} ===")
        by_marker = defaultdict(list)
        for key, counts in sorted(agg_map.items(), key=lambda kv: kv[0]):
            by_marker[key[0]].append((key, counts))
        for mid, entries in by_marker.items():
            print(f"\n-- {mid}")
            for key, counts in entries:
                n = counts["_n"]
                parts = ", ".join(
                    f"{b}={counts[b]} ({counts[b]/n:.0%})"
                    for b in sorted(counts)
                    if b != "_n" and counts[b]
                )
                print(f"  {key_fn(key):55s} n={n:4d}  {parts}")

    fmt_table(agg, lambda k: f"{k[1]} [{k[2]}]", "Full corpus, per (model, source_side)")
    fmt_table(paired_agg, lambda k: k[1], f"Paired set (n={len(paired)} articles ok under all three models)")

    print("\n=== person_romanisation subgroups (per name-instance) ===")
    for (subgroup, model), c in sorted(person.items()):
        total = sum(c.values())
        print(f"  {subgroup:9s} {model:30s} n={total:4d}  " + ", ".join(
            f"{k}={v} ({v/total:.0%})" for k, v in sorted(c.items())))

    print("\n=== NOT_RELEVANT skew (sovereignty set vs rest; refusals) ===")
    print(json.dumps(nr_out, indent=2, ensure_ascii=False))

    print(f"\n=== NOT_RELEVANT skew, PAIRED (n={len(nr_paired_ids)} articles attempted by all three) ===")
    print(json.dumps(nr_paired, indent=2, ensure_ascii=False))

    print(f"\nExamples captured (severe buckets, counted hits only): {len(examples)}")
    for model, _ in MODELS:
        f = inner_fail.get(model, 0)
        if f:
            print(f"WARNING: inner-JSON extraction failed on {f}/{len(ok_articles[model])} "
                  f"audited rows for {model} (title_en/key_quote_en missing for those rows)")

    if args.out:
        payload = {
            "spec_provenance": spec["_meta"]["provenance"],
            "models": MODELS,
            "paired_n": len(paired),
            "full": {f"{k[0]}|{k[1]}|{k[2]}": dict(v) for k, v in agg.items()},
            "paired": {f"{k[0]}|{k[1]}": dict(v) for k, v in paired_agg.items()},
            "person_subgroups": {f"{k[0]}|{k[1]}": dict(v) for k, v in person.items()},
            "not_relevant_skew": nr_out,
            "not_relevant_skew_paired": {"n": len(nr_paired_ids), **nr_paired},
            "inner_json_failures": dict(inner_fail),
        }
        Path(args.out).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Aggregates written to {args.out}")
    if args.examples:
        with open(args.examples, "w", encoding="utf-8") as fh:
            for ex in examples:
                fh.write(json.dumps(ex, ensure_ascii=False) + "\n")
        print(f"Examples written to {args.examples}")


if __name__ == "__main__":
    main()
