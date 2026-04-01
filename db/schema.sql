-- ============================================================
-- CORE TABLES
-- ============================================================

CREATE TABLE sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,               -- e.g. "PRC Ministry of Foreign Affairs"
    name_zh         TEXT,                        -- 中华人民共和国外交部
    url             TEXT NOT NULL,
    source_type     TEXT NOT NULL,               -- 'government', 'military', 'state_media', 'independent_media', 'think_tank', 'osint_feed'
    country         TEXT NOT NULL,               -- 'PRC', 'TW', 'US', 'UK', 'intl'
    language        TEXT NOT NULL,               -- 'zh-cn', 'zh-tw', 'en', 'multi'
    tier            INTEGER NOT NULL DEFAULT 2,  -- 1=official/military, 2=media, 3=think_tank, 4=osint
    scrape_interval INTEGER NOT NULL DEFAULT 360,-- minutes between scrapes
    scrape_method   TEXT NOT NULL DEFAULT 'rss', -- 'rss', 'html_scrape', 'api'
    is_active       BOOLEAN NOT NULL DEFAULT 1,
    last_scraped    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       INTEGER NOT NULL REFERENCES sources(id),
    url             TEXT UNIQUE NOT NULL,        -- deduplication key
    title_original  TEXT NOT NULL,               -- original language title
    title_en        TEXT,                        -- AI-translated English title
    content_original TEXT NOT NULL,              -- full text in original language
    content_en      TEXT,                        -- AI-translated English text (summary or full)
    language        TEXT NOT NULL,               -- 'zh-cn', 'zh-tw', 'en'
    published_at    TIMESTAMP,
    scraped_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ai_processed    BOOLEAN NOT NULL DEFAULT 0,
    ai_processed_at TIMESTAMP,
    word_count      INTEGER
);

CREATE TABLE ai_analysis (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER NOT NULL REFERENCES articles(id),
    -- Classification
    topic_primary   TEXT NOT NULL,               -- see Topic Taxonomy below
    topic_secondary TEXT,                        -- optional second topic
    sentiment       TEXT NOT NULL,               -- 'escalatory', 'conciliatory', 'neutral', 'ambiguous'
    sentiment_score REAL,                        -- -1.0 (strongly conciliatory) to +1.0 (strongly escalatory)
    urgency         TEXT NOT NULL DEFAULT 'routine', -- 'flash', 'priority', 'routine'
    -- AI-generated summary
    summary_en      TEXT NOT NULL,               -- 2-3 sentence English summary
    summary_zh      TEXT,                        -- Chinese summary (for verification)
    key_quote       TEXT,                        -- most significant direct quote (original language)
    key_quote_en    TEXT,                        -- translated quote
    -- Analytical flags
    is_new_formulation BOOLEAN DEFAULT 0,        -- new diplomatic language detected
    is_escalation_signal BOOLEAN DEFAULT 0,      -- potential escalation indicator
    escalation_note TEXT,                        -- AI explanation if flagged
    -- Metadata
    model_used      TEXT NOT NULL DEFAULT 'claude-sonnet-4-20250514',
    confidence      REAL,                        -- AI self-assessed confidence 0-1
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE entities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER NOT NULL REFERENCES articles(id),
    entity_name     TEXT NOT NULL,               -- e.g. "Xi Jinping", "东部战区"
    entity_name_en  TEXT,                        -- "Xi Jinping", "Eastern Theatre Command"
    entity_type     TEXT NOT NULL,               -- 'person', 'military_unit', 'ship', 'aircraft', 'location', 'organisation', 'weapon_system'
    entity_role     TEXT,                        -- 'leader', 'spokesperson', 'military_commander', etc.
    location_name   TEXT,                        -- associated location if mentioned
    latitude        REAL,                        -- geocoded (Phase 2)
    longitude       REAL,                        -- geocoded (Phase 2)
    context         TEXT,                        -- sentence/paragraph where entity appears
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE keywords_matched (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER NOT NULL REFERENCES articles(id),
    keyword         TEXT NOT NULL,
    keyword_category TEXT NOT NULL,              -- matches taxonomy categories
    match_context   TEXT                         -- surrounding sentence
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_articles_source      ON articles(source_id);
CREATE INDEX idx_articles_published   ON articles(published_at DESC);
CREATE INDEX idx_articles_url         ON articles(url);
CREATE INDEX idx_analysis_topic       ON ai_analysis(topic_primary);
CREATE INDEX idx_analysis_sentiment   ON ai_analysis(sentiment);
CREATE INDEX idx_analysis_urgency     ON ai_analysis(urgency);
CREATE INDEX idx_analysis_escalation  ON ai_analysis(is_escalation_signal);
CREATE INDEX idx_entities_type        ON entities(entity_type);
CREATE INDEX idx_entities_name        ON entities(entity_name);
CREATE INDEX idx_keywords_category    ON keywords_matched(keyword_category);

-- ============================================================
-- FULL-TEXT SEARCH (SQLite FTS5)
-- ============================================================

CREATE VIRTUAL TABLE articles_fts USING fts5(
    title_original,
    title_en,
    content_original,
    content_en,
    content='articles',
    content_rowid='id'
);