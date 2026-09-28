"""Re-key event cluster ids that SQLite stored as numbers (2026-09-28).

cluster_events.py used bare 8-hex ids in an INTEGER-affinity column, so ids
that looked numeric were coerced: '3e412345' became REAL inf (52 prod rows
from about 20 unrelated clusters shared it, and the feed's "also covered by"
list mixed them all), and all-digit ids became integers. New ids carry a
letter prefix; this migration re-keys the old ones once, re-grouping the
infinity rows by the clustering rule itself. Logic lives in
scripts/cluster_events.py (repair_numeric_cluster_ids) so it is tested there.
"""
import importlib.util
import os


def migrate(conn):
    path = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', 'cluster_events.py')
    spec = importlib.util.spec_from_file_location('cluster_events_for_0015', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    summary = mod.repair_numeric_cluster_ids(conn)
    print(f"    cluster ids: {summary}")
