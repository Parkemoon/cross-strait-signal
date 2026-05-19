# Staging Environment

Staging worktree: `/var/www/cross-strait-signal-staging` (branch: `staging`)
Production worktree: `/var/www/cross-strait-signal` (branch: `main`)

## Current state

**Phase 1a + 1b** (`ce7b35e`): desktop 3-column layout with sticky
independently-scrolling columns; editorial design refresh (parchment palette,
thick-rule section headers, TopicPill flags, urgency stripes, masthead).

**Phase 2a**: Cross-strait economy tab with MAC + UN Comtrade verification.
Sources turned out to be `data.gov.tw` dataset 7887 (the original DGBAS API
plan was abandoned — geo-blocked + no public consumer API) plus UN Comtrade
preview API for PRC-side trade data. `economic_indicators` table populated
with ~9 years of monthly data; Economy tab includes KPI strip, main trade
chart, indicator picker, and a verification section overlaying MAC (TW
customs) vs PRC Customs figures — the gap is the analytical story.

**Next up — Phase 2a.2 (optional)**: more MAC datasets — 7472 (TW surplus
with PRC + HK, captures the HK transit story), 7478 (PRC investment in TW by
industry), 7888 (GDP/CPI/FX side-by-side). Then **Phase 2b**: MND incursion
tracker.

## Restarting staging (if the tmux session has died)

Check first — it may still be running:
```bash
tmux attach -t staging
```

If dead, restart both servers:

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
npm start
```
Note: `DANGEROUSLY_DISABLE_HOST_CHECK=true` and `PORT=3001` are set in
`frontend/.env.development` — no extra env flags needed. The dev server binds
to `0.0.0.0:3001` but is only reachable via SSH tunnel.

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
