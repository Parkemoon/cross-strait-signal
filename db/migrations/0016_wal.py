"""Switch the database to WAL journaling (2026-09-29).

In the default rollback journal a committing writer locks readers out, and a
long read holds off a writer's commit, so the six-hourly pipeline, the API and
detached backfills collided as 'database is locked'. In WAL mode readers run
alongside the one writer. The mode is stored in the database file, so this runs
once; `synchronous = NORMAL` (safe under WAL: a power cut can lose the last
commits but cannot corrupt the file) is per-connection and set by both
connection factories.

Switching needs a moment with no other connection mid-transaction; the runner's
30 s busy_timeout waits for one.
"""


def migrate(conn):
    # Inside an open transaction SQLite ignores the switch and just reports
    # the current mode, so close any the caller left open.
    conn.commit()
    mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0].lower()
    # An in-memory database reports 'memory' and cannot use WAL.
    if mode not in ('wal', 'memory'):
        raise RuntimeError(f"journal_mode is {mode!r} after the switch, expected 'wal'")
