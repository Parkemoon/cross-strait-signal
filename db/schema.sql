-- ============================================================
-- CORE TABLES
-- ============================================================

CREATE TABLE sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,               -- e.g. "PRC Ministry of Foreign Affairs"
    name_zh         TEXT,                        -- 中华人民共和国外交部
    url             TEXT NOT NULL,
    source_type     TEXT NOT NULL,               -- 'government', 'military', 'state_media', 'independent_media', 'think_tank', 'osint_feed'
    place           TEXT NOT NULL,               -- 'PRC', 'TW', 'HK', 'SG', etc.
    language        TEXT NOT NULL,               -- 'zh-cn', 'zh-tw', 'en', 'multi'
    tier            INTEGER NOT NULL DEFAULT 2,  -- 1=official/military, 2=media, 3=think_tank, 4=osint
    scrape_interval INTEGER NOT NULL DEFAULT 360,-- minutes between scrapes
    scrape_method   TEXT NOT NULL DEFAULT 'rss', -- 'rss', 'html_scrape', 'api'
    bias            TEXT,                        -- 'green', 'green_leaning', 'blue', 'centrist', 'state_official', 'state_nationalist'
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
    word_count      INTEGER,
    event_cluster_id INTEGER,                    -- links related articles within 48h window
    cluster_size    INTEGER DEFAULT 1,           -- number of articles in this cluster
    is_hidden       BOOLEAN DEFAULT 0,           -- hidden from feed (analyst action)
    is_active       BOOLEAN NOT NULL DEFAULT 1,  -- soft delete flag
    analyst_approved BOOLEAN DEFAULT 0,          -- must be approved by analyst before appearing on public feed
    title_en_override TEXT,                      -- analyst-corrected headline
    summary_en_override TEXT,                    -- analyst-corrected summary
    key_quote_override TEXT                      -- analyst-corrected key quote translation
);

CREATE TABLE ai_analysis (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER NOT NULL REFERENCES articles(id),
    -- Classification
    topic_primary   TEXT NOT NULL,               -- see Topic Taxonomy below
    topic_secondary TEXT,                        -- optional second topic
    sentiment       TEXT NOT NULL,               -- 'hostile', 'cooperative', 'neutral', 'mixed'
    sentiment_score REAL,                        -- -1.0 (strongly hostile) to +1.0 (strongly cooperative)
    sentiment_reasoning TEXT,                    -- one-sentence audit trail: who is framed how, toward whom, with quoted phrase
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
    -- Human review
    needs_human_review BOOLEAN DEFAULT 0,        -- flagged for analyst review
    review_resolved    BOOLEAN DEFAULT 0,        -- review completed
    is_hidden          BOOLEAN DEFAULT 0,        -- hidden from public feed pending review
    -- Metadata
    model_used      TEXT NOT NULL DEFAULT 'gemini-3.1-flash-lite',
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
-- ANALYST COMMENTARY
-- ============================================================

CREATE TABLE analyst_notes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER NOT NULL REFERENCES articles(id),
    note_text       TEXT NOT NULL,           -- your editorial commentary
    sentiment_override TEXT,                  -- override AI sentiment if wrong
    topic_override  TEXT,                     -- override AI topic if wrong
    score_override  REAL,                     -- override sentiment score (-1.0 to +1.0)
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_notes_article ON analyst_notes(article_id);

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

-- Sync triggers — keep articles_fts in lock-step with the articles table.
-- Without these, the external-content FTS5 index drifts: rows added to
-- articles never become searchable. If you ever drop and recreate the FTS
-- table, you also need to re-run scripts/rebuild_fts.py to backfill history.
CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
    INSERT INTO articles_fts(rowid, title_original, title_en, content_original, content_en)
    VALUES (new.id, new.title_original, new.title_en, new.content_original, new.content_en);
END;
CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title_original, title_en, content_original, content_en)
    VALUES('delete', old.id, old.title_original, old.title_en, old.content_original, old.content_en);
END;
CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title_original, title_en, content_original, content_en)
    VALUES('delete', old.id, old.title_original, old.title_en, old.content_original, old.content_en);
    INSERT INTO articles_fts(rowid, title_original, title_en, content_original, content_en)
    VALUES (new.id, new.title_original, new.title_en, new.content_original, new.content_en);
END;

-- ============================================================
-- SOCIAL PULSE (Weibo Hot Search + PTT trending posts)
-- ============================================================

