"""Editable site prose ("Tier 1 copy").

Tab intros, section descriptions, reading cards, caveats — the paragraphs an
editor may want to reword without a deploy. They live in data/site_copy.json
as a flat key -> string map, served whole (public) and rewritten one key at a
time by the admin UI (the same inline-editing flow as positions.json).
Labels, buttons and axis titles are NOT here — they stay in code.

Same JsonFileStore as api/routes/positions.py (mtime-reload cache, atomic
rewrite); strings only, keys must already exist (adding a key is a code change so the frontend
and tests/test_site_copy.py stay in step).
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Body, Depends, HTTPException

from api.auth import require_admin
from api.json_store import JsonFileStore

router = APIRouter(prefix="/api/copy", tags=["copy"])

COPY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "site_copy.json")

_store = JsonFileStore(COPY_PATH)


def _load() -> dict:
    return _store.load()


def get_copy() -> dict:
    """Key -> string, minus authoring comments. Importable by other routes."""
    return {k: v for k, v in _load().items() if not k.startswith("_comment")}


def copy_text(key: str, default: str = "") -> str:
    return get_copy().get(key, default)


@router.get("/")
def read_copy():
    return {"copy": get_copy()}


def apply_edit(data: dict, key: str, value) -> dict:
    """Return a copy of ``data`` with ``key`` replaced. Pure — the validation
    the route enforces, testable without the file (same shape as
    positions._apply_text_edit). KeyError = unknown key (→ 404), ValueError =
    bad value (→ 400)."""
    if not isinstance(value, str):
        raise ValueError("value must be a string")
    if not value.strip():
        raise ValueError("value must not be empty")
    if not isinstance(key, str) or key.startswith("_comment") or key not in data or not isinstance(data[key], str):
        raise KeyError(f"unknown copy key {key!r} — add it to data/site_copy.json first")
    new_data = dict(data)
    new_data[key] = value
    return new_data


@router.patch("/{key}")
def patch_copy(key: str, payload: dict = Body(...), _admin: None = Depends(require_admin)):
    """Replace one string. Body: {"value": "…"}. The key must already exist."""
    with _store.lock:
        try:
            new_data = apply_edit(_store.load(), key, payload.get("value"))
        except KeyError as e:
            raise HTTPException(404, str(e.args[0]))
        except ValueError as e:
            raise HTTPException(400, str(e))
        _store.write(new_data)
    return {"key": key, "value": payload.get("value")}
