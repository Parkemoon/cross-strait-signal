# Staging Environment

Staging worktree: `/var/www/cross-strait-signal-staging` (branch: `staging`)
Production worktree: `/var/www/cross-strait-signal` (branch: `main`)

## Current state

See `CHANGELOG.md` (*Delivered* / *In progress*) and the gitignored
`SESSION_LOG.md` for the live history — this file only documents the staging
mechanics. As of 2026-09-01 the Morning Brief frontend redesign (phase 1) is
deployed to prod; staging and prod are at the same commit.

## How staging serves

- **API**: uvicorn on `127.0.0.1:8001` (plain process, not a systemd unit).
  If it's down: `cd /var/www/cross-strait-signal-staging && source venv/bin/activate
  && uvicorn api.main:app --host 127.0.0.1 --port 8001` (background it or use tmux).
- **UI**: nginx serves the BUILT admin bundle at `127.0.0.1:8082`
  (`/etc/nginx/sites-available/cross-strait-staging-local` — root
  `frontend/build`, proxies `/api/` to :8001). Rebuild after changes:
  source `.env`, then `REACT_APP_ADMIN_TOKEN="$ADMIN_TOKEN" npm run build`
  (see frontend.md for the env caveat). 8082 not 8081 — 8081 is taken on
  Ed's local machine. CRA dev-server on :3001 also works for hot-reload
  sessions (`frontend/.env.development` sets PORT/host-check).

## Accessing staging from your local machine

```bash
ssh -N -L 8082:127.0.0.1:8082 root@<server-ip>
```
Then open http://localhost:8082 (API is proxied — no second tunnel needed).

## Databases are SEPARATE and diverged

Staging and prod DBs have different row ids (including pollster ids) — do
NOT blindly copy prod's DB over staging's (that swap happened once,
2026-08-07→12, and had to be reverted). Target the prod DB from staging
scripts with their `--db /var/www/cross-strait-signal/db/cross_strait_signal.db`
flag instead. If a disposable prod snapshot is genuinely needed, copy it to a
DIFFERENT filename and point uvicorn/scripts at it explicitly.

## Pipeline in staging

The pipeline (scraper + AI) is intentionally **not scheduled** in staging —
cron runs it from the prod worktree only (`0 */6 * * *`). To run manually:
```bash
cd /var/www/cross-strait-signal-staging
source venv/bin/activate
python scripts/run_pipeline.py
```

## Merging staging work to production

When work is reviewed and approved in staging (this session runs ON the
server, so skip `deploy.sh`'s SSH hop):
```bash
cd /var/www/cross-strait-signal-staging && git push origin staging
cd /var/www/cross-strait-signal && git merge --ff-only staging && git push origin main
bash server_deploy.sh     # pull, migrations, both bundles, service restart
```
Major/structural changes go through staging first; bug fixes and small doc
edits can go straight to `main` (see CLAUDE.md).
