# Architecture

Full technical reference for Cross-Strait Signal — pipeline diagram,
tech stack, complete topic taxonomy, granular source list, API
surface, and dashboard features. The README has the methodology
summary; this is the deep version.

## Data flow

```
Sources (PRC + Taiwan + HK + Singapore + UK, Chinese-language priority)
├── RSS scraper (Xinhua, People's Daily, China News Service, Global Times, The Paper,
│               CNA sections, LTN sections, CT sections via RSSHub,
│               RTHK Greater China, Ming Pao sections, Zaobao, BBC Chinese)
├── HTML scrapers (TAO, MFA, Guancha, Haixia Daobao, PLA Daily, YDN,
│                 LTN Defence, UDN sections)
├── Social scrapers (Weibo hot search JSON API, PTT BBS boards)
│
Keyword Pre-filter (directional — no API calls on irrelevant articles)
├── PRC/HK/SG sources: must mention Taiwan/ROC territory to proceed
├── TW sources: must mention PRC/mainland/HK/Macau to proceed
│
Three-Tier AI Analysis Pipeline (articles only)
├── Tier 1: Gemini 3.1 Flash Lite — topic, sentiment, entities, urgency
│           (submitted via the Gemini Batch API by default — ~half the
│           token price; collected same tick when the job finishes in
│           the wait window, else next tick)
│           + side-extract: key figure statements (pending), military
│             exercise candidates from MIL_EXERCISE articles (pending),
│             third-country diplomatic stances on Taiwan (pending →
│             diplomacy_statements → Diplomacy tab; intl orgs excluded,
│             EU bloc kept), poll questions from TW poll-bearing
│             articles (pending)
├── Tier 2: Gemini 3.5 Flash — escalation review for flagged articles
├── Tier 3: Human review queue — model disagreement resolution
│            (translation editing + auto-approve on resolution)
│
Secondary extraction passes (keyword-filter rejects — no ai_analysis row,
nothing enters the article feed)
├── Exercise-only pass — YDN military articles the filter rejected →
│   Tier 1 exercise extraction only → military_exercises review queue
├── Poll-only pass — TW-side rejects whose title carries 民調/民意調查 →
│   stripped poll-only prompt → polls review queue
├── MAC poll PDFs — deterministic pdfplumber parse of 配布表 tables →
│   polls + poll_results as approved (no AI, config-driven question keys)
└── Poll-label canonicaliser — idempotent per-tick drift-catcher collapsing
    option-label variants to canonical strings
│
Glossary injection (pre-analysis): glossary.json terms injected as CRITICAL TERMINOLOGY MAPPING
Officials roster injection (pre-analysis): current_officials.json (~28 roles, TW/US/PRC/JP) injected as authoritative reference; prevents officeholder hallucinations from stale training data
Entity canonical normalisation (post-analysis): entity_canonical.json normalises extracted name_en fields
Sentiment consistency check (post-extraction): flags label/score band mismatches and directional claims with no quoted evidence to the human review queue
│
Editorial Approval Gate
└── All articles held from public feed until analyst explicitly approves
│
Parallel Data Pipelines (no AI analysis — feed dedicated tables and tabs)
├── Social Pulse — Gemini 3.1 Flash Lite batch-translates Weibo / PTT titles
├── Economic Indicators — MAC 7887 (TW trade), UN Comtrade (PRC Customs),
│   MAC 7459 (TW-HK dual reporter), MAC 7888 (TW-vs-PRC macro), HK CSD direct
│   → /api/economy/*  (verification dimension: same flow, different reporters)
├── Investment by Industry — MAC 7478 (PRC→TW) + MAC 7473 (TW→PRC)
│   → /api/economy/investment-by-industry
├── Trade Access — BOFT bans, ECFA correspondence, MoF suspension waves,
│   curated PRC bans, monthly CIFER snapshot (Playwright)
│   → /api/trade-access/*
├── Cross-Strait Population — TW NIA permits + curated PRC-side data
│   → /api/economy/people-records
└── PLA Incursions — Taiwan MND daily 共軍動態 briefing (sectors, vessels,
    coast-guard) + one-shot PLATracker CSV backfill (ADIZ-entry count only,
    2020-09 → 2026-04) → /api/military/incursions, /api/military/zones

Event clustering — related articles grouped within a 48-hour window by
Jaccard similarity on title keywords (threshold 0.25)

Storage: SQLite with full-text search (FTS5); versioned schema migrations
(db/migrations/ + scripts/migrate.py, applied on every deploy)
```

