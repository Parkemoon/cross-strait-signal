#!/usr/bin/env bash
# Runs on the server. Called by the local deploy.sh via SSH.
set -e

cd /var/www/cross-strait-signal

# Pull then re-exec self so the rest of the script runs from the freshly
# pulled file on disk — bash's read-ahead behaviour when the script file
# changes mid-execution is implementation-defined, and a deploy that
# adds a new schema migration block has to actually execute that block.
# The DEPLOY_POST_PULL sentinel prevents the re-exec from looping.
if [ -z "${DEPLOY_POST_PULL:-}" ]; then
    echo "--- Pulling latest code ---"
    git pull
    DEPLOY_POST_PULL=1 exec bash "$0" "$@"
fi

# Load server secrets (.env) so subsequent steps — notably the admin frontend
# build — can read them. The set -a / set +a brackets export every variable
# the .env defines. The admin build inlines REACT_APP_* vars into the JS
# bundle, so ADMIN_TOKEN must be present at build time, not just at runtime.
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# Apply idempotent schema additions. init_db.py runs the full schema.sql,
# which contains non-idempotent CREATE TABLEs from the original layout (would
# fail on an existing DB), so we apply just the new objects inline. Each new
# table or index added in a feature branch should be appended here AND added
# to db/schema.sql (with IF NOT EXISTS) for fresh-init parity.
echo "--- Applying idempotent schema additions ---"
sqlite3 db/cross_strait_signal.db <<'SQL'
CREATE TABLE IF NOT EXISTS economic_indicators (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id   TEXT NOT NULL,
    period      TEXT NOT NULL,
    period_type TEXT NOT NULL,
    value       REAL,
    unit        TEXT NOT NULL,
    yoy_pct     REAL,
    source      TEXT NOT NULL,
    source_url  TEXT,
    scraped_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(series_id, period, period_type)
);
CREATE INDEX IF NOT EXISTS idx_econ_series_period ON economic_indicators(series_id, period DESC);
CREATE INDEX IF NOT EXISTS idx_econ_period_type ON economic_indicators(period_type, period DESC);

-- Trade access (Phase 2a.2) — cross-strait import permission regime.
-- One row per (direction, hs_code). See db/schema.sql for full column docs.
CREATE TABLE IF NOT EXISTS trade_access (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    direction             TEXT NOT NULL,
    hs_code               TEXT NOT NULL,
    product_zh            TEXT,
    product_en            TEXT,
    status                TEXT NOT NULL,
    effective_date        TEXT,
    source                TEXT NOT NULL,
    notes                 TEXT,
    ban_announcement_url  TEXT,
    scraped_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(direction, hs_code)
);
CREATE INDEX IF NOT EXISTS idx_trade_access_direction_status ON trade_access(direction, status);
CREATE INDEX IF NOT EXISTS idx_trade_access_hs ON trade_access(hs_code);

-- Cross-strait investment by industry (Phase 2a.2) — MAC 7478 + 7473.
-- Cumulative monthly snapshots in both directions; see db/schema.sql for
-- direction values and unit normalisation notes.
CREATE TABLE IF NOT EXISTS investment_by_industry (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    direction         TEXT NOT NULL,
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

-- CIFER snapshots (Phase 2a.2) — monthly count from PRC's CIFER portal.
CREATE TABLE IF NOT EXISTS cifer_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    status        TEXT NOT NULL,
    status_zh     TEXT,
    count         INTEGER NOT NULL,
    notes         TEXT,
    scraped_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(snapshot_date, status)
);
CREATE INDEX IF NOT EXISTS idx_cifer_snapshots_date ON cifer_snapshots(snapshot_date DESC);

-- Cross-strait population (Phase 2a.2) — residents in the other side.
CREATE TABLE IF NOT EXISTS cross_strait_population (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    direction   TEXT NOT NULL,
    metric      TEXT NOT NULL,
    period      TEXT NOT NULL,
    period_type TEXT NOT NULL,
    value       REAL,
    unit        TEXT NOT NULL,
    source      TEXT NOT NULL,
    source_url  TEXT,
    notes       TEXT,
    scraped_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(direction, metric, period, period_type)
);
CREATE INDEX IF NOT EXISTS idx_csp_direction_metric ON cross_strait_population(direction, metric, period DESC);

-- PLA incursions (Phase 2b) — daily MND counts of PLA aircraft/vessel activity.
CREATE TABLE IF NOT EXISTS pla_incursions (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    date                     TEXT NOT NULL,
    aircraft_total           INTEGER,
    aircraft_intruded        INTEGER,
    aircraft_zones           TEXT,
    vessels_total            INTEGER,
    coast_guard_total        INTEGER,
    source                   TEXT NOT NULL,
    source_url               TEXT,
    raw_text                 TEXT,
    scraped_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, source)
);
CREATE INDEX IF NOT EXISTS idx_pla_incursions_date ON pla_incursions(date DESC);

