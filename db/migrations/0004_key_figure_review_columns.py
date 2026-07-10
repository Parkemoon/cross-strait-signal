"""Align key_figure_statements with the other three review queues
(code-review §4.3): every editorial gate now carries the full
pending/approved/dismissed/merged state machine columns, served by the
shared primitives in api/review_queue.py. Same tolerant-ALTER pattern
as 0002 (SQLite has no ADD COLUMN IF NOT EXISTS).
"""

_ALTERS = [
    "ALTER TABLE key_figure_statements ADD COLUMN reviewed_by TEXT",
    "ALTER TABLE key_figure_statements ADD COLUMN merged_into_id INTEGER REFERENCES key_figure_statements(id)",
]


def migrate(conn):
    import sqlite3
    for stmt in _ALTERS:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as e:
            if 'duplicate column name' not in str(e).lower():
                raise
