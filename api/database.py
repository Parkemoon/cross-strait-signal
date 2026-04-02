import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'cross_strait_signal.db')


def get_db():
    """Get a database connection for API requests."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn