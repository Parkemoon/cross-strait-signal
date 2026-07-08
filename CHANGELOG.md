# Changelog

Development history for Cross-Strait Signal. Items are grouped by
delivery state rather than version — the project ships continuously
to a single production deploy.

## Delivered

### Pipeline + classification

- Multi-source bilingual scraping (RSS + HTML)
- Directional keyword pre-filter (saves ~80% API costs)
- Three-tier AI analysis pipeline with human review queue
- Source bias taxonomy (green / green_leaning / centrist / blue_leaning / blue / state_official / state_nationalist)
- Sentiment audit trail (`sentiment_reasoning`) — one-sentence quoted evidence per non-neutral score
- Sentiment consistency validation — label/score band mismatches and unsupported directional claims auto-flagged to human review queue
- Wikidata-driven officials roster with auto-refresh script (`scripts/refresh_officials.py`) — ~28 positions across TW/US/PRC/JP, injected into every prompt
- Entity name merge CLI (`scripts/merge_entities.py` — fuzzy clustering, interactive merge)
- Editorial accuracy reporting (`scripts/accuracy_report.py`) — override rates + per-topic dismissal + reclassification target distribution

### Sources

- LTN (Politics, World, Business, Defence)
- CNA (Politics, Mainland, International, Finance)
- China Times sections via self-hosted RSSHub (chromium-bundled)
- UDN HTML scraper (Cross-Strait, Breaking, International, Business)
- YDN (ROC MND newspaper) — green_leaning under DPP executive
- Provincial PRC media (海峽導報, 解放軍報, 观察者网)
- HK sources — RTHK Greater China, Ming Pao (Cross-Strait, Editorial, Opinion)
- International Chinese-language sources — BBC Chinese, Zaobao
- Social media signal layer (Weibo hot search + PTT trending)

### Backend + frontend

- FastAPI backend with filtering and full-text search (FTS5)
- React 19 dashboard with dark/light theme
- Priority signals section and review queue UI
- Sentiment trend visualisation + topic breakdown chart
- Event clustering (Jaccard similarity, 48-hour window)
- Analyst commentary and classification override
- Inline translation editing (headline, summary, key quote) with amber override indicator
- Editorial approval gate — all articles held from public feed until analyst sign-off
- Filter-scoped Strait Watch sentiment gauges (scope chip, ghost baseline dots, entity/topic/place/urgency filtering)
- Key Figures panel with manual curation workflow (attributed quotes/actions, analyst approval)
- Public read-only dashboard (`strait-signal.net`) — write controls hidden at build time
- Admin dashboard (`admin.strait-signal.net`) behind HTTP basic auth
- Domain name + SSL (Cloudflare proxy)
- Mobile-responsive layout with tab navigation
- Automated scheduling (cron every 6 hours)
- VPS deployment (Ionos S+, Ubuntu 24.04)

### Structured data tabs

- **Economy tab** — TW-vs-PRC trade with multi-reporter verification (MAC + UN Comtrade + HK CSD direct); the reporter gap is the analytical signal
- **Investment-by-industry** — both directions, with industry colour-coding and the ~50× outbound asymmetry visible
- **Trade Access tab** — BOFT bans + ECFA active/suspended + MoF PRC suspension waves + curated PRC bans, plus the monthly CIFER snapshot scraper (Playwright)
- **People tab** — bidirectional cross-strait residency: TW NIA permits + spouse stock + curated PRC-side data (台胞证 / census / settler floor) — with the 1992 籍貫 cutoff documented inline
- **PLA Incursion tracker** — Taiwan MND daily 共軍動態 scraper + PLATracker historical CSV backfill (2020-09 → 2026-04); KPI strip, daily bars, six-sector ADIZ heatmap, custom Taiwan Strait SVG map
- **Exercise Tracker** — Leaflet map + list of cross-strait exercises and drills, AI-extracted from MIL_EXERCISE articles, with analyst review queue, canonical-key auto-merge, and edit modal
- **Poll tracker** — Taiwan domestic pollster ingestion (My-Formosa, ETtoday, TVBS, NCCU long series); cross-pollster trend charts per canonical question_key

### Hardening & fixes (2026-07-04, multi-agent code review)

Full remediation from a multi-agent review; work order + per-item status in `CODE_REVIEW_2026-07-03.md`.

- **Access control** — admin-only reads gated server-side via a new non-raising `is_admin` dependency: `include_pending`, single-article + cluster visibility (with real 404s, not 200+error bodies), and `GET /api/stats/key-figures/candidates` no longer leak unapproved rows to anonymous callers. Tokens compared with `hmac.compare_digest`.
- **Entity canonicalisation** — bare `中國`/`台灣` were resolving to "Kuomintang (KMT)"/"TPP" via prefix-collision; added exact canonical entries and back-filled **2,749** existing rows (`renormalise_entities.py --apply`).
- **Pipeline resilience** — transient Gemini errors (429/5xx/timeout) now retry next run instead of tombstoning articles as processed; explicit JSON-null guards; `run_pipeline.py` isolates each step so one bad source can't abort AI analysis + clustering.
- **Data integrity** — `cluster_events` no longer tears apart clusters straddling the 48h window edge; `published_at` window filters use `strftime` `T`-format (a `datetime('now')` string mis-compare was over-including ~a day); weekly digest sends before archiving (no false "emailed" rows); MND KPI leap-day 500 fixed; `schema.sql` re-synced (`review_reason`/`reviewed_at`).
- **Scrapers** — RSS content no longer clobbered by an untrimmed generic selector; PTT pagination walks all pages; YDN/UDN timestamps stored UTC-correct (were 8h off); trade-access `banned`-list crash + propylene HS code (2901.22).
- **Prompt / cost** — officials roster trimmed to static-current + article-matched-former (~14.5k→3.1k chars/call); `poll_only`/`exercise_only` dropped to `thinking_level=low`; Tier-2 escalation review skips the extraction arrays; poll example labels made canonical.
- **Performance / hygiene** — `entities(article_id)` index; removed committed scratch files, a dead route, and 6 dead `api.js` exports.

## In progress / planned

- Deferred code-review items (bigger/structural) tracked in `CODE_REVIEW_2026-07-03.md`: versioned migrations (§4.2), unified review-queue mechanism (§4.3), one entity-normalisation semantics (§4.6), shared scraper utils (§4.9), Tier-2 standalone lean prompt (§3.3 remainder). (Applied 2026-07-08 on staging: §3.1 scan markers, §3.5 Batch-API Tier 1, §3.7a shared prompt constants, §4.4/4.5/4.7/4.8/4.10, §5 stragglers, plus the diplomacy dedup/off-axis maintenance scripts.)
- Maps for geocoded entities (entity table already carries lat/lng schema fields)
- Incursion × exercise cross-reference — apply the verification angle to military data (do PLA spikes track MIL_EXERCISE / MIL_MOVEMENT article volume?)
- Monthly-aggregated sentiment endpoint (revisit when 12+ months of data exists)
- Audit trail for AI classifications — `topic_primary_ai_original` column or change log to unlock per-category accuracy measurement
- Override-propagation race fix — optimistic concurrency control on the notes/review write paths, or frontend dirty-tracking on the override dropdowns
- ADS-B / AIS data integration (Phase 3)
