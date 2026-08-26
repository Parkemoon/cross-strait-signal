import copy
import os

from fastapi import APIRouter, Body, Depends, HTTPException

from api.auth import require_admin
from api.json_store import JsonFileStore

router = APIRouter(prefix="/api/positions", tags=["positions"])

# Curated content for the Positions & Legal Status page. Hand-edited JSON
# (see the file's own _comment for the authoring rules) — served whole, no
# DB involved. Reloaded on mtime change so content edits show up without a
# service restart, which matters during co-writing sessions.
_CONTENT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "scraper", "processors", "positions.json"
)

_store = JsonFileStore(_CONTENT_PATH)


def _load():
    return _store.load()


@router.get("/")
def get_positions():
    """Full curated positions content (public — the page is reference material)."""
    data = _load()
    # _comment* keys are authoring docs, not content.
    return {k: v for k, v in data.items() if not k.startswith("_comment")}


# --- Inline text editing (admin) -------------------------------------------
#
# The admin PositionsTab can rewrite individual STRING fields in place (the
# co-writing flow: Claude drafts structure + sources, Ed polishes wording in
# the browser instead of posting edits through chat). Deliberately strings
# only — adding/removing entries or sources stays a hand-edit so the shape
# invariants in tests/test_positions_content.py can't be broken from the UI.

# Path roots an edit may enter, and leaf keys it may never touch (structural
# identifiers; changing them would orphan React keys / readings.actor_id refs).
_EDITABLE_ROOTS = {"actors", "concepts", "_meta"}
_PROTECTED_LEAVES = {"id", "actor_id", "party", "depth", "iso"}


def _apply_text_edit(data, path, value):
    """Return a deep-copied ``data`` with the string leaf at ``path`` replaced.

    Raises ValueError with a human-readable message on any invalid edit.
    """
    if not isinstance(value, str):
        raise ValueError("value must be a string")
    if not isinstance(path, list) or not path:
        raise ValueError("path must be a non-empty list")
    for seg in path:
        if not isinstance(seg, (str, int)) or isinstance(seg, bool):
            raise ValueError("path segments must be strings or integers")
        if isinstance(seg, str) and seg.startswith("_comment"):
            raise ValueError("authoring-doc keys are not editable")
    if path[0] not in _EDITABLE_ROOTS:
        raise ValueError(f"path must start with one of {sorted(_EDITABLE_ROOTS)}")
    if path[-1] in _PROTECTED_LEAVES:
        raise ValueError(f"'{path[-1]}' is structural and not editable")

    new_data = copy.deepcopy(data)
    node = new_data
    for seg in path[:-1]:
        if isinstance(node, list):
            if not isinstance(seg, int) or not (0 <= seg < len(node)):
                raise ValueError(f"invalid list index {seg!r} in path")
            node = node[seg]
        elif isinstance(node, dict):
            if seg not in node:
                raise ValueError(f"unknown key {seg!r} in path")
            node = node[seg]
        else:
            raise ValueError(f"path descends through a non-container at {seg!r}")

    leaf = path[-1]
    if isinstance(node, dict):
        if leaf not in node:
            raise ValueError(f"unknown key {leaf!r} in path")
        if not isinstance(node[leaf], str):
            raise ValueError("only string fields are editable")
        node[leaf] = value
    else:
        raise ValueError("path must end at a named field, not a list position")
    return new_data


@router.patch("/text")
def patch_text(payload: dict = Body(...), _admin: None = Depends(require_admin)):
    """Replace one string field, addressed by its JSON path from the file root.

    Body: {"path": ["actors", 0, "intro_en"], "value": "…"}.
    """
    with _store.lock:
        try:
            new_data = _apply_text_edit(_store.load(), payload.get("path"), payload.get("value"))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        _store.write(new_data)
    return {"status": "ok", "path": payload["path"]}
