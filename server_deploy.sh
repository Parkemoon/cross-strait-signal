#!/usr/bin/env bash
# Runs on the server. Called by the local deploy.sh via SSH.
set -e

cd /var/www/cross-strait-signal

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

echo "--- Pulling latest code ---"
git pull

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
