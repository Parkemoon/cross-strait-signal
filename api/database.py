import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'cross_strait_signal.db')


def _configure(conn):
    """Per-connection PRAGMAs. `foreign_keys=ON` activates ON DELETE
    CASCADE (it's a no-op without this — applies to poll_results.poll_id
    and any future cascading FKs). `busy_timeout` makes writers wait up
    to 30s for the lock instead of erroring with 'database is locked'
    when the cron pipeline overlaps a long-running scrape."""
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def get_db():
    """Return a database connection. Caller is responsible for closing.

    Prefer ``db_conn()`` (context manager) in new code so connections are
    released even when a query raises.
    """
    return _configure(sqlite3.connect(DB_PATH))


@contextmanager
def db_conn():
    """Context-managed database connection. Always closes, even on exception."""
    conn = _configure(sqlite3.connect(DB_PATH))
    try:
        yield conn
    finally:
        conn.close()
