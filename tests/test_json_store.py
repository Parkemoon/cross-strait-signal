"""JsonFileStore — the shared mtime-cache + atomic-write helper behind
positions.json and site_copy.json."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.json_store import JsonFileStore  # noqa: E402


def test_load_write_and_external_edit_reload(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"a": "1"}), encoding="utf-8")
    store = JsonFileStore(str(p))
    assert store.load() == {"a": "1"}
    assert store.load() is store.load()                     # cached object, no re-read

    store.write({"a": "2"})
    assert store.load() == {"a": "2"}
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": "2"}
    assert not (tmp_path / "c.json.tmp").exists()           # atomic rename, no temp left behind
    assert p.read_text(encoding="utf-8").endswith("}\n")    # normalised formatting

    # an edit made outside the process (hand edit, git checkout) is picked up on mtime change
    time.sleep(0.01)
    p.write_text(json.dumps({"a": "3"}), encoding="utf-8")
    os.utime(p, (time.time() + 5, time.time() + 5))         # force a distinct mtime even on coarse filesystems
    assert store.load() == {"a": "3"}


def test_lock_is_reentrant_for_read_modify_write(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{}", encoding="utf-8")
    store = JsonFileStore(str(p))
    with store.lock:                                        # the routes hold the lock while calling load()+write()
        data = dict(store.load())
        data["k"] = "v"
        store.write(data)
    assert store.load() == {"k": "v"}
