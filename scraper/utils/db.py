import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'db', 'cross_strait_signal.db')


def get_connection():
    """Get a database connection with row_factory set for dict-like access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # This lets you access columns by name
    return conn


def article_exists(conn, url):
    """Check if an article URL is already in the database. This is your deduplication."""
    cursor = conn.execute("SELECT id FROM articles WHERE url = ?", (url,))
    return cursor.fetchone() is not None