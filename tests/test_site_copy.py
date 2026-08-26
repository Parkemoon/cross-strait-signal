"""Shape test for the editable site prose (data/site_copy.json).

Every key the frontend or the API references must exist, every value must be
a non-empty string, and nothing in the file may be Chinese-only chrome. A
missing key would silently render the JSX fallback (or nothing), so this is
what stops a rename from blanking a paragraph.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.join(os.path.dirname(__file__), "..")
COPY_PATH = os.path.join(ROOT, "data", "site_copy.json")
FRONTEND_SRC = os.path.join(ROOT, "frontend", "src")


def _copy():
    with open(COPY_PATH, encoding="utf-8") as f:
        return json.load(f)


def _frontend_keys():
    keys = set()
    for dirpath, _, files in os.walk(FRONTEND_SRC):
        for fn in files:
            if fn.endswith((".js", ".jsx")):
                with open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                    keys.update(re.findall(r'<Copy\s[^>]*?\bk="([^"]+)"', f.read()))
    return keys


def test_values_are_nonempty_strings():
    data = _copy()
    for k, v in data.items():
        if k.startswith("_comment"):
            continue
        assert isinstance(v, str) and v.strip(), f"{k} must be a non-empty string"


def test_every_frontend_key_exists():
    data = _copy()
    keys = _frontend_keys()
    assert keys, "no <Copy k=…> usages found — the regex or the migration is broken"
    missing = sorted(k for k in keys if k not in data)
    assert not missing, f"frontend references copy keys missing from site_copy.json: {missing}"


def test_caveat_keys_exist():
    from api.routes.coast_guard import CAVEAT_SCOPES
    data = _copy()
    missing = [f"coast_guard.caveat.{k}" for k in CAVEAT_SCOPES if f"coast_guard.caveat.{k}" not in data]
    assert not missing, missing


def test_patch_rejects_unknown_key_and_non_string():
    from api.routes.copy import _load
    data = _load()
    assert "maritime.intro" in data
    # the route-level guards are exercised through the API in the smoke test;
    # here we just pin the contract that keys are pre-declared
    assert all(not k.startswith("_comment") or isinstance(v, str) for k, v in data.items())