CREATE TABLE IF NOT EXISTS social_pulse (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    platform          TEXT NOT NULL,       -- 'weibo' or 'ptt'
    item_key          TEXT NOT NULL,       -- weibo: keyword, ptt: post URL
    title             TEXT NOT NULL,       -- original Chinese keyword or post title
    title_en          TEXT,                -- AI-translated English (Gemini Flash Lite)
    title_en_override TEXT,                -- manual analyst correction
    rank_position     INTEGER,             -- Weibo: rank in hot search top 50
    heat_index        INTEGER,             -- Weibo: heat/热度 value
    push_count        INTEGER,             -- PTT: upvote count (100 = 爆)
    boo_count         INTEGER,             -- PTT: downvote count
    board             TEXT,                -- PTT: board name
    url               TEXT,                -- PTT: post URL
    scraped_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_social_pulse_platform_time ON social_pulse(platform, scraped_at DESC);

-- ============================================================
-- KEY FIGURE STATEMENTS (manual curation of attributed quotes/actions)
-- ============================================================

CREATE TABLE IF NOT EXISTS key_figure_statements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER NOT NULL REFERENCES articles(id),
    figure_id       TEXT NOT NULL,                  -- matches key_figures.json id
    speaker_raw     TEXT NOT NULL,                  -- name as extracted by AI
    statement_text  TEXT NOT NULL,                  -- English (translated if needed)
    statement_zh    TEXT,                           -- original-language version (optional)
    statement_kind  TEXT NOT NULL,                  -- 'quote' or 'action'
    confidence      REAL,
    approval_status TEXT NOT NULL DEFAULT 'pending',-- 'pending' | 'approved' | 'dismissed'
    reviewed_at     TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_kfs_figure_status ON key_figure_statements(figure_id, approval_status);
CREATE INDEX IF NOT EXISTS idx_kfs_article ON key_figure_statements(article_id);

-- ============================================================
-- ECONOMIC INDICATORS (Phase 2a — cross-strait trade, investment, people flows)
-- ============================================================
-- Sourced from data.gov.tw / MAC monthly speed reports.
-- One row per (series_id, period, period_type). Re-running the scraper
-- updates value/yoy_pct/scraped_at if MAC revises a historical figure.

CREATE TABLE IF NOT EXISTS economic_indicators (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id   TEXT NOT NULL,        -- e.g. 'trade_total_usd_b', 'exports_to_prc_usd_b'
    period      TEXT NOT NULL,        -- 'YYYY-MM' for month, 'YYYY' for annual
    period_type TEXT NOT NULL,        -- 'month' | 'ytd' | 'cumulative_alltime'
    value       REAL,                 -- NULL if MAC reports '—' (data not yet released)
    unit        TEXT NOT NULL,        -- 'usd_billion' | 'count' | '10k_persons'
    yoy_pct     REAL,                 -- year-on-year growth %, NULL if not reported
    source      TEXT NOT NULL,        -- 'MAC_7887', 'MAC_7888', etc.
    source_url  TEXT,                 -- URL of the source CSV file
    scraped_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(series_id, period, period_type)
);

CREATE INDEX IF NOT EXISTS idx_econ_series_period ON economic_indicators(series_id, period DESC);
CREATE INDEX IF NOT EXISTS idx_econ_period_type ON economic_indicators(period_type, period DESC);

-- ============================================================
-- TRADE ACCESS (Phase 2a.2 — cross-strait import permission regime)
-- ============================================================
-- One row per (direction, hs_code) tuple. `direction` records which side is
-- the *importer* (so an item TW refuses to import from PRC is
-- 'tw_imports_from_prc' with status 'banned'). Sources:
--   * BOFT 大陸物品不准許輸入項目 (TW ban list)
--   * BOFT 大陸物品有條件准許輸入項目 (TW conditional list)
--   * MoF Customs ECFA correspondence table (ODS) — paired TW↔PRC HS codes
--   * MoF (PRC) State Council Tariff Commission suspension PDFs
--   * Curated prc_trade_bans.json for PRC's targeted bans on TW goods

CREATE TABLE IF NOT EXISTS trade_access (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    direction             TEXT NOT NULL,   -- 'tw_imports_from_prc' | 'prc_imports_from_tw'
    hs_code               TEXT NOT NULL,   -- 8-digit HS code (the importer's system)
    product_zh            TEXT,
    product_en            TEXT,
    status                TEXT NOT NULL,   -- 'allowed' | 'banned' | 'conditional' | 'ecfa_active' | 'ecfa_suspended'
    effective_date        TEXT,            -- 'YYYY-MM-DD' if known, else NULL
    source                TEXT NOT NULL,   -- 'BOFT_22674' | 'BOFT_22675' | 'CUSTOMS_ECFA_2024' | 'MOF_PRC_SUSP_W1' | 'MOF_PRC_SUSP_W2' | 'CURATED'
    notes                 TEXT,
    ban_announcement_url  TEXT,            -- News / official URL for targeted bans
    scraped_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(direction, hs_code)
);

CREATE INDEX IF NOT EXISTS idx_trade_access_direction_status ON trade_access(direction, status);
CREATE INDEX IF NOT EXISTS idx_trade_access_hs ON trade_access(hs_code);

-- ============================================================
-- CROSS-STRAIT INVESTMENT BY INDUSTRY (Phase 2a.2 — MAC datasets 7478 + 7473)
-- ============================================================
-- Cumulative monthly snapshots of approved cross-strait investment cases,
-- broken out by industry sector. Two directions:
--   * direction='prc_to_tw' — MAC 7478, cumulative since 2009-07
--   * direction='tw_to_prc' — MAC 7473, cumulative since 1991
-- One row per (direction, period, industry_zh).
--
-- `period` is the END month of the cumulative range, formatted YYYY-MM.
-- `amount_usd_k` is in thousands of USD (normalised — MAC 7478 publishes
-- in 千美元 directly; 7473 publishes in 百萬美元 and is multiplied by 1000
-- on ingest). `amount_share_pct` is share of cumulative total at snapshot.

CREATE TABLE IF NOT EXISTS investment_by_industry (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    direction         TEXT NOT NULL,         -- 'prc_to_tw' | 'tw_to_prc'
    period            TEXT NOT NULL,
    industry_zh       TEXT NOT NULL,
    industry_en       TEXT,
    cases             INTEGER,
    amount_usd_k      REAL,
    amount_share_pct  REAL,
    source_url        TEXT,
    scraped_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(direction, period, industry_zh)
);

CREATE INDEX IF NOT EXISTS idx_invest_direction_period ON investment_by_industry(direction, period DESC);
CREATE INDEX IF NOT EXISTS idx_invest_industry ON investment_by_industry(industry_zh, direction, period DESC);

-- ============================================================
-- CIFER SNAPSHOTS (Phase 2a.2 — automated tracker of PRC's CIFER counts)
-- ============================================================
-- Headless-browser scraper drives ciferquery.singlewindow.cn (港澳台 tab,
-- country = 中国台湾) and captures the totals for status = 暫停進口
-- (suspended) and 有效 (valid). One row per (snapshot_date, status).
-- Cron runs monthly; the Trade Access tab reads the latest row to
-- replace the previously-hardcoded CIFER_SNAPSHOT constant.

CREATE TABLE IF NOT EXISTS cifer_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,          -- 'YYYY-MM-DD'
    status        TEXT NOT NULL,          -- 'suspended' | 'valid' | 'total'
    status_zh     TEXT,                   -- '暫停進口' | '有效' | '全部'
    count         INTEGER NOT NULL,
    notes         TEXT,
    scraped_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(snapshot_date, status)
);

CREATE INDEX IF NOT EXISTS idx_cifer_snapshots_date ON cifer_snapshots(snapshot_date DESC);

-- ============================================================
-- CROSS-STRAIT POPULATION (Phase 2a.2 — residents in the other side)
-- ============================================================
-- Unified table holding both directions of cross-strait residency:
--   * direction='taiwanese_in_prc'  — TW citizens living in PRC
--   * direction='prc_in_taiwan'     — PRC citizens living in TW
-- Multiple metric types per direction (residence flows, settlement
-- flows, cumulative spouse counts, census snapshots, 台胞证 issuance).
-- One row per (direction, metric, period, period_type).
--
-- Note: ROC household registration dropped 籍貫 (ancestral origin) in
-- 1992 to dissolve 省籍情結, so there's no current census-derived
-- 外省人 count — the 1949-cohort estimates remain ~1.2M but aren't
-- refreshed. Modern PRC-citizen residents in TW are tracked via NIA's
-- 居留/定居 permits and 大陸配偶 statistics.

CREATE TABLE IF NOT EXISTS cross_strait_population (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    direction   TEXT NOT NULL,        -- 'taiwanese_in_prc' | 'prc_in_taiwan'
    metric      TEXT NOT NULL,        -- 'permits_annual_residence' | 'permits_annual_settlement' |
                                      -- 'spouses_cumulative' | 'census_snapshot' |
                                      -- 'tbz_cumulative' | 'tbz_annual_issued' | etc.
    period      TEXT NOT NULL,        -- 'YYYY' for annual, 'YYYY-MM' for monthly
    period_type TEXT NOT NULL,        -- 'annual' | 'monthly' | 'snapshot'
    value       REAL,                 -- usually integer count
    unit        TEXT NOT NULL,        -- 'persons' | 'permits' (one company may issue multiple permits)
    source      TEXT NOT NULL,        -- 'TW_NIA_167829' | 'TW_NIA_13503' | 'PRC_CENSUS_7' | 'PRC_NIA' | 'CURATED'
    source_url  TEXT,
    notes       TEXT,
    scraped_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(direction, metric, period, period_type)
);

CREATE INDEX IF NOT EXISTS idx_csp_direction_metric ON cross_strait_population(direction, metric, period DESC);

-- ============================================================
-- PLA INCURSIONS (Phase 2b — MND daily activity tracker)
-- ============================================================
-- Daily counts of PLA aircraft and vessel activity around Taiwan,
-- as reported by Taiwan's Ministry of National Defence in its
-- "中共解放軍臺海周邊海、空域動態" press releases (reporting day runs
-- 0600-0600 in MND's convention). Two sources can populate a date:
--   * source='mnd'                  — live scrape of mnd.gov.tw
--   * source='platracker_backfill'  — one-time history pull from the
--                                     public PLATracker Google Sheet
-- API endpoints coalesce, preferring 'mnd' when both rows exist for
-- a date. MND publishes a list of zones plus a single crossing count
-- (not per-zone counts), so zones are stored as a comma-separated list
-- of sector codes drawn from {N, C, SW, SE, E} matching MND's wording
-- (北部 / 中部 / 西南 / 東南 / 東部).

CREATE TABLE IF NOT EXISTS pla_incursions (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    date                     TEXT NOT NULL,         -- 'YYYY-MM-DD'
    aircraft_total           INTEGER,               -- 共機 N 架次
    aircraft_intruded        INTEGER,               -- count in parenthetical, covers both 逾越中線 and ADIZ entry forms
    aircraft_zones           TEXT,                  -- comma list of sectors entered, e.g. 'N,SW,E'
    vessels_total            INTEGER,               -- 共艦 N 艘
    coast_guard_total        INTEGER,               -- 公務船 N 艘
    source                   TEXT NOT NULL,         -- 'mnd' | 'platracker_backfill'
    source_url               TEXT,
    raw_text                 TEXT,                  -- verbatim Chinese summary preserved for audit
    scraped_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, source)
);

CREATE INDEX IF NOT EXISTS idx_pla_incursions_date ON pla_incursions(date DESC);

-- ============================================================
-- MILITARY EXERCISES (Phase 2b.2 — cross-strait exercise tracker)
-- ============================================================
-- AI-extracted military exercises and drills from MIL_EXERCISE-topic
-- articles (named exercises like 聯合劍 / Joint Sword / Han Kuang, plus
-- unnamed readiness drills described in MND or PLA releases). Mirrors
-- the `key_figure_statements` editorial-gate pattern: candidates land
-- with approval_status='pending'; analyst confirms/edits/dismisses/
-- merges through the admin UI before public exposure.
--
-- One row per article-mention. The analyst uses 'merged' status to
-- collapse multiple articles about the same exercise (e.g. several
-- outlets reporting on Joint Sword 2024B) into a single canonical row;
-- merged_into_id links to the kept row.
--
-- Lat/lng are NULL unless the AI confidently parses a named base /
-- well-known waters / explicit coordinates. Rows without coords are
-- listed in the table view but omitted from the map.

CREATE TABLE IF NOT EXISTS military_exercises (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id        INTEGER NOT NULL REFERENCES articles(id),
    canonical_name    TEXT,                  -- 'joint-sword-2024b' (lower-hyphen); NULL for unnamed
    name_en           TEXT,
    name_zh           TEXT,
    name_raw          TEXT,
    performer         TEXT NOT NULL,         -- 'PRC' | 'ROC' | 'US' | 'JP' | 'MULTI'
    participants_json TEXT,                  -- '["US","JP","ROC"]' when performer='MULTI'
    exercise_kind     TEXT,                  -- 'live_fire'|'readiness_drill'|'joint_patrol'
                                             -- |'named_exercise'|'cyber'|'amphibious'|'other'
    start_date        TEXT,                  -- 'YYYY-MM-DD' (NULL if AI uncertain)
    end_date          TEXT,
    location_label    TEXT,
    latitude          REAL,                  -- NULL unless AI confident
    longitude         REAL,
    description_en    TEXT,
    description_zh    TEXT,
    confidence        REAL,
    approval_status   TEXT NOT NULL DEFAULT 'pending',  -- 'pending'|'approved'|'dismissed'|'merged'
    merged_into_id    INTEGER REFERENCES military_exercises(id),
    reviewed_at       TIMESTAMP,
    reviewed_by       TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_milex_status_date ON military_exercises(approval_status, start_date DESC);
CREATE INDEX IF NOT EXISTS idx_milex_canonical  ON military_exercises(canonical_name, approval_status);
CREATE INDEX IF NOT EXISTS idx_milex_article    ON military_exercises(article_id);
CREATE INDEX IF NOT EXISTS idx_milex_performer  ON military_exercises(performer, start_date DESC);

-- ============================================================
-- POLLS (Phase 2d — TW polling tracker)
-- ============================================================
-- Public opinion polling on cross-strait identity, unification
-- preference, presidential approval, and ad-hoc attitude questions
-- (war risk, US trust, KMT-PRC engagement). Mirrors the
-- `military_exercises` editorial-gate pattern: AI-extracted candidates
-- land with approval_status='pending' and are hidden from the public
-- tab until analyst review.
--
-- `pollsters` is a controlled vocabulary so bias chip and status are
-- consistent across every poll from that pollster.
--
-- `poll_questions` is the cross-pollster join key. A single
-- 'approval_lai_overall' question_key ties together TVBS, MyFormosa,
-- ETtoday versions of the same question so they plot on one chart.
-- Question keys are analyst-assigned during approval (NOT AI-extracted):
-- AI provides raw question text, the reviewer picks an existing key or
-- creates a new one. Prevents long-tail miscategorisation from
-- corrupting trend charts.
--
-- `poll_results` carries per-option percentages with option_order
-- preserved for stacked-chart display.
--
-- `source_article_id` on `polls` is populated automatically when the
-- row is AI-extracted from an article. NULL for manually-entered
-- polls. The canonical-merge step on approve collapses multi-outlet
-- coverage of the same underlying poll on (pollster_id, fielded_start)
-- match.

CREATE TABLE IF NOT EXISTS pollsters (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    slug         TEXT NOT NULL UNIQUE,       -- 'nccu_esc'|'myformosa'|'tvbs'|'ettoday'|'tpof'|'unknown'
    name_zh      TEXT NOT NULL,
    name_en      TEXT NOT NULL,
    bias         TEXT NOT NULL,              -- 'academic'|'green'|'green_leaning'|'centrist'|'blue_leaning'|'blue'|'state_official'
    status       TEXT NOT NULL DEFAULT 'active',  -- 'active'|'historical'|'ad_hoc'|'unknown'
    cadence      TEXT,                       -- 'monthly'|'biannual'|'ad_hoc'|NULL
    methodology  TEXT,                       -- default method (CATI, online panel, etc.)
    notes        TEXT,
    homepage_url TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pollsters_status ON pollsters(status);

CREATE TABLE IF NOT EXISTS poll_questions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    question_key     TEXT NOT NULL UNIQUE,   -- 'identity_nccu_3pt'|'unification_nccu_6pt'|'approval_lai_overall'|'war_risk_5y'
    question_text_zh TEXT NOT NULL,
    question_text_en TEXT NOT NULL,
    family           TEXT NOT NULL,          -- 'identity'|'unification'|'approval'|'attitude'|'vote_intent'|'issue'
    scale_type       TEXT NOT NULL,          -- 'approve_disapprove'|'support_oppose'|'five_point'|'six_point'|'choice'|'numeric'
    description      TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_poll_questions_family ON poll_questions(family);

CREATE TABLE IF NOT EXISTS polls (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    pollster_id          INTEGER NOT NULL REFERENCES pollsters(id),
    fielded_start        TEXT NOT NULL,         -- 'YYYY-MM-DD'
    fielded_end          TEXT,                  -- 'YYYY-MM-DD' (NULL for single-day fielding)
    sample_size          INTEGER,
    methodology_note     TEXT,                  -- per-poll method details
    source_url           TEXT,
    source_article_id    INTEGER REFERENCES articles(id),  -- where AI extracted from (NULL for manual entry)
    notes                TEXT,
    confidence           REAL,                  -- AI extraction confidence (NULL for manual)
    approval_status      TEXT NOT NULL DEFAULT 'pending',  -- 'pending'|'approved'|'dismissed'|'merged'
    -- Holds AI-extracted {questions:[{question_text_zh, question_text_en,
    -- family_hint, options:[{label_zh, label_en, percentage}]}]} while the
    -- poll sits in pending. The analyst picks a question_key for each entry
    -- in the review queue; on approve the server materialises poll_results
    -- rows from this blob and NULLs the column. NULL for manual entries
    -- (which create poll_results directly) and for already-approved polls.
    pending_results_json TEXT,
    merged_into_id       INTEGER REFERENCES polls(id),
    reviewed_at          TIMESTAMP,
    reviewed_by          TEXT,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_polls_status_date ON polls(approval_status, fielded_start DESC);
CREATE INDEX IF NOT EXISTS idx_polls_pollster ON polls(pollster_id, fielded_start DESC);
CREATE INDEX IF NOT EXISTS idx_polls_article ON polls(source_article_id);

CREATE TABLE IF NOT EXISTS poll_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_id         INTEGER NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    question_id     INTEGER NOT NULL REFERENCES poll_questions(id),
    option_label_zh TEXT NOT NULL,
    option_label_en TEXT,
    option_order    INTEGER,                 -- display order (low → high or source order)
    percentage      REAL NOT NULL,
    margin_error    REAL,
    UNIQUE(poll_id, question_id, option_label_zh)
);
CREATE INDEX IF NOT EXISTS idx_poll_results_poll ON poll_results(poll_id);
CREATE INDEX IF NOT EXISTS idx_poll_results_question ON poll_results(question_id);

-- Seed pollster roster
INSERT OR IGNORE INTO pollsters (slug, name_zh, name_en, bias, status, cadence, notes) VALUES
    ('nccu_esc',  '國立政治大學選舉研究中心', 'NCCU Election Study Center',       'academic',      'active',     'biannual', 'Identity + unification trend since 1992'),
    ('myformosa', '美麗島電子報',             'My-Formosa',                       'green_leaning', 'active',     'monthly',  'Best of the active regulars'),
    ('tvbs',      'TVBS民調中心',             'TVBS Poll Center',                 'blue',          'active',     'monthly',  NULL),
    ('ettoday',   'ETtoday民調雲',            'ETtoday Survey Cloud',             'centrist',      'active',     'monthly',  NULL),
    ('tpof',      '台灣民意基金會',           'Taiwan Public Opinion Foundation', 'green_leaning', 'historical', NULL,       'Chair moved to head TW CEC; no new polls expected'),
    -- MAC is a TW executive-branch ministry, not party media — bias=state_official is symmetric
    -- with how PRC state outlets are labelled. The chip colour in PollsTab is side-aware
    -- (TW state → DPP green under current exec, PRC state → red) since state_official can
    -- attach to either side. Short forms (陸委會/陆委会) resolve via _MASTER_GLOSSARY in
    -- _resolve_pollster_id without needing an aliases column.
    ('mac',       '大陸委員會',               'Mainland Affairs Council',         'state_official','active',     'quarterly', 'TW executive branch; cross-strait attitudes survey 民眾對當前兩岸關係之看法'),
    ('unknown',   '未識別',                   'Unknown',                          'centrist',      'unknown',    NULL,       'Fallback for AI extractions where pollster could not be identified — analyst sets during approval');

-- Seed canonical question keys for the three hero series
INSERT OR IGNORE INTO poll_questions (question_key, question_text_zh, question_text_en, family, scale_type, description) VALUES
    ('identity_nccu_3pt',    '請問您認為自己是台灣人、中國人，或者都是？',     'Do you consider yourself Taiwanese, Chinese, or both?',                'identity',    'choice',             'NCCU ESC flagship since 1992'),
    ('unification_nccu_6pt', '請問您認為台灣和大陸的關係應該是什麼？',         'What should the relationship between Taiwan and mainland China be?',   'unification', 'six_point',          'NCCU ESC 6-point scale: unification now / status quo→union / status quo / status quo→indep / indep now / no opinion'),
    ('approval_lai_overall', '請問您對賴清德總統的整體表現滿意還是不滿意？',   'Are you satisfied with President Lai Ching-te overall performance?',   'approval',    'approve_disapprove', 'Multi-pollster monthly approval tracker');