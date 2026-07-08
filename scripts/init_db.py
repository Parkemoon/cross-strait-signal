import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scraper.utils.db import get_connection

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'cross_strait_signal.db')

def init_database():
    """Create the database and tables, then bring the migration ledger up
    to date. schema.sql already contains every object, so the migrations
    themselves no-op on a fresh DB (they're all idempotent) — running the
    runner here just records them in schema_migrations so a later deploy
    doesn't re-apply history."""
    schema_path = os.path.join(os.path.dirname(__file__), '..', 'db', 'schema.sql')
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = f.read()

    conn = get_connection(DB_PATH)
    conn.executescript(schema)

    from scripts.migrate import apply_migrations
    applied = apply_migrations(conn, quiet=True)
    conn.close()

    print(f"Database created at: {DB_PATH} "
          f"({len(applied)} migration(s) recorded)")

if __name__ == '__main__':
    init_database()
