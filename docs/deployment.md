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
ADMIN_TOKEN=...                 # required for admin frontend build
```

Initialise the database and seed sources:

```bash
python scripts/init_db.py
python scripts/seed_sources.py
```

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
```

## Deploy workflow

```bash
# Local — commit, push, then SSH to server
git push
ssh root@<your-server>
cd /var/www/cross-strait-signal && ./server_deploy.sh
```

`server_deploy.sh` runs `git pull`, builds both frontend versions
(`npm run build` for admin, `npm run build:public` for public), and
restarts the service.

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