## Tech stack

| Layer | Technology |
|-------|------------|
| Backend API | FastAPI (Python) |
| Database | SQLite with FTS5, versioned migrations |
| AI Pipeline | Google Gemini 3.1 Flash Lite (Tier 1, via Batch API by default) + Gemini 3.5 Flash (Tier 2 / poll extraction) |
| Model audit | OpenRouter (alt-model comparison sweeps — admin experiment, never feeds the editorial pipeline) |
| Scraping | feedparser, BeautifulSoup, httpx, Playwright (CIFER + pollster sites), pdfplumber (MAC poll PDFs) |
| Frontend | React 19, Recharts, react-leaflet |
| RSS proxy | RSSHub (self-hosted Docker, chromium-bundled) |
| Web server | Nginx (reverse proxy + static serving) |
| Process manager | systemd |
| Hosting | Ionos VPS S+, Ubuntu 24.04 |

## Topic taxonomy (full)

| Code | Description |
|------|-------------|
| `MIL_EXERCISE` | PLA drills, live-fire exercises, joint exercises near Taiwan |
| `MIL_MOVEMENT` | Troop deployments, naval transits, ADIZ incursions |
| `MIL_HARDWARE` | Weapons systems, procurement, specific platform news |
| `MIL_POLICY` | Defence budgets, doctrine, white papers, conscription, MND statements |
| `DIP_STATEMENT` | MFA remarks, TAO statements, official warnings |
| `DIP_VISIT` | Leader travel, delegation visits, ally engagement (state-level) |
| `DIP_SANCTIONS` | Trade restrictions, entity listings, diplomatic downgrades |
| `PARTY_VISIT` | KMT/opposition visits to PRC (distinct from state-level DIP_VISIT) |
| `ARMS_SALES` | US or third-party arms transfers, export licence decisions, delivery milestones |
| `ECON_TRADE` | Cross-strait trade, supply chain, ECFA |
| `ECON_INVEST` | FDI flows, business restrictions, tech sector |
| `ENERGY` | Energy security — LNG, nuclear policy, shipping lane economics, infrastructure vulnerability |
| `SCI_TECH` | Science and technology — semiconductors, chip supply chains, export controls as tech policy, AI competition, scientific exchanges |
| `POL_DOMESTIC_TW` | Taiwan elections, party dynamics, domestic politics (subject = Taiwan) |
| `POL_DOMESTIC_PRC` | PRC internal politics, leadership, domestic governance |
| `POL_TONGDU` | 統獨 spectrum — unification/independence dynamics (bidirectional) |
| `INFO_WARFARE` | Disinformation, cognitive warfare, narrative manipulation |
| `CYBER` | Cyber operations, hacking, digital espionage, infrastructure intrusions |
| `LEGAL_GREY` | Coast guard activity, sand dredging, cable incidents |
| `HUMANITARIAN` | People-to-people exchange, humanitarian issues |
| `TRANSPORT` | Cross-strait transport links, aviation, shipping |
| `INT_ORG` | Taiwan's participation in international organisations |
| `US_PRC` | US-China relations as primary subject — Washington-Beijing diplomacy, tech/trade sanctions |
| `US_TAIWAN` | US-Taiwan relations — political support, congressional legislation, US officials |
| `HK_MAC` | Hong Kong and Macao with cross-strait relevance — "one country, two systems" credibility |
| `CULTURE` | Cross-strait cultural exchange and soft power |
| `SPORT` | Sporting events with cross-strait political dimensions |
| `NOT_RELEVANT` | Article does not meet cross-strait relevance threshold |

`POL_TONGDU` (統獨) rather than `POL_UNIFICATION` — the bidirectional
framing reflects that both independence moves and unification
rhetoric shift the status quo.

