---
paths:
  - "frontend/src/**"
  - "frontend/public/**"
  - "frontend/package.json"
---

# Frontend

React 19 + Recharts + Tailwind CSS 4. State management lives in `App.js`. All API calls use relative URLs (`API_BASE = ""`); dev server proxies `localhost:8000` via `"proxy"` in `package.json`.

## Central API client (`api.js`)

Every fetch in the frontend goes through a named function in `api.js`, not inline `fetch`. When adding a new API endpoint, add the corresponding function to `api.js` first; components import from it directly.

`fetchStats` only forwards keys in `SCOPING_KEYS` to the stats endpoint (`sentiment` and `search` are intentionally article-list-only). When adding a new scoping filter, add it to both `SCOPING_KEYS` here AND `_build_filter_clause` in `stats.py`.

## Read-only build (`readOnly.js`)

`READ_ONLY = process.env.REACT_APP_READ_ONLY === 'true'`. Import in any component with write controls to hide them in the public build. Build with `npm run build:public` (sets `BUILD_PATH=build-public`). Nginx also blocks POST/PATCH on the public server at the edge.

## Layout and view state (`App.js`)

- `view` state (`"feed"` | `"review"` | `"economy"` | `"trade"` | `"people"`) controls the center column on desktop. `"review"` → `<ReviewQueue />`; `"economy"` → `<EconomyTab />`; `"trade"` → `<TradeAccessTab />`; `"people"` → `<PeopleTab />`.
- The 3-column grid collapses to 2 columns (hides the Social Pulse right aside) when `view` is `"economy"`, `"trade"`, or `"people"`, so wide tables/charts get full width.
- Below 768px (`isMobile`, from `hooks/useWindowWidth.js`), everything collapses to a single column with a sticky top tab bar (`mobileTab` state). Each tab shows/hides its panel via `display: none`. Check `isMobile` when adding any fixed-width or multi-column structure.

## Sync points — keep these in lockstep when adding things

| Adding | Update |
|---|---|
| A scoping filter | `SCOPING_KEYS` (api.js) + `_build_filter_clause` (stats.py) + `hasScopingFilter`/`buildScopeLabel` (StatsSidebar) |
| A new source place | API filter block in `articles.py`; never hardcode beyond PRC / TW / hk / intl in `FilterBar` |
| A multi-feed publication | `PUBLICATION_NAMES` (StatsSidebar source grouping) + `SOURCE_FILTER` (click-to-filter prefix map) + `SOURCE_ABBREV` (SourceBadge) |
| A TW-vs-PRC pair on Economy tab | `MACRO_PAIRS` in `EconomyTab.jsx` (set `dualAxis: true` when scales differ ≥5×) |
| A verification reporter pair | `VERIFICATION_PAIRS` (economy.py) + `VERIFICATION_KINDS` (EconomyTab.jsx) for subsection styling |
| A new industry that misses bar colour | Widen the `INDUSTRY_SECTOR` token list in EconomyTab.jsx or accept grey "Other" |
| A new trade-access direction or status | `DIRECTIONS` / `STATUS_FILTERS` / `STATUS_PILLS` in TradeAccessTab.jsx |
| A new economic indicator | `SERIES_META` in `api/routes/economy.py` with a `category` field — picker auto-discovers via `data.series` (except `category='macro'`, which is filtered out and goes through MacroSection instead) |
| A new metric for `cross_strait_population` | Update the seed script or scraper to produce the metric; `PeopleTab.jsx` pulls a small fixed set of metrics (latest residence permit, census, spouse stock, 台胞证 holders) so add a KPI card and/or chart for new metrics that should be surfaced |

## Component-specific notes

