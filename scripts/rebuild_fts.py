"""Rebuild the two FTS5 mirrors of `articles` from the content table.

Both indexes are external-content tables (``content='articles'``) kept in sync
by triggers. Rebuild them if they ever drift (an integrity-check failure, or a
table dropped and recreated): ``articles_fts`` (unicode61, Latin-script
queries) and ``articles_fts_zh`` (trigram, Chinese queries; migration 0018).
History: articles_fts was first declared without its triggers, so writes to
``articles`` never reached it; this script was the one-off backfill.

Idempotent: each index is rebuilt in its own transaction, holding the write
lock throughout, then checked against `articles`. Staging (60k articles):
32 s + 87 s; prod (213k) is about 3.5x that, so run it between pipeline ticks.

Usage:
    venv/bin/python3 scripts/rebuild_fts.py [--db PATH] [--only articles_fts|articles_fts_zh]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scraper.utils.db import get_connection

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'cross_strait_signal.db')
INDEXES = ('articles_fts', 'articles_fts_zh')


def rebuild(db_path=DB_PATH, indexes=INDEXES):
    conn = get_connection(db_path)
    try:
        for table in indexes:
            print(f"Rebuilding {table} in {db_path}")
            start = time.time()
            conn.execute(f"INSERT INTO {table}({table}) VALUES('rebuild')")
            conn.commit()
            conn.execute(f"INSERT INTO {table}({table}, rank) VALUES('integrity-check', 1)")
            print(f"  done in {time.time() - start:.1f}s; integrity-check against articles passed")
    finally:
        conn.close()


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description="Rebuild the articles FTS5 indexes")
    ap.add_argument('--db', default=DB_PATH, help="Path to another worktree's DB (e.g. prod)")
    ap.add_argument('--only', choices=INDEXES, help="Rebuild one index")
    args = ap.parse_args()
    rebuild(args.db, (args.only,) if args.only else INDEXES)
