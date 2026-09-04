-- LinkedIn post proposer log (scripts/propose_linkedin_post.py).
-- One row per story the proposer EMAILED to the analyst. Exists for two
-- things only: dedup (a story is never proposed twice — matched on the
-- cluster id OR on any shared article id, because cluster_events.py
-- regenerates ids every tick) and an audit trail of what was drafted.
-- NOTHING here feeds any editorial queue or the public site; the draft
-- is copied by hand into LinkedIn or not at all.

CREATE TABLE IF NOT EXISTS linkedin_drafts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id       TEXT NOT NULL,              -- articles.event_cluster_id, cast to text
    article_ids      TEXT NOT NULL,              -- JSON array of every member article id at proposal time
    draft            TEXT NOT NULL,              -- the post as emailed, plain text
    ranking_factors  TEXT NOT NULL,              -- JSON: winner factors + runner-ups + exclusion counts
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    emailed_at       TIMESTAMP,                  -- NULL only if the row was recorded without a send
    emailed_to       TEXT
);
CREATE INDEX IF NOT EXISTS idx_linkedin_drafts_cluster ON linkedin_drafts(cluster_id);
