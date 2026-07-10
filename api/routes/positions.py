import json
import os
import threading

from fastapi import APIRouter

router = APIRouter(prefix="/api/positions", tags=["positions"])

# Curated content for the Positions & Legal Status page. Hand-edited JSON
# (see the file's own _comment for the authoring rules) — served whole, no
# DB involved. Reloaded on mtime change so content edits show up without a
# service restart, which matters during co-writing sessions.
_CONTENT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "scraper", "processors", "positions.json"
)

_lock = threading.Lock()
_cache = {"mtime": None, "data": None}


def _load():
    mtime = os.path.getmtime(_CONTENT_PATH)
    with _lock:
        if _cache["mtime"] != mtime:
            with open(_CONTENT_PATH, encoding="utf-8") as f:
                _cache["data"] = json.load(f)
            _cache["mtime"] = mtime
        return _cache["data"]


@router.get("/")
def get_positions():
    """Full curated positions content (public — the page is reference material)."""
    data = _load()
    # _comment* keys are authoring docs, not content.
    return {k: v for k, v in data.items() if not k.startswith("_comment")}