## Sentiment axis (with score bands)

| Score | Label | Meaning |
|-------|-------|---------|
| −1.0 to −0.3 | Hostile | Article frames the other side negatively — threatening, antagonistic, confrontational |
| −0.3 to +0.3 | Neutral | Factual reporting without strong positive or negative framing of the other side |
| +0.3 to +1.0 | Cooperative | Warm, engaging framing — shared identity, dialogue, trade, people-to-people ties |

Sentiment measures **how the source frames the opposing side of the
strait**, not geopolitical stability. The axis is **bidirectional**
— a PRC outlet publishing a hostile piece about Lai Ching-te and a
Taiwan outlet publishing a hostile piece about PLA exercises both
score negative. Taiwan-US military cooperation does not score as
cross-strait cooperative.

A Taiwanese politician opposing formal Taiwan independence scores
**neutral** — a mainstream within-Taiwan position with no consensus
against it, not a cross-strait stance. A PRC official invoking
anti-independence language to deny ROC sovereignty scores **hostile**
— it asserts framing over Taiwan's right to choose. Every non-neutral
score is accompanied by a one-sentence `sentiment_reasoning` field
quoting the specific phrase that drove the classification.

## Source list (granular)

### Taiwan

| Source | Bias | Method |
|--------|------|--------|
| LTN Politics (自由時報政治) | green | RSS |
| LTN World (自由時報國際) | green | RSS |
| LTN Business (自由時報財經) | green | RSS |
| LTN Defence (自由軍武頻道) | green | HTML scraper |
| CNA Politics (中央社政治) | green_leaning | RSS |
| CNA Mainland (中央社兩岸) | green_leaning | RSS |
| CNA International (中央社國際) | green_leaning | RSS |
| CNA Finance (中央社財經) | green_leaning | RSS |
| CT Cross-Strait (中時兩岸) | blue | RSS (RSSHub) |
| CT Politics (中時政治) | blue | RSS (RSSHub) |
| CT Military (中時軍事) | blue | RSS (RSSHub) |
| CT Opinion (中時言論) | blue | RSS (RSSHub) |
| UDN Cross-Strait (聯合報兩岸) | blue | HTML scraper |
| UDN Breaking (聯合報要聞) | blue | HTML scraper |
| UDN International (聯合報全球) | blue | HTML scraper |
| UDN Business (聯合報産経) | blue | HTML scraper |
| YDN (青年日報) | green_leaning | HTML scraper |

### PRC

| Source | Bias | Method |
|--------|------|--------|
| Xinhua Chinese (新华社) | state_official | RSS |
| People's Daily Politics (人民日报台湾) | state_official | RSS (RSSHub) |
| China News Service (中国新闻网) | state_official | RSS |
| Global Times (环球时报台海) | state_nationalist | RSS (RSSHub) |
| The Paper (澎湃新聞) | state_official | RSS (RSSHub) |
| PRC MFA Spokesperson (外交部发言人) | state_official | HTML scraper |
| Taiwan Affairs Office (国台办) | state_official | HTML scraper |
| China Taiwan Net (中国台湾网) | state_official | HTML scraper |
| Guancha (观察者网) | state_nationalist | HTML scraper |
| Haixia Daobao (海峽導報) | state_official | HTML scraper |
| PLA Daily (解放軍報) | state_official | HTML scraper |

### Hong Kong

| Source | Bias | Method |
|--------|------|--------|
| RTHK Greater China (香港電台大灣區) | state_official | RSS |
| Ming Pao Cross-Strait (明報兩岸) | china_centrist | RSS |
| Ming Pao Editorial (明報社評) | china_centrist | RSS |
| Ming Pao Opinion (明報觀點) | china_centrist | RSS |

### International

| Source | Bias | Method |
|--------|------|--------|
| Zaobao Cross-Strait (联合早报中港台) | centrist | RSS (RSSHub) |
| BBC Chinese (BBC中文) | centrist | RSS |

### Social (not in article pipeline)

| Source | Method |
|--------|--------|
| Weibo Hot Search (微博热搜) | JSON API |
| PTT Military / Gossiping / HatePolitics | HTML scraper |

