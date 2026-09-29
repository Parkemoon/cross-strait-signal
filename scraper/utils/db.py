import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'db', 'cross_strait_signal.db')


def get_connection(db_path=None):
    """Get a database connection with row_factory set for dict-like access.

    `foreign_keys=ON` activates ON DELETE CASCADE (a no-op without it —
    applies to poll_results.poll_id and any future cascading FKs).
    `busy_timeout` makes writers wait up to 30s for the lock instead of
    erroring with 'database is locked' when the cron pipeline overlaps
    a long-running scrape (Step 2L Playwright + Step 3c can contend).

    `synchronous = NORMAL` once the file is in WAL mode (migration 0016):
    commits stop waiting on an fsync, and under WAL a power cut can lose the
    last commits but cannot corrupt the file. Under the rollback journal it
    could, so a database still in that mode keeps the default FULL.

    db_path overrides the module default — for scripts with a --db flag
    that target another worktree's DB. Every script that talks to the
    canonical DB should come through here; bare sqlite3.connect() misses
    the pragmas and can die with 'database is locked' under the cron."""
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row  # This lets you access columns by name
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    if conn.execute("PRAGMA journal_mode").fetchone()[0] == 'wal':
        conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def article_exists(conn, url):
    """Check if an article URL is already in the database. This is your deduplication."""
    cursor = conn.execute("SELECT id FROM articles WHERE url = ?", (url,))
    return cursor.fetchone() is not None


# Stored-content cap. 25,000 chars matches ai_pipeline's
# MAX_PROMPT_CONTENT_CHARS — storing less than the model can read throws
# away analysable text. (Per-scraper caps had drifted 10K vs 25K before
# this was centralised — CODE_REVIEW_2026-07-03 §4.9.)
ARTICLE_CONTENT_CAP = 25000


def save_article(conn, source_id, url, title, content, language, published_at):
    """The single INSERT INTO articles every scraper routes through.
    Applies the standard content cap and commits.

    Scrapers fetch the next article over the network between saves (up to
    30-45 s a page). Committing once at the end of a scrape held the write
    lock across all of those fetches, so analyst approvals and other
    pipeline writers queued behind a whole feed, and a crash mid-scrape lost
    every article saved so far."""
    conn.execute("""
        INSERT INTO articles (source_id, url, title_original, content_original, language, published_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (source_id, url, title, (content or '')[:ARTICLE_CONTENT_CAP],
          language, published_at))
    conn.commit()