- **`StatsSidebar.jsx`**: dashboard gauges sorted PRC → TW → HK/Macao → International. Taiwan camp gauges (`green` / `green_leaning` / `blue`) hidden below n=5 articles to avoid noise. When a scoping filter is active, a teal chip appears above "Strait Watch" with a dismissable `×`; each gauge shows a grey ghost dot at the global baseline position (only when scoped score differs by >0.01). `TopicBreakdownChart` hides when `filters.topic` is set. All sidebar elements are clickable to set filters: gauges → `onPlaceClick(placeKey|null)`, camp gauges → `onBiasClick(bias)`, source rows → `onSourceClick(dbPrefix)` using `SOURCE_FILTER` map, entity rows → `onEntityClick(entityNameEn)`. Renders `EconomyMini` between the topic breakdown and Sources sections.
- **`ArticleCard.jsx`**: inline sentiment/topic override + analyst notes. `onSignalOff` prop for FlashTraffic removal; `onApprove` callback for pending count updates. Unapproved articles (`analyst_approved=0`) show an amber left border and Approve/Dismiss banner (admin only). `FieldEditor` handles inline editing of the three `*_override` columns — pencil icon reveals textarea; overridden fields render in amber. `sentiment_reasoning` renders as a small italic grey line below the sentiment badge (admin only, hidden when empty).
- **`ReviewQueue.js`**: human review UI with translation editing fields (headline, summary, key quote) always visible — changed fields saved via `updateArticleTranslation` before resolving. Confirm/override auto-approves the article.
- **`SignalCharts.jsx`**: sentiment trend (Y-axis clamped to `[-1, 1]`, single YAxis) + topic breakdown.
- **`EconomyTab.jsx`**: KPI strip (4 cards), main trade chart with 1Y/3Y/5Y/All range toggle, indicator picker (macro filtered out — has its own section), `MacroSection` for TW-vs-PRC side-by-side line charts driven by `MACRO_PAIRS`, `VerificationSection` rendering one subsection per `kind` returned by `/api/economy/verification` (styling per kind in `VERIFICATION_KINDS`), `InvestmentSection` (default direction `tw_to_prc` — the dominant flow). Verification charts always show last 60 months regardless of main-chart range (PRC data lags ~6 months). Investment bars colour-coded by `INDUSTRY_SECTOR` via `classifySector(zh)`; `formatInvestmentAmount` adapts K/M/B (outbound is ~50× inbound). Also exports `EconomyMini` — sidebar widget showing TW–PRC trade balance + total trade headline.
- **`PeopleTab.jsx`**: own top-level tab as of 2026-05-23 (was a section inside EconomyTab). KPI strip (4 cards), bidirectional 2-column grid (collapses to 1 column under ~680px via `grid-template-columns: repeat(auto-fit, minmax(340px, 1fr))`): LEFT = PRC-in-TW (grouped bar chart of annual residence + settlement permits); RIGHT = TW-in-PRC (milestone cards + vertical policy timeline). Flow strip = paired monthly visitor flows (TW→PRC dark vs PRC→TW teal) — shows ALL available periods rather than slicing to last 60, because MAC only publishes TW outbound from 2024-03 and slicing made the line look like it cliffed. Closing methodology blurb explains why the two sides are asymmetric (1992 籍貫 cutoff + no 出生地 publish, see [[tw-birthplace-data-unavailable]]). Reads `/api/economy/people-records`. Local `formatLargeNumber` deliberately keeps 1 decimal at the 10M+ band (so 11.6M renders as "11.6M" not "12M") — the policy-timeline "12M+ targeted" wording is a different concept from cumulative holders and the two figures should be visibly different.
- **`TradeAccessTab.jsx`**: Headline strip framing the asymmetry, suspension wave timeline (per `summary.suspension_waves`), filter bar (direction toggle + status pills + debounced search), paginated table sorted by status severity. `STATUS_PILLS` colour scheme — `banned`=red, `ecfa_suspended`=amber, `conditional`=blue, `ecfa_active`=green — the contrast between directions IS the analytical point; don't soften it.
- **`FlashTraffic.jsx`**: priority signals section — renders full `ArticleCard` components, inverted colour scheme (`.signal-inverted` CSS class).
- **`SocialPulse.jsx`**: accepts `column` prop — in column mode (right-hand aside) always expanded, vertical stack layout; in default inline mode, collapsible with two-column Weibo/PTT panel. Weibo shows only cross-strait relevant items. Inline translation correction via pencil icon (hidden in read-only build). Override colour highlight is also hidden in read-only build.
- **`KeyFigures.jsx`**: horizontal scrollable row of cards above SocialPulse; each card shows portrait (images in `frontend/public/figures/`, initials fallback with party colour), name, role, latest approved statement; pencil icon (amber when candidates pending) opens per-card curation modal; hidden in read-only build.
- **`AboutModal.jsx`**: triggered from header (desktop) and mobile header "i" button; explains methodology, sentiment axis, source bias taxonomy, AI pipeline, author bio. Follows CSS variable conventions.
- **`SourceBadge.jsx`**: colour-coded by `bias` prop — `SOURCE_ABBREV` map covers all active sources; multi-feed publications collapse to a shared abbreviation (e.g. all CT sections → `CT`).
- **`FilterBar.jsx`**: topic / sentiment / source_place / bias / entity / escalation / search filters. Source place options: PRC / Taiwan / HK/Macao (`hk`) / International (`intl`).
- **`hooks/useWindowWidth.js`**: returns `window.innerWidth`, updates on resize. Used in `App.js` to derive `isMobile = windowWidth < 768`.
- **`ThemeToggle.jsx`** — light/dark theme switcher in the header. **`TopicPill.jsx`** — inline topic category label used in `ArticleCard`.

## Build env caveat

Never run `npm run build` (admin bundle) without sourcing `.env` — the admin bundle bakes in `REACT_APP_ADMIN_TOKEN` at build time. A plain `npm run build` ships an empty token; every write request then fails auth.

For iterating fast: `set -a && source .env && set +a && cd frontend && REACT_APP_ADMIN_TOKEN="$ADMIN_TOKEN" npm run build`. Otherwise use `bash server_deploy.sh` which handles env sourcing. The public build (`npm run build:public`) intentionally has no token and is safe to run without env.
