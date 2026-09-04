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
- Weekly digest runs Mondays 08:00 (`0 8 * * 1`), logging to `/var/log/cross-strait-digest.log`.
- LinkedIn post proposer runs Tuesdays and Thursdays 07:00 **Europe/London** (installed 2026-09-04): `0 6,7 * * 2,4 [ "$(TZ=Europe/London date +\%H)" = 07 ] && cd /var/www/cross-strait-signal && [ -f scripts/propose_linkedin_post.py ] && venv/bin/python scripts/propose_linkedin_post.py >> /var/log/cross-strait-linkedin.log 2>&1`. The server clock is UTC and Ubuntu's vixie cron has no `CRON_TZ`, so both UTC hours fire and the London-hour test keeps exactly one across the BST/GMT switch; the `-f` test keeps it silent until the script is deployed. Sends nothing when no cluster qualifies; recipient `LINKEDIN_TO`, falling back to `DIGEST_TO`; the SMTP env is the digest's. Migration 0011 creates `linkedin_drafts` on deploy.
- Scraper health monitor runs daily 08:15 (`15 8 * * *`), logging to `/var/log/scraper-health.log`. Emails on staleness state changes only (state in `/var/log/scraper-health-state.json`); see `scripts/check_scraper_health.py` for per-source thresholds.
- Alt-model crons (installed 2026-08-07 with the alt-model-UI deploy):
  - Daily v4f incremental sweep, 04:00: `0 4 * * * cd /var/www/cross-strait-signal && venv/bin/python scripts/sweep_alt_models.py --model deepseek/deepseek-v4-flash --arm neutral --probe && venv/bin/python scripts/sweep_alt_models.py --model deepseek/deepseek-v4-flash --arm neutral --retry-errors --days 3650 --limit 1000 >> /var/log/cross-strait-v4f-sweep.log 2>&1`. Full-window (`--days 3650`) so nothing ever ages out unswept: was weekly with `--days 10 --limit 400` until 2026-08-12, which risked losing articles for good whenever a heavy approval week overflowed the cap and the miss slid past the 10-day window (Ed: lens coverage of the corpus must stay complete). The 1000 cap is a runaway guard, not a quota — an overflow carries to the next night. The `--probe` guard makes an OpenRouter account/data-policy breakage fail loudly before the sweep; `--retry-errors` makes transient provider failures self-heal; if the sweep goes stale anyway, `check_scraper_health.py`'s `alt_model:v4f_sweep` check (5-day threshold — sweep rows only land when new approvals exist, so it tolerates a few review-free days) emails once on the state change. The neutral arm's provider whitelist (6 Western hosts, DeepInfra order-preferred) lives in `scraper/utils/openrouter.py` `ARMS` — widened 2026-08-07 after a DeepInfra-only capacity outage; it's the reliability lever if 429s recur.
  - Alt-model monthly review email, 1st 08:30: `30 8 1 * * cd /var/www/cross-strait-signal && venv/bin/python scripts/alt_model_monthly_report.py >> /var/log/alt-model-report.log 2>&1` — live aggregates vs the frozen write-up table (see the script docstring for the review procedure).

## After deploying source changes

After deploying changes to `seed_sources.py`, always run `python scripts/seed_sources.py` on the server to apply source additions/deactivations.

## RSSHub

Several sources use a self-hosted RSSHub instance on the server (`http://localhost:1200`) — People's Daily, Global Times, The Paper, Zaobao, RTHK Greater China, and all CT sections. It runs as a Docker container:

```bash
docker run -d --name rsshub --restart always -p 1200:1200 diygod/rsshub:chromium-bundled
```

The `chromium-bundled` tag is required — CT sections use Puppeteer to render chinatimes.com and will return 503 without it. If these feeds return 0 entries, check `docker ps` to confirm the container is running. rsshub.app (the public instance) blocks automated clients — always use localhost.

**The chinatimes route is locally patched inside the container** (2026-07-21). Upstream RSSHub (still broken on master) has two bugs: (a) `const { category = 'realtimenews' } = ctx.req.param('category')` object-destructures a string, so the category is always ignored and every section serves the generic 即時新聞 feed — this silently fed the realtime firehose into CT Cross-Strait for 3 months and starved the other three CT sections to zero via dedup; (b) category pages use absolute hrefs which the route double-prefixes with the base URL (503). Both are patched in the container's built file `/app/dist/chinatimes-CoSBu9wp.mjs` (original at `.bak` alongside). **The patch survives container restarts but is LOST if the image is re-pulled or the container recreated** — after any `docker pull`/`docker run`, re-check `curl localhost:1200/chinatimes/politic` returns a 政治-titled feed, not 即時新聞, and re-apply if not (see SESSION_LOG 2026-07-21 for the patch strings).

**The zaobao route is also locally patched inside the container** (2026-08-16). Zaobao restructured ~2026-07-29 (`/realtime/china` redirects to `zaobao.com.sg/news/china`; article pages gained a second `ld+json` script; `#seo-article-page` removed), which 503'd the route for 18 days (clean outage — no DB fallout). Patched in `/app/dist/util-CTsi-oV3.mjs` (original at `.bak` alongside) by porting the upstream fix: select only the `NewsArticle` ld+json tag, reuse its parsed JSON in place of `#seo-article-page`, and read `image[0].url`. **Unlike chinatimes, this fix IS on upstream master** — a re-pulled image fixes zaobao natively but still loses the chinatimes patch. Health test: `curl localhost:1200/zaobao/realtime/china` returns 200 with a 《联合早报》-中港台-即时 feed.

## Read-only build

`src/readOnly.js` exports `READ_ONLY = process.env.REACT_APP_READ_ONLY === 'true'`. The public build runs `npm run build:public` which sets `REACT_APP_READ_ONLY=true` and `BUILD_PATH=build-public`. Nginx also blocks POST/PATCH on the public server at the edge.

The admin build (`npm run build`) bakes in `REACT_APP_ADMIN_TOKEN` at build time. Never run it without sourcing `.env` first — see `frontend/.claude/rules` (frontend.md) for the env-sourcing pattern.

## Coast Guard tracker — deploy-time data steps (2026-08-26)

Migrations 0008/0009 create the tables but ship them EMPTY. After a first deploy to a fresh DB, from the target worktree (its venv + its `.env` for `GFW_API_TOKEN`): `scripts/backfill_cga_enforcement.py` (seconds) → `scripts/refresh_coast_guard_roster.py` (minutes; runs the deterministic triage at the end) → `scripts/backfill_coast_guard.py --start 2020-01-01` **detached** (`setsid nohup`, ~880 pulls / ~5 h, log `/var/log/coast-guard-backfill-prod.log`, resumable — periods logged `ok` in `coast_guard_pulls` are skipped). Roster BEFORE presence: the presence pull widens its GFW flag filter from the roster's spoofed-MID hulls. Nightly pipeline Steps 2n/2o keep both series current afterwards; `check_scraper_health.py` carries `coast_guard:gfw_pull` (3 d), `coast_guard:presence` (12 d) and `cga_enforcement:monthly` checks. Prod backfill launched 2026-08-26 09:20 UTC.

## Hand-edited JSON content that the admin UI rewrites

`scraper/processors/positions.json` and `data/site_copy.json` are committed files that the running API rewrites in place on admin edits (`JsonFileStore`). Consequence: edits made on prod dirty the PROD tree. Before any content change on staging, copy prod's file over staging's and commit both together; `server_deploy.sh`'s `git pull` will refuse to run over a dirty prod tree, so check `git -C /var/www/cross-strait-signal status` first.

