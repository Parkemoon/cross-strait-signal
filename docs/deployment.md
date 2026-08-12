# Deployment

Setup, infrastructure, and operational notes. The README has the
methodology and feature summary; this is the developer doc.

## Local setup

```bash
git clone https://github.com/Parkemoon/cross-strait-signal.git
cd cross-strait-signal
python -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
GEMINI_API_KEY=your_gemini_key_here
ADMIN_TOKEN=...                 # required for admin frontend build; gates write
                                # endpoints AND admin-only reads server-side
```

Optional extras (all degrade gracefully when unset):

```
GEMINI_TIER1_MODE=interactive   # Tier 1 defaults to the Gemini Batch API;
                                # this restores the sequential per-article path
TIER1_BATCH_WAIT_MIN=20         # same-tick batch collection window (0 = always next tick)
OPENROUTER_API_KEY=...          # alt-model comparison sweeps only
SMTP_HOST=... SMTP_PORT=587     # weekly digest + health/report emails
SMTP_USER=... SMTP_PASS=...
DIGEST_TO=...                   # digest + alt-model report recipient
HEALTH_TO=...                   # scraper-health alerts (falls back to DIGEST_TO)
```

Initialise the database and seed sources:

```bash
python scripts/init_db.py       # fresh install — creates the full schema from db/schema.sql
python scripts/seed_sources.py
```

Existing databases are upgraded by versioned migrations instead:
ordered files in `db/migrations/` tracked in a `schema_migrations`
ledger, applied by `python scripts/migrate.py` (run automatically on
every server deploy). New schema always lands as a numbered migration
file AND mirrored into `db/schema.sql` for fresh-init parity.

Run the full pipeline (scrape + analyse):

```bash
python scripts/run_pipeline.py
```

Start the API server and React dashboard (two terminals):

```bash
# Terminal 1 — API
python -m uvicorn api.main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm install
npm start
```

API docs at `http://localhost:8000/docs`. Dashboard at
`http://localhost:3000`.

### Windows note

The project venv at `venv/` may be near-empty on Windows. Use
`/c/Users/Ed/venv/Scripts/python.exe` instead. Add
`sys.stdout.reconfigure(encoding='utf-8', errors='replace')` at the
top of any script that prints Chinese text.

## RSSHub

Several sources (People's Daily, Global Times, The Paper, Zaobao,
RTHK, China Times sections) are fetched via a self-hosted RSSHub
instance. Run it as a Docker container with Chromium bundled
(required for China Times):

```bash
docker run -d --name rsshub --restart always -p 1200:1200 \
  diygod/rsshub:chromium-bundled
```

The `chromium-bundled` tag is required — the China Times sections
render via Puppeteer and 503 without it. Note that the chinatimes
route currently needs a local patch inside the container (upstream
RSSHub serves the generic realtime feed for every CT section and
503s on category pages); the patch is lost if the image is re-pulled
— details in `.claude/rules/deployment.md`.

## Server setup

```bash
cd /var/www
git clone https://github.com/Parkemoon/cross-strait-signal.git
cd cross-strait-signal
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
python scripts/init_db.py
python scripts/seed_sources.py
```

## systemd service

```ini
# /etc/systemd/system/cross-strait-signal.service
[Unit]
Description=Cross-Strait Signal API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/var/www/cross-strait-signal
Environment=PATH=/var/www/cross-strait-signal/venv/bin
ExecStart=/var/www/cross-strait-signal/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Nginx config

Two server blocks — one per domain, both proxying to the same
FastAPI backend.

**Public** (`/etc/nginx/sites-available/cross-strait-signal-public`):

```nginx
server {
    listen 80;
    server_name strait-signal.net www.strait-signal.net;

    root /var/www/cross-strait-signal/frontend/build-public;
    index index.html;

    location / { try_files $uri $uri/ /index.html; }

    location /api/ {
        limit_except GET { deny all; }
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Admin** (`/etc/nginx/sites-available/cross-strait-signal-admin`):

```nginx
server {
    listen 80;
    server_name admin.strait-signal.net;

    auth_basic "Cross-Strait Signal";
    auth_basic_user_file /etc/nginx/.htpasswd;

    root /var/www/cross-strait-signal/frontend/build;
    index index.html;

    location / { try_files $uri $uri/ /index.html; }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /review/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
}
```

## Cron schedule

```bash
# Main pipeline runs every 6 hours
0 */6 * * * cd /var/www/cross-strait-signal && /var/www/cross-strait-signal/venv/bin/python scripts/run_pipeline.py >> /var/log/cross-strait-pipeline.log 2>&1

# CIFER snapshot (Playwright, monthly — not in main pipeline because of the
# headless Chromium launch cost)
0 3 1 * * cd /var/www/cross-strait-signal && /var/www/cross-strait-signal/venv/bin/python -m scraper.scrapers.cifer_snapshot_scraper >> /var/log/cifer-snapshot.log 2>&1

# Weekly editorial digest email (Mon 08:00)
0 8 * * 1 cd /var/www/cross-strait-signal && venv/bin/python scripts/weekly_digest.py >> /var/log/cross-strait-digest.log 2>&1

# Scraper staleness monitor (daily 08:15 — emails on state changes only)
15 8 * * * cd /var/www/cross-strait-signal && venv/bin/python scripts/check_scraper_health.py >> /var/log/scraper-health.log 2>&1

# Alt-model experiment: daily full-window incremental v4f sweep (04:00,
# probe-guarded, self-heals transient provider failures; full-corpus window
# so no approved article ever ages out unswept)
0 4 * * * cd /var/www/cross-strait-signal && venv/bin/python scripts/sweep_alt_models.py --model deepseek/deepseek-v4-flash --arm neutral --probe && venv/bin/python scripts/sweep_alt_models.py --model deepseek/deepseek-v4-flash --arm neutral --retry-errors --days 3650 --limit 1000 >> /var/log/cross-strait-v4f-sweep.log 2>&1

# Alt-model monthly review email (1st 08:30 — live aggregates vs frozen write-up)
30 8 1 * * cd /var/www/cross-strait-signal && venv/bin/python scripts/alt_model_monthly_report.py >> /var/log/alt-model-report.log 2>&1
```

## Deploy workflow

```bash
# Local — commit, push, then SSH to server
git push
ssh root@<your-server>
cd /var/www/cross-strait-signal && ./server_deploy.sh
```

`server_deploy.sh` runs `git pull`, applies pending schema migrations
via `scripts/migrate.py`, builds both frontend versions
(`npm run build` for admin, `npm run build:public` for public), and
restarts the service. After deploying changes to `seed_sources.py`,
also run `python scripts/seed_sources.py` on the server.

## Frontend builds

```bash
cd frontend
npm install
npm run build          # admin bundle (requires .env with ADMIN_TOKEN sourced)
npm run build:public   # public read-only bundle (no token, safe to run plain)
npm test
```

The two bundles serve different domains: `strait-signal.net` gets
the public build (write controls hidden at compile time);
`admin.strait-signal.net` gets the admin build behind HTTP basic
auth.
