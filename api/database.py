import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'cross_strait_signal.db')


def get_db():
    """Return a database connection. Caller is responsible for closing.

    Prefer ``db_conn()`` (context manager) in new code so connections are
    released even when a query raises.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_conn():
    """Context-managed database connection. Always closes, even on exception."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
