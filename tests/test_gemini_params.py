"""Guards on what the code sends to Gemini.

1. No sampling parameters, no thinking_budget. Google deprecated
   temperature / top_p / top_k on Gemini 3.x and stopped remapping
   thinking_budget to thinking_level; upcoming models answer either with 400
   INVALID_ARGUMENT (notice received 2026-10-08). The pipeline would then
   fail on the next model bump rather than here. Use thinking_level. The
   OpenRouter client is exempt: its arms are not Gemini, and they keep
   temperature 0.1 as the sweep invariant.

2. One setting per model. Every call takes its model from TIER1_MODEL /
   TIER2_MODEL in scraper/utils/llm.py, so a model change is one edit. A
   quoted model id anywhere else fails, except where the id is data: the
   price table and the read-only audits that match rows already stored
   under an id.
"""
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
SCAN_DIRS = ("scraper", "scripts", "shared", "api")

# A config key or keyword argument: "temperature": …, temperature=…,
# 'topP': …, thinking_budget=… (not TEMPERATURE constants or
# temperature_sent columns).
DEPRECATED = re.compile(
    r"""(?<![\w])["']?(temperature|top_p|top_k|topP|topK|thinking_budget|thinkingBudget)["']?\s*[:=](?!=)"""
)
DEPRECATED_EXEMPT = {os.path.join("scraper", "utils", "openrouter.py")}

# A quoted Gemini model id: "gemini-3.1-flash-lite", 'gemini-3.8-flash'
# (not 'gemini-control', the alt-model arm name).
MODEL_ID = re.compile(r"""["']gemini-\d[\w.-]*["']""")
MODEL_ID_EXEMPT = {
    os.path.join("scraper", "utils", "llm.py"),
    os.path.join("scripts", "usage_report.py"),
    os.path.join("scripts", "audit_summary_completeness.py"),
    os.path.join("scripts", "audit_terminology_markers.py"),
}


def _hits(pattern, exempt):
    hits = []
    for top in SCAN_DIRS:
        for dirpath, _, files in os.walk(os.path.join(ROOT, top)):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, ROOT)
                if rel in exempt:
                    continue
                with open(path, encoding="utf-8") as f:
                    for n, line in enumerate(f, 1):
                        if pattern.search(line):
                            hits.append(f"{rel}:{n}: {line.strip()}")
    return hits


def test_no_deprecated_gemini_params():
    hits = _hits(DEPRECATED, DEPRECATED_EXEMPT)
    assert not hits, "deprecated Gemini parameters:\n" + "\n".join(hits)


def test_model_ids_only_in_llm_settings():
    hits = _hits(MODEL_ID, MODEL_ID_EXEMPT)
    assert not hits, ("literal Gemini model id; use TIER1_MODEL / TIER2_MODEL "
                      "from scraper.utils.llm:\n" + "\n".join(hits))
