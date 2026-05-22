---
paths:
  - "deploy.sh"
  - "server_deploy.sh"
  - "scripts/init_db.py"
  - "scripts/seed_sources.py"
  - "db/schema.sql"
---

# Deployment

## Two-script deploy pattern

- **`deploy.sh`** (local): builds frontend, git push, SSHs to server to run `server_deploy.sh`.
- **`server_deploy.sh`** (server only): `git pull`, applies idempotent schema additions inline via `sqlite3`, `npm run build` (admin), `npm run build:public` (public read-only), `systemctl restart cross-strait-signal`.

## Schema migrations

`init_db.py` runs the full `schema.sql` and would fail on an existing DB because original tables don't use `IF NOT EXISTS`. When adding new tables or indexes:

1. Append a `CREATE … IF NOT EXISTS` block to the inline migration in `server_deploy.sh`.
2. Add the same statement to `db/schema.sql` (with `IF NOT EXISTS`) so fresh init still works.

## Live URLs

- Public: `strait-signal.net` (read-only)
- Admin: `admin.strait-signal.net` (password-protected, admin build)

Server path: `/var/www/cross-strait-signal`. Service name: `cross-strait-signal`. Staging worktree at `/var/www/cross-strait-signal-staging` (branch `staging`).

## Cron schedule

- Pipeline runs every 6h (`0 */6 * * *`), logging to `/var/log/cross-strait-pipeline.log`.
- CIFER snapshot scraper runs monthly (`0 3 1 * *`), logging to `/var/log/cifer-snapshot.log`.

## After deploying source changes

After deploying changes to `seed_sources.py`, always run `python scripts/seed_sources.py` on the server to apply source additions/deactivations.

## RSSHub

Several sources use a self-hosted RSSHub instance on the server (`http://localhost:1200`) — People's Daily, Global Times, The Paper, Zaobao, RTHK Greater China, and all CT sections. It runs as a Docker container:

```bash
docker run -d --name rsshub --restart always -p 1200:1200 diygod/rsshub:chromium-bundled
```

The `chromium-bundled` tag is required — CT sections use Puppeteer to render chinatimes.com and will return 503 without it. If these feeds return 0 entries, check `docker ps` to confirm the container is running. rsshub.app (the public instance) blocks automated clients — always use localhost.

## Read-only build

`src/readOnly.js` exports `READ_ONLY = process.env.REACT_APP_READ_ONLY === 'true'`. The public build runs `npm run build:public` which sets `REACT_APP_READ_ONLY=true` and `BUILD_PATH=build-public`. Nginx also blocks POST/PATCH on the public server at the edge.

The admin build (`npm run build`) bakes in `REACT_APP_ADMIN_TOKEN` at build time. Never run it without sourcing `.env` first — see `frontend/.claude/rules` (frontend.md) for the env-sourcing pattern.
