"""Editable site prose ("Tier 1 copy").

Tab intros, section descriptions, reading cards, caveats — the paragraphs an
editor may want to reword without a deploy. They live in data/site_copy.json
as a flat key -> string map, served whole (public) and rewritten one key at a
time by the admin UI (the same inline-editing flow as positions.json).
Labels, buttons and axis titles are NOT here — they stay in code.

Mirrors api/routes/positions.py: mtime-reload cache, atomic rewrite, strings
only, keys must already exist (adding a key is a code change so the frontend
and tests/test_site_copy.py stay in step).
"""
from __future__ import annotations

import json
import os
import threading

from fastapi import APIRouter, Body, Depends, HTTPException

from api.auth import require_admin

router = APIRouter(prefix="/api/copy", tags=["copy"])

COPY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "site_copy.json")

_lock = threading.Lock()
_cache: dict = {"mtime": None, "data": None}


def _load() -> dict:
    mtime = os.path.getmtime(COPY_PATH)
    with _lock:
        if _cache["mtime"] != mtime:
            with open(COPY_PATH, encoding="utf-8") as f:
                _cache["data"] = json.load(f)
            _cache["mtime"] = mtime
        return _cache["data"]


def get_copy() -> dict:
    """Key -> string, minus authoring comments. Importable by other routes."""
    return {k: v for k, v in _load().items() if not k.startswith("_comment")}


def copy_text(key: str, default: str = "") -> str:
    return get_copy().get(key, default)


def _write(data: dict) -> None:
    tmp = COPY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, COPY_PATH)


@router.get("/")
def read_copy():
    return {"copy": get_copy()}


@router.patch("/{key}")
def patch_copy(key: str, payload: dict = Body(...), _admin: None = Depends(require_admin)):
    """Replace one string. Body: {"value": "…"}. The key must already exist."""
    value = payload.get("value")
    if not isinstance(value, str):
        raise HTTPException(400, "value must be a string")
    if not value.strip():
        raise HTTPException(400, "value must not be empty")
    data = _load()
    with _lock:
        if key.startswith("_comment") or key not in data or not isinstance(data[key], str):
            raise HTTPException(404, f"unknown copy key {key!r} — add it to data/site_copy.json first")
        new_data = dict(data)
        new_data[key] = value
        _write(new_data)
        _cache["data"] = new_data
        _cache["mtime"] = os.path.getmtime(COPY_PATH)
    return {"key": key, "value": value}
