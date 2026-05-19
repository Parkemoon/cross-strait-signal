#!/usr/bin/env bash
# Runs on the server. Called by the local deploy.sh via SSH.
set -e

cd /var/www/cross-strait-signal

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
SQL

echo "--- Building frontend (admin) ---"
cd frontend
npm run build

echo "--- Building frontend (public read-only) ---"
npm run build:public
cd ..

echo "--- Restarting backend ---"
systemctl restart cross-strait-signal

echo "--- Done ---"
