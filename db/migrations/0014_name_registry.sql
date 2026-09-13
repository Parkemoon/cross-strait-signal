-- Name registry (2026-09-13): one row per Chinese personal name the pipeline
-- has met, with the English form the site uses for it and where that form
-- came from. Seeded from glossary.json + entity_canonical.json
-- (scripts/seed_name_registry.py); grown by the post-Tier-1 lookup worker
-- (scraper/processors/name_lookup.py — Wikidata exact label, then grounded
-- search, then a generated Wade-Giles fallback) and by analyst approvals in
-- the Admin ▾ Names queue. Only status='approved' rows feed the resolver and
-- the prompt-time glossary block; a wrong canonical would propagate to every
-- later article, so nothing but a Wikidata hit with Taiwan citizenship and a
-- matching role auto-approves. Mirrored in db/schema.sql.

CREATE TABLE IF NOT EXISTS name_registry (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    zh_trad          TEXT NOT NULL UNIQUE,        -- traditional form (simplified folded onto it)
    zh_simp          TEXT,                        -- simplified form when it differs
    en               TEXT,                        -- canonical English; NULL while pending with no proposal
    side             TEXT CHECK (side IN ('TW', 'PRC', 'OTHER')),
    source           TEXT NOT NULL,               -- glossary | canonical | survey | wikidata | search | generated | analyst
    status           TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    qid              TEXT,                        -- Wikidata item when the form came from there
    evidence_url     TEXT,                        -- page the form was verified on (search tier)
    evidence_note    TEXT,                        -- Wikidata description / verification note / reason for pending
    role_hint        TEXT,                        -- the model's role text for the person, for namesake checks
    candidates_json  TEXT,                        -- JSON list of alternative forms seen (renderings, namesakes)
    mentions         INTEGER NOT NULL DEFAULT 0,
    first_article_id INTEGER,
    confidence       REAL,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    reviewed_at      TEXT,
    reviewed_by      TEXT
);
CREATE INDEX IF NOT EXISTS idx_name_registry_simp ON name_registry(zh_simp);
CREATE INDEX IF NOT EXISTS idx_name_registry_status ON name_registry(status);
