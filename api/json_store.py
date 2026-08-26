"""A hand-edited JSON content file served by the API and rewritten by it.

Shared by api/routes/positions.py (positions.json) and api/routes/copy.py
(site_copy.json): mtime-reload cache so file edits show up without a restart,
one lock so a PATCH can't interleave with a reload, atomic rewrite so a crash
mid-write never leaves a truncated file.

    store = JsonFileStore(path)
    data = store.load()                 # cached; re-read when the file's mtime changes
    with store.lock:                    # for read-modify-write
        new = edit(store.load(), ...)
        store.write(new)                # atomic; refreshes the cache
"""
from __future__ import annotations

import json
import os
import threading


class JsonFileStore:
    def __init__(self, path: str):
        self.path = path
        self.lock = threading.RLock()
        self._mtime = None
        self._data = None

    def load(self):
        mtime = os.path.getmtime(self.path)
        with self.lock:
            if self._mtime != mtime:
                with open(self.path, encoding="utf-8") as f:
                    self._data = json.load(f)
                self._mtime = mtime
            return self._data

    def write(self, data) -> None:
        """Atomic rewrite (json.dumps-normalised formatting), cache refreshed."""
        tmp = self.path + ".tmp"
        with self.lock:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp, self.path)
            self._data = data
            self._mtime = os.path.getmtime(self.path)