### Pollster-direct scrapers (feed the poll tracker, not the article feed)

| Source | Bias | Method |
|--------|------|--------|
| My-Formosa (美麗島電子報) | centrist | Playwright |
| TVBS Poll Center (TVBS民調中心) | blue | Playwright (PDF releases) |
| ETtoday Polls (ETtoday民調雲) | blue_leaning | Playwright |
| MAC 即時民調 (structured 配布表 PDFs) | state_official (TW exec) | pdfplumber, no AI |

### Removed

- **Guangming Daily (光明日報)** — anyfeeder proxy dead, rarely cross-strait relevant.

## API surface

Full Swagger UI at `/docs` when the backend is running. Selected
endpoints below.

```
Articles & analysis
├── GET    /api/articles                — filtered feed; ?include_pending=true for admin
├── GET    /api/articles/{id}           — single article with full details
├── POST   /api/articles/{id}/approve   — mark article analyst-approved
└── PATCH  /api/articles/{id}/translation — override headline, summary, key quote

Stats & key figures
├── GET    /api/stats                   — dashboard summary, scoped aggregations + global baselines
│                                         (admin: ?alt_model=&alt_arm= re-aggregates from an alt-model sweep)
├── GET    /api/stats/entities          — entity leaderboard
├── GET    /api/stats/key-figures(/candidates)
├── POST   /api/stats/key-figures/statements/{id}/approve  (and /dismiss)
└── POST   /api/notes                   — analyst commentary

Social
├── GET    /api/social/                 — Weibo top 50 + PTT trending
└── PATCH  /api/social/{id}/translation — analyst translation correction

Economy & people
├── GET    /api/economy/series(/meta)   — time-series + indicator catalog
├── GET    /api/economy/verification    — paired reporter gaps (3 kinds)
├── GET    /api/economy/investment-by-industry?direction=…
└── GET    /api/economy/people-records  — bidirectional residency + flows

Trade access
├── GET    /api/trade-access/items?direction=…&status=…
├── GET    /api/trade-access/summary    — asymmetry counts + suspension waves
└── GET    /api/trade-access/cifer-snapshot — monthly Playwright snapshot

Military
├── GET    /api/military/incursions(/monthly|/summary)
├── GET    /api/military/zones          — ADIZ sector heatmap
├── GET    /api/military/exercises(/summary)        — approved exercises
├── GET    /api/military/exercises/candidates       — admin: pending queue
├── POST   /api/military/exercises/{id}/(approve|dismiss|merge)
└── PATCH  /api/military/exercises/{id}             — analyst edit

Polls
├── GET    /api/polls/                  — recent approved waves, paginated
├── GET    /api/polls/by-question/{question_key} — cross-pollster trend series
├── GET    /api/polls/roster            — pollster list with approved counts
├── GET    /api/polls/topics            — question families grouped
├── GET    /api/polls/candidates        — admin: pending queue with pending JSON
├── POST   /api/polls/{id}/(approve|dismiss|merge)
└── POST   /api/polls/                  — manual entry fallback

Diplomacy (third-country stance on the Taiwan question)
├── GET    /api/diplomacy/map           — choropleth payload: official-tier aggregate fill per
│                                         country + non-official "voices" pins + divergence flag
├── GET    /api/diplomacy/summary       — KPI strip (countries tracked, band histogram, divergent count)
├── GET    /api/diplomacy/statements    — windowed statement list (country / tier / side filters)
├── GET    /api/diplomacy/candidates    — admin: pending queue grouped by country
├── POST   /api/diplomacy/{id}/(approve|dismiss|merge)
└── PATCH  /api/diplomacy/{id}          — analyst edit (stance re-clamped, label recomputed)

Positions & alt-model experiment
├── GET    /api/positions/              — curated Positions & Legal Status reference content
├── GET    /api/alt-models/summary      — admin: per-(model, arm) sweep aggregates vs production
├── GET    /api/alt-models/article/{id} — admin: per-article alt-model rows
└── GET    /api/alt-models/refusals     — admin: refusal browser

Review
├── GET    /review/queue                — articles pending human review
├── POST   /review/{id}/resolve         — confirm / override / dismiss
└── GET    /review/stats                — pending/resolved + pending_approval
```

