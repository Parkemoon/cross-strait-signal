"""One-off rebuild of the articles_fts FTS5 index.

The FTS5 virtual table was declared as ``content='articles'`` (external content
mode) without INSERT/UPDATE/DELETE triggers, so historical writes to
``articles`` never made it into the index. Run this once to backfill, and
ensure the new triggers in ``schema.sql`` / ``server_deploy.sh`` are in place
so future inserts stay in sync.

Idempotent: re-running drops and rebuilds the index in one transaction.
Takes ~30-60 seconds for a ~55k-row corpus.

Usage:
    venv/bin/python3 scripts/rebuild_fts.py
"""
import os
import sqlite3
import sys
import time

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'cross_strait_signal.db')


def rebuild():
    print(f"Rebuilding articles_fts in {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        start = time.time()
        conn.execute("INSERT INTO articles_fts(articles_fts) VALUES('rebuild')")
        conn.commit()
        elapsed = time.time() - start

        before, after = conn.execute(
            "SELECT (SELECT COUNT(*) FROM articles), "
            "(SELECT COUNT(*) FROM articles_fts WHERE articles_fts MATCH 'a' OR articles_fts MATCH 'the')"
        ).fetchone()
        print(f"Done in {elapsed:.1f}s. {before} articles, {after} indexed rows matched a smoke-test query.")
    finally:
        conn.close()


if __name__ == '__main__':
    rebuild()
    sys.exit(0)
