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

# Apply versioned schema migrations (db/migrations/*, tracked in the
# schema_migrations table — see scripts/migrate.py). Replaces the old
# inline heredoc + error-swallowing ALTER pattern: real errors now fail
# the deploy loudly, a concurrent cron lock waits (30s busy_timeout)
# instead of silently skipping, and dated data-fix migrations run once.
echo "--- Applying schema migrations ---"
./venv/bin/python scripts/migrate.py

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
