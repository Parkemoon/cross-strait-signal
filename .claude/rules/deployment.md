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
- **`server_deploy.sh`** (server only): `git pull`, applies pending schema migrations via `scripts/migrate.py`, `npm run build` (admin), `npm run build:public` (public read-only), `systemctl restart cross-strait-signal`.

## Schema migrations

Versioned since 2026-07-08: ordered files in `db/migrations/` (`NNNN_name.sql`, or `NNNN_name.py` with `migrate(conn)` for ALTERs), tracked in the `schema_migrations` table, applied by `scripts/migrate.py` on every deploy. New schema = a new numbered migration file AND the same object mirrored into `db/schema.sql` for fresh-init parity. Real migration errors fail the deploy loudly; a concurrent cron lock waits (30s busy_timeout) instead of skipping. Full rules in `.claude/rules/database.md`.

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