-- Military exercises (Phase 2b.2) — AI-extracted exercise tracker with
-- editorial approval gate. See db/schema.sql for full column docs.
CREATE TABLE IF NOT EXISTS military_exercises (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id        INTEGER NOT NULL REFERENCES articles(id),
    canonical_name    TEXT,
    name_en           TEXT,
    name_zh           TEXT,
    name_raw          TEXT,
    performer         TEXT NOT NULL,
    participants_json TEXT,
    exercise_kind     TEXT,
    start_date        TEXT,
    end_date          TEXT,
    location_label    TEXT,
    latitude          REAL,
    longitude         REAL,
    description_en    TEXT,
    description_zh    TEXT,
    confidence        REAL,
    approval_status   TEXT NOT NULL DEFAULT 'pending',
    merged_into_id    INTEGER REFERENCES military_exercises(id),
    reviewed_at       TIMESTAMP,
    reviewed_by       TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_milex_status_date ON military_exercises(approval_status, start_date DESC);
CREATE INDEX IF NOT EXISTS idx_milex_canonical  ON military_exercises(canonical_name, approval_status);
CREATE INDEX IF NOT EXISTS idx_milex_article    ON military_exercises(article_id);
CREATE INDEX IF NOT EXISTS idx_milex_performer  ON military_exercises(performer, start_date DESC);

-- Polls (Phase 2d) — TW polling tracker.
-- See db/schema.sql for full column docs and canonical-merge rationale.
CREATE TABLE IF NOT EXISTS pollsters (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    slug         TEXT NOT NULL UNIQUE,
    name_zh      TEXT NOT NULL,
    name_en      TEXT NOT NULL,
    bias         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active',
    cadence      TEXT,
    methodology  TEXT,
    notes        TEXT,
    homepage_url TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pollsters_status ON pollsters(status);

CREATE TABLE IF NOT EXISTS poll_questions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    question_key     TEXT NOT NULL UNIQUE,
    question_text_zh TEXT NOT NULL,
    question_text_en TEXT NOT NULL,
    family           TEXT NOT NULL,
    scale_type       TEXT NOT NULL,
    description      TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_poll_questions_family ON poll_questions(family);

CREATE TABLE IF NOT EXISTS polls (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    pollster_id          INTEGER NOT NULL REFERENCES pollsters(id),
    fielded_start        TEXT NOT NULL,
    fielded_end          TEXT,
    sample_size          INTEGER,
    methodology_note     TEXT,
    source_url           TEXT,
    source_article_id    INTEGER REFERENCES articles(id),
    notes                TEXT,
    confidence           REAL,
    approval_status      TEXT NOT NULL DEFAULT 'pending',
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
    option_order    INTEGER,
    percentage      REAL NOT NULL,
    margin_error    REAL,
    UNIQUE(poll_id, question_id, option_order)
);
CREATE INDEX IF NOT EXISTS idx_poll_results_poll ON poll_results(poll_id);
CREATE INDEX IF NOT EXISTS idx_poll_results_question ON poll_results(question_id);

-- Analyst-assigned party/colour identity for poll options (keyed by canonical
-- option_label_zh). party → palette in frontend partyColours.js; colour_override
-- ('#RRGGBB') wins. Person→party for the key_figures roster resolves at query
-- time in polls.py, so only party-name labels + off-roster candidates need rows.
CREATE TABLE IF NOT EXISTS poll_option_parties (
    option_label_zh TEXT PRIMARY KEY,
    party           TEXT,
    colour_override TEXT,
    updated_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_by      TEXT
);
INSERT OR IGNORE INTO poll_option_parties (option_label_zh, party, updated_by) VALUES
    ('民主進步黨', 'DPP',  'seed'), ('民進黨', 'DPP', 'seed'),
    ('中國國民黨', 'KMT',  'seed'), ('國民黨', 'KMT', 'seed'),
    ('台灣民眾黨', 'TPP',  'seed'), ('民眾黨', 'TPP', 'seed'),
    ('時代力量',   'NPP',  'seed'),
    ('台灣基進',   'TSP',  'seed'),
    ('台灣綠黨',   'GPT',  'seed'), ('綠黨', 'GPT', 'seed'),
    ('新黨',       'NP',   'seed'),
    ('親民黨',     'PFP',  'seed'),
    ('中華統一促進黨', 'CUPP', 'seed'), ('統促黨', 'CUPP', 'seed');

INSERT OR IGNORE INTO pollsters (slug, name_zh, name_en, bias, status, cadence, notes) VALUES
    ('nccu_esc',  '國立政治大學選舉研究中心', 'NCCU Election Study Center',       'academic',      'active',     'biannual', 'Identity + unification trend since 1992'),
    ('myformosa', '美麗島電子報',             'My-Formosa',                       'centrist',      'active',     'monthly',  'Owner expelled from DPP for being too critical; editorial posture no longer green-leaning'),
    ('tvbs',      'TVBS民調中心',             'TVBS Poll Center',                 'blue',          'active',     'monthly',  NULL),
    ('ettoday',   'ETtoday民調雲',            'ETtoday Survey Cloud',             'blue_leaning',  'active',     'monthly',  NULL),
    ('tpof',      '台灣民意基金會',           'Taiwan Public Opinion Foundation', 'green_leaning', 'historical', NULL,       'Chair moved to head TW CEC; no new polls expected'),
    ('mac',       '大陸委員會',               'Mainland Affairs Council',         'state_official','active',     'quarterly', 'TW executive branch; cross-strait attitudes survey 民眾對當前兩岸關係之看法'),
    ('unknown',   '未識別',                   'Unknown',                          'centrist',      'unknown',    NULL,       'Fallback for AI extractions where pollster could not be identified — analyst sets during approval');

-- Bias correction (2026-05-26): INSERT OR IGNORE above won't update existing
-- rows, so apply the updated calls directly. Idempotent — re-running just
-- sets the same value again.
UPDATE pollsters SET bias='centrist',     notes='Owner expelled from DPP for being too critical; editorial posture no longer green-leaning' WHERE slug='myformosa';
UPDATE pollsters SET bias='blue_leaning'                                                                                                     WHERE slug='ettoday';

INSERT OR IGNORE INTO poll_questions (question_key, question_text_zh, question_text_en, family, scale_type, description) VALUES
    ('identity_nccu_3pt',    '請問您認為自己是台灣人、中國人，或者都是？',     'Do you consider yourself Taiwanese, Chinese, or both?',                'identity',    'choice',             'NCCU ESC flagship since 1992'),
    ('unification_nccu_6pt', '請問您認為台灣和大陸的關係應該是什麼？',         'What should the relationship between Taiwan and mainland China be?',   'unification', 'six_point',          'NCCU ESC 6-point scale: unification now / status quo→union / status quo / status quo→indep / indep now / no opinion'),
    ('approval_lai_overall', '請問您對賴清德總統的整體表現滿意還是不滿意？',   'Are you satisfied with President Lai Ching-te overall performance?',   'approval',    'approve_disapprove', 'Multi-pollster monthly approval tracker');

-- Diplomacy Tracker (Phase 2c) — third-country stance on Taiwan / cross-strait.
-- See db/schema.sql for full column semantics. Editorial-gate pattern.
CREATE TABLE IF NOT EXISTS diplomacy_statements (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id        INTEGER NOT NULL REFERENCES articles(id),
    country_iso       TEXT NOT NULL,
    country_name      TEXT,
    speaker           TEXT,
    authority_tier    TEXT NOT NULL,
    stance            REAL NOT NULL,
    stance_label      TEXT,
    statement_en      TEXT,
    statement_zh      TEXT,
    stated_date       TEXT,
    source_side       TEXT,
    confidence        REAL,
    approval_status   TEXT NOT NULL DEFAULT 'pending',
    merged_into_id    INTEGER REFERENCES diplomacy_statements(id),
    reviewed_at       TIMESTAMP,
    reviewed_by       TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_diplo_status_date ON diplomacy_statements(approval_status, stated_date DESC);
CREATE INDEX IF NOT EXISTS idx_diplo_country     ON diplomacy_statements(country_iso, approval_status);
CREATE INDEX IF NOT EXISTS idx_diplo_article     ON diplomacy_statements(article_id);
CREATE INDEX IF NOT EXISTS idx_diplo_tier        ON diplomacy_statements(authority_tier, approval_status);

-- FTS5 sync triggers. The articles_fts virtual table existed without triggers,
-- so historical inserts never made it into the index. The /api/articles search
-- now hits articles_fts directly. After applying these triggers, run
-- scripts/rebuild_fts.py once to backfill the existing 55k+ rows; future
-- inserts/updates/deletes flow through automatically.
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
SQL

# Idempotent ALTER for DBs where polls was created before pending_results_json
# was added (i.e. between commits 78bc88f and this one). SQLite has no
# `ADD COLUMN IF NOT EXISTS`, so swallow the duplicate-column error and
# carry on. Safe on freshly-initialised DBs too — CREATE TABLE above
# already includes the column, so this ALTER simply fails-and-skips.
sqlite3 db/cross_strait_signal.db \
    "ALTER TABLE polls ADD COLUMN pending_results_json TEXT" \
    2>/dev/null || true

# Idempotent ALTER for pollsters.place — added so `state_official` chips can
# side-disambiguate (TW exec ministries get DPP green, PRC state outlets get
# red). Defaults to 'TW' since every pollster in the seed roster is TW-side;
# explicit place='PRC' on future PRC-state pollster inserts.
sqlite3 db/cross_strait_signal.db \
    "ALTER TABLE pollsters ADD COLUMN place TEXT NOT NULL DEFAULT 'TW'" \
    2>/dev/null || true

echo "--- Building frontend (admin) ---"
cd frontend
# Pass ADMIN_TOKEN through to the admin bundle so write endpoints can be
# called from the admin UI. The public build below intentionally omits it.
REACT_APP_ADMIN_TOKEN="${ADMIN_TOKEN:-}" npm run build

echo "--- Building frontend (public read-only) ---"
npm run build:public
cd ..

echo "--- Restarting backend ---"
systemctl restart cross-strait-signal

echo "--- Done ---"
