import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'db', 'cross_strait_signal.db')


def get_connection():
    """Get a database connection with row_factory set for dict-like access.

    `foreign_keys=ON` activates ON DELETE CASCADE (a no-op without it —
    applies to poll_results.poll_id and any future cascading FKs).
    `busy_timeout` makes writers wait up to 30s for the lock instead of
    erroring with 'database is locked' when the cron pipeline overlaps
    a long-running scrape (Step 2L Playwright + Step 3c can contend)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # This lets you access columns by name
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def article_exists(conn, url):
    """Check if an article URL is already in the database. This is your deduplication."""
    cursor = conn.execute("SELECT id FROM articles WHERE url = ?", (url,))
    return cursor.fetchone() is not None