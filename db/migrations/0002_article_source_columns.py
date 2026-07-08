"""ALTER-based columns that predate the migration framework.

SQLite has no `ADD COLUMN IF NOT EXISTS`, so column additions are Python
migrations that tolerate exactly the duplicate-column error (anything
else — locked DB, syntax error — raises loudly; the old deploy-script
pattern `2>/dev/null || true` swallowed everything including SQLITE_BUSY).
"""

_ALTERS = [
    # polls staged-results blob (Phase 2d)
    "ALTER TABLE polls ADD COLUMN pending_results_json TEXT",
    # pollster side-disambiguation for state_official chips
    "ALTER TABLE pollsters ADD COLUMN place TEXT NOT NULL DEFAULT 'TW'",
    # Step 3b/3c scan markers (code-review §3.1)
    "ALTER TABLE articles ADD COLUMN poll_scanned_at TIMESTAMP",
    "ALTER TABLE articles ADD COLUMN exercise_scanned_at TIMESTAMP",
    # source behaviour flags (code-review §4.7)
    "ALTER TABLE sources ADD COLUMN is_pollster_direct BOOLEAN NOT NULL DEFAULT 0",
    "ALTER TABLE sources ADD COLUMN exercise_only_scan BOOLEAN NOT NULL DEFAULT 0",
]


def migrate(conn):
    import sqlite3
    for stmt in _ALTERS:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as e:
            if 'duplicate column name' not in str(e).lower():
                raise
