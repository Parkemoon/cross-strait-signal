"""Guard against sampling parameters and thinking_budget in Gemini requests.

Google deprecated temperature / top_p / top_k on Gemini 3.x and stopped
remapping thinking_budget to thinking_level; upcoming models answer either
with 400 INVALID_ARGUMENT (notice received 2026-10-08). The pipeline would
then fail on the next model bump rather than here, so any of these keys in
a request config is caught at test time instead. Use thinking_level.

The OpenRouter client is exempt: its arms are not Gemini, and they keep
temperature 0.1 as the sweep invariant.
"""
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
SCAN_DIRS = ("scraper", "scripts", "shared", "api")
EXEMPT = {os.path.join("scraper", "utils", "openrouter.py")}

# A config key or keyword argument: "temperature": …, temperature=…,
# 'topP': …, thinking_budget=… (not TEMPERATURE constants or
# temperature_sent columns).
DEPRECATED = re.compile(
    r"""(?<![\w])["']?(temperature|top_p|top_k|topP|topK|thinking_budget|thinkingBudget)["']?\s*[:=](?!=)"""
)


def test_no_deprecated_gemini_params():
    hits = []
    for top in SCAN_DIRS:
        for dirpath, _, files in os.walk(os.path.join(ROOT, top)):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, ROOT)
                if rel in EXEMPT:
                    continue
                with open(path, encoding="utf-8") as f:
                    for n, line in enumerate(f, 1):
                        if DEPRECATED.search(line):
                            hits.append(f"{rel}:{n}: {line.strip()}")
    assert not hits, "deprecated Gemini parameters:\n" + "\n".join(hits)
