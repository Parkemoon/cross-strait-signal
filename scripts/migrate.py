"""
Versioned schema migrations (CODE_REVIEW_2026-07-03 §4.2).

Replaces the server_deploy.sh inline heredoc + `2>/dev/null || true` ALTER
pattern, which (a) swallowed every error including SQLITE_BUSY (a deploy
coinciding with the 6h cron lock silently skipped the migration → API
500s on the missing column), (b) re-ran dated data-fix UPDATEs on every
deploy, and (c) had to be hand-mirrored into db/schema.sql.

How it works:
  - db/migrations/ holds ordered files: NNNN_name.sql (run via
    executescript) or NNNN_name.py (must define migrate(conn) — used for
    ALTER TABLE, which needs duplicate-column tolerance SQLite can't
    express in SQL).
  - A schema_migrations table records each applied filename; files
    already recorded are skipped. Each migration commits on success.
  - The connection comes from scraper.utils.db.get_connection, so the
    30s busy_timeout applies — a concurrent cron tick delays the
    migration instead of silently skipping it, and any real error
    raises loudly and fails the deploy.

Adding schema: write a NEW numbered file here AND mirror the object into
db/schema.sql (fresh-init parity — init_db.py runs schema.sql then this
runner, which records everything as applied). 0001_baseline.sql is the
frozen pre-framework state; never edit it.

Usage:
    python scripts/migrate.py              # apply pending to the worktree DB
    python scripts/migrate.py --status     # list applied/pending
    python scripts/migrate.py --db /var/www/cross-strait-signal/db/cross_strait_signal.db
"""
import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scraper.utils.db import get_connection

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), '..', 'db', 'migrations')


def _migration_files():
    names = [n for n in os.listdir(MIGRATIONS_DIR)
             if (n.endswith('.sql') or n.endswith('.py'))
             and n[:4].isdigit() and not n.startswith('__')]
    return sorted(names)


def _applied(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name       TEXT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}


def _run_one(conn, name):
    path = os.path.join(MIGRATIONS_DIR, name)
    if name.endswith('.sql'):
        with open(path, encoding='utf-8') as f:
            conn.executescript(f.read())
    else:
        spec = importlib.util.spec_from_file_location(f'migration_{name[:-3]}', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.migrate(conn)
    conn.execute("INSERT INTO schema_migrations (name) VALUES (?)", (name,))
    conn.commit()


def apply_migrations(conn, quiet=False):
    """Apply every pending migration in order. Returns the applied names.
    Called by this script's CLI, server_deploy.sh, and init_db.py."""
    done = _applied(conn)
    applied = []
    for name in _migration_files():
        if name in done:
            continue
        if not quiet:
            print(f"  applying {name} ...")
        _run_one(conn, name)
        applied.append(name)
    return applied


def main():
    ap = argparse.ArgumentParser(description="Apply pending schema migrations")
    ap.add_argument('--db', help="Path to another worktree's DB (e.g. prod)")
    ap.add_argument('--status', action='store_true', help="List applied/pending, apply nothing")
    args = ap.parse_args()

    conn = get_connection(args.db)
    try:
        if args.status:
            done = _applied(conn)
            for name in _migration_files():
                print(f"  [{'applied' if name in done else 'PENDING'}] {name}")
            return
        applied = apply_migrations(conn)
        if applied:
            print(f"Applied {len(applied)} migration(s): {', '.join(applied)}")
        else:
            print("Schema up to date — no pending migrations.")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
