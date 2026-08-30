-- Cross-strait visits tracker (Phase 2f). One row per publicly reported
-- visit / meeting / exchange between an official- or party-level actor from
-- Taiwan and one from the mainland (incl. HK/Macao). Scope is DELIBERATELY
-- cross-strait only: Taiwan↔third-country and PRC↔third-country travel is the
-- diplomacy axis (diplomacy_statements), never this table (Ed, 2026-08-30).
--
-- Side-extracted by a topic-gated pass (pipeline Step 3e) over analysed
-- DIP_VISIT / PARTY_VISIT articles — NOT part of the unconditional Tier-1
-- prompt, so it costs one extra call on ~5% of articles instead of prompt
-- tokens on every article. Same editorial gate as diplomacy_statements:
-- candidates land 'pending'; several articles on one trip yield several
-- rows the analyst merges (no mechanical canonical key — a delegation has
-- no exercise-style name). Blocked / cancelled visits are kept: a denied
-- entry permit is a signal in its own right.

CREATE TABLE IF NOT EXISTS cross_strait_visits (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id             INTEGER NOT NULL REFERENCES articles(id),
    direction              TEXT NOT NULL CHECK (direction IN ('TW_TO_PRC','PRC_TO_TW','THIRD_VENUE')),
    visit_status           TEXT NOT NULL DEFAULT 'reported'
                           CHECK (visit_status IN ('reported','planned','rumoured','cancelled','blocked')),
    -- the travelling party (for THIRD_VENUE: the Taiwan-side party)
    visitor_name_en        TEXT,
    visitor_name_zh        TEXT,
    visitor_title          TEXT,                    -- role as printed, English
    visitor_affiliation    TEXT NOT NULL,           -- enum, see visits_extract.AFFILIATIONS
    visitor_side           TEXT NOT NULL CHECK (visitor_side IN ('TW','PRC')),
    visitor_figure_id      TEXT,                    -- key_figures.json id when the alias resolves
    visit_level            TEXT NOT NULL DEFAULT 'other',  -- enum, see visits_extract.LEVELS
    delegation_desc_en     TEXT,                    -- e.g. 'KMT youth delegation, ~30 members'
    -- who they met (may be null when the article names only the venue/event)
    counterpart_name_en    TEXT,
    counterpart_name_zh    TEXT,
    counterpart_title      TEXT,
    counterpart_affiliation TEXT,
    counterpart_figure_id  TEXT,
    -- the occasion
    event_name_en          TEXT,                    -- 'Straits Forum', 'Shanghai–Taipei City Forum'
    event_name_zh          TEXT,
    location_label         TEXT,                    -- city / venue, English
    start_date             TEXT,                    -- YYYY-MM-DD
    end_date               TEXT,
    purpose_en             TEXT,                    -- one English sentence
    quote_zh               TEXT,                    -- verbatim original-language snippet
    confidence             REAL,
    -- editorial gate (shared review_queue primitives)
    approval_status        TEXT NOT NULL DEFAULT 'pending'
                           CHECK (approval_status IN ('pending','approved','dismissed','merged')),
    merged_into_id         INTEGER REFERENCES cross_strait_visits(id),
    reviewed_at            TIMESTAMP,
    reviewed_by            TEXT,
    created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_csv_article  ON cross_strait_visits(article_id);
CREATE INDEX IF NOT EXISTS idx_csv_status   ON cross_strait_visits(approval_status);
CREATE INDEX IF NOT EXISTS idx_csv_date     ON cross_strait_visits(start_date);
CREATE INDEX IF NOT EXISTS idx_csv_figure   ON cross_strait_visits(visitor_figure_id);

-- Scan marker: stamped after EVERY visit scan of an article, zero-yield
-- included, so an article is only ever sent to the API once (the same
-- lesson as articles.exercise_scanned_at — idempotency on inserted rows
-- alone re-qualifies no-yield articles every tick).
CREATE TABLE IF NOT EXISTS cross_strait_visit_scans (
    article_id   INTEGER PRIMARY KEY REFERENCES articles(id),
    scanned_at   TEXT NOT NULL DEFAULT (datetime('now')),
    n_extracted  INTEGER NOT NULL DEFAULT 0,
    n_inserted   INTEGER NOT NULL DEFAULT 0
);