## Dashboard features

```
React Dashboard
├── Signal Feed — filterable article list with event clustering; filter by PRC / Taiwan / HK/Macao / International
├── Priority Signals (flash/priority urgency articles)
├── Key Figures panel (10 curated officials, portraits, latest approved statement, curation modal)
├── Social Pulse column (Weibo cross-strait items + PTT trending, persistent right-hand column)
├── Strait Watch gauges (overall + PRC / TW / HK/Macao / International + by political camp)
├── Sentiment trend chart and topic breakdown chart (Recharts)
├── Inline editorial overrides (sentiment, topic, score on any article card)
├── Inline translation editing (headline, summary, key quote — amber highlight on override)
├── Editorial approval gate (pending articles shown with amber border + approve/dismiss buttons)
├── Analyst commentary per article
├── Review Queue (human review UI with translation editing + confirm/override/dismiss)
├── Economy tab (TW-vs-PRC indicators, verification panels, investment by industry)
├── Trade Access tab (asymmetry headline, suspension waves, status-coloured table)
├── People tab (bidirectional residency, policy timeline, paired visitor flows)
├── Military tab (PLA incursion KPIs + ADIZ heatmap + Strait map; Exercise Tracker with Leaflet map, list, analyst review queue, edit modal)
├── Polls tab (three flagship trend strips + two-tier question selector + review queue,
│   manual entry, per-chart party-colour assignment)
├── Diplomacy tab (world choropleth of third-country stance — official fill + non-official
│   voices pins, divergence highlighting, per-country drill-in, review queue)
├── Stat Spotlight (rotating sidebar card cycling one headline figure per top-level section)
├── Positions tab (curated cross-strait positions reference — admin-gated until content review completes)
├── Alt Models tab + feed model lens (admin only — the model-audit experiment: aggregate
│   agreement cards, refusal browser, and a Gemini / DeepSeek / Both feed view with
│   lensed sidebar stats)
└── Dark/light theme toggle
```

## Design principles

- **Chinese-language sources are primary.** English versions of Chinese outlets break stories later and with less analytical depth.
- **Bias labels reflect editorial reality, not diplomatic hedging.** CNA is `green_leaning` (state-controlled under DPP), not centrist. UDN is `blue` (consistent editorial line), not merely blue-leaning.
- **The sentiment axis is bidirectional.** Destabilising actions from either side register on the same scale.
- **POL_TONGDU not POL_UNIFICATION.** The 統獨 spectrum runs in both directions.
- **Human judgment overrides AI.** The review queue, inline overrides, and translation editing exist because AI classification and translation of politically sensitive content requires editorial judgment.
- **Every article requires analyst approval.** Nothing reaches the public dashboard without explicit sign-off. AI-flagged articles are additionally routed through the review queue before approval.

## Model strategy

The pipeline uses Google Gemini 3.1 Flash Lite as the default
processing engine (cost-effective, strong Chinese-language
performance) with Gemini 3.5 Flash for escalation review on flagged
articles and for poll-question extraction (denser parsing task,
longer outputs).

DeepSeek was passed over early on after content-dropping was observed
in translation testing via its first-party endpoint. That early call
was **superseded by a systematic audit in mid-2026**: the entire
approved corpus (13,000+ articles) re-run through DeepSeek V4 Flash —
plus a stratified Kimi K3 sample — on Western-hosted endpoints with
the byte-identical production prompt, against a same-model Gemini
rerun as the noise-floor control. Result: zero refusals, no
sovereignty-selective avoidance, no romanisation or title-dropping
tells, and summary omission of sensitive entities at the control's
noise floor. The measured differences are analytic (a stricter
relevance gate, taxonomy boundary disputes), not political filtering.
Gemini remains the production engine on quality and operational
grounds; the audit lives in
[`ALT_MODEL_EXPERIMENT_WRITEUP.md`](../ALT_MODEL_EXPERIMENT_WRITEUP.md)
and stays comparable over time via a daily incremental sweep
(admin-only Alt Models tab + feed model lens).
