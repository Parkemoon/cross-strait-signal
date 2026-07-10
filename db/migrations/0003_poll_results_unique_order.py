"""Rebuild poll_results with UNIQUE(poll_id, question_id, option_order).

The constraint was changed from option_label_zh to option_order before the
migration framework existed (commit 69f10f7 updated seed_nccu_polls.py to
match), but the rebuild was only ever applied ad hoc to the prod DB —
staging still carried the old constraint, and the seed script's
ON CONFLICT(poll_id, question_id, option_order) errors against it.
Idempotent: inspects the live constraint via sqlite_master and no-ops on
DBs (prod, fresh inits) already rebuilt.

Why option_order, not label_zh: two options can legitimately share a
Chinese label but disambiguate via English (or vice versa); option_order
is the canonical per-question position the chart pivots on.
"""

_NEW_TABLE = """
CREATE TABLE poll_results_new (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_id         INTEGER NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    question_id     INTEGER NOT NULL REFERENCES poll_questions(id),
    option_label_zh TEXT NOT NULL,
    option_label_en TEXT,
    option_order    INTEGER,
    percentage      REAL NOT NULL,
    margin_error    REAL,
    UNIQUE(poll_id, question_id, option_order)
)
"""


def migrate(conn):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='poll_results'"
    ).fetchone()
    if row is None:
        return  # fresh init — schema.sql creates it with the new constraint
    if 'unique(poll_id,question_id,option_order)' in row['sql'].replace(' ', '').lower():
        return  # already rebuilt (prod, or a fresh init)

    conn.execute(_NEW_TABLE)
    conn.execute("""
        INSERT INTO poll_results_new
            (id, poll_id, question_id, option_label_zh, option_label_en,
             option_order, percentage, margin_error)
        SELECT id, poll_id, question_id, option_label_zh, option_label_en,
               option_order, percentage, margin_error
        FROM poll_results
    """)
    conn.execute("DROP TABLE poll_results")
    conn.execute("ALTER TABLE poll_results_new RENAME TO poll_results")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_poll_results_poll "
                 "ON poll_results(poll_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_poll_results_question "
                 "ON poll_results(question_id)")
