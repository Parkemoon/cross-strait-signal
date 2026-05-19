# Staging Environment

Staging worktree: `/var/www/cross-strait-signal-staging` (branch: `staging`)
Production worktree: `/var/www/cross-strait-signal` (branch: `main`)

## Starting the staging servers

Open a tmux session on the server:

```bash
tmux new -s staging
```

Pane 1 — API on port 8001:
```bash
cd /var/www/cross-strait-signal-staging
source venv/bin/activate
uvicorn api.main:app --host 127.0.0.1 --port 8001 --reload
```

Split the pane (`Ctrl-b %`), Pane 2 — React dev server on port 3001:
```bash
cd /var/www/cross-strait-signal-staging/frontend
env -u HOST PORT=3001 npm start
```
Note: `HOST` must be explicitly unset — if it's set to an empty string in the shell environment (common on this server), webpack-dev-server will reject it with an `allowedHosts` error. The dev server binds to `0.0.0.0:3001` but is only reachable via the SSH tunnel.

## Accessing staging from your local machine

SSH tunnel (run this locally, keep the terminal open):
```bash
ssh -L 3001:127.0.0.1:3001 -L 8001:127.0.0.1:8001 root@<server-ip>
```

Then open: http://localhost:3001

## Refreshing the database snapshot

When you want to test against fresh prod data:
```bash
cp /var/www/cross-strait-signal/db/cross_strait_signal.db \
   /var/www/cross-strait-signal-staging/db/cross_strait_signal.db
```

## Pipeline in staging

The pipeline (scraper + AI) is intentionally **not scheduled** in staging.
Check `crontab -l` to confirm — only the prod entry (`0 6,18 * * *`) should appear.
To run the pipeline manually in staging if needed:
```bash
cd /var/www/cross-strait-signal-staging
source venv/bin/activate
python scripts/run_pipeline.py
```

## Merging staging work to production

When a phase is reviewed and approved in staging:
```bash
# Back in the production worktree
cd /var/www/cross-strait-signal
git merge staging
./deploy.sh
```
