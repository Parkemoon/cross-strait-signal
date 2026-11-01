# Architecture

Full technical reference for Cross-Strait Signal: pipeline diagram,
tech stack, complete 24-category topic taxonomy, granular source list,
API surface, and dashboard features. The README has the methodology
summary; this is the deep reference.

## Data flow

```
Sources (PRC + Taiwan + HK + Singapore + UK, Chinese-language priority)
├── RSS scraper (Xinhua, People's Daily, China News Service, Global Times, The Paper,
│               CNA sections, LTN sections, RTHK Greater China, Ming Pao sections,
│               Zaobao, BBC Chinese)
├── HTML & browser scrapers (TAO, China Taiwan Net, MFA, Guancha, Haixia Daobao,
│                            PLA Daily, YDN, LTN Defence, UDN sections,
│                            CT sections via headful Chromium on Xvfb)
├── Social scrapers (Weibo hot search JSON API, PTT BBS boards)
│
Same-Outlet Deduplication (Step 2m — deterministic, before AI)
└── Hides same-source re-pushes and rewrites (identical content ≤7d, trigram Jaccard
    ≥0.90 ≤72h, or same-day exact title match) while preserving cross-outlet coverage
│
Keyword Pre-filter (directional — no API calls on irrelevant articles)
├── PRC/HK/SG sources: must mention Taiwan/ROC territory to proceed
├── TW sources: must mention PRC/mainland/HK/Macau to proceed
│
Three-Tier AI Analysis Pipeline (articles only)
├── Tier 1: Gemini 3.1 Flash Lite — 24-topic classification, sentiment, entities, urgency
│           (submitted via the Gemini Batch API by default at ~50% token price;
│           collected same tick when the job finishes in the wait window, else next tick)
│           + side-extract: key figure statements (pending), military
│             exercise candidates from MIL_EXERCISE articles (pending),
│             third-country diplomatic stances on Taiwan (pending →
│             diplomacy_statements → Diplomacy tab; intl orgs excluded,
│             EU bloc kept), poll questions from TW poll-bearing
│             articles (pending)
├── Tier 2: Gemini 3.8 Flash — blind escalation review for flagged articles
├── Tier 3: Human review queue — model disagreement and validation resolution
│            (translation editing + auto-approve on resolution)
│
Secondary Passes & Hygiene (Steps 2L, 3b–3g)
├── MAC poll PDFs (Step 2L) — deterministic pdfplumber parse of 配布表 tables →
│   polls + poll_results as approved (no AI, config-driven question keys)
├── Exercise-only pass (Step 3b) — YDN military articles the keyword filter rejected →
│   Tier 1 exercise extraction only → military_exercises review queue
├── Poll-only pass (Step 3c) — TW-side rejects whose title carries 民調/民意調查 →
│   stripped poll-only prompt → polls review queue
├── Poll-label canonicaliser (Step 3d) — idempotent per-tick drift-catcher collapsing
│   option-label variants to canonical strings
├── Cross-strait visits pass (Step 3e) — analysed DIP_VISIT / PARTY_VISIT articles →
│   visits-only extraction → cross_strait_visits (pending) → pre-queue trip dedup
├── Name lookup pass (Step 3f) — unresolved Taiwan-side person entities →
│   Wikidata SPARQL / grounded web search / Wade-Giles → name_registry queue
└── Queue rules (Step 3g) — deterministic dismissal of incomplete pending exercises
    (no start date, location, or name), incomplete polls (unknown pollster, no sample
    size, or no end date), and non-quote key-figure statements
│
Terminology & Validation Hooks
├── Glossary + Name Registry injection (pre-analysis): glossary.json + approved
│   name_registry rows injected as authoritative terminology mapping
├── Officials roster injection (pre-analysis): current_officials.json (~28 roles,
│   TW/US/PRC/JP) + per-article former-officials filter prevents stale-role attribution
├── Entity & prose normalisation (post-analysis): entity_canonical.json + approved
│   name_registry normalise extracted entity rows and rewrite prose renderings
└── Sentiment consistency + reported-speech check (post-extraction): flags label/score
    band mismatches, unquoted directional claims, and reported-speech axis inversions
│
Editorial Approval Gate
└── All articles and side-extracted rows held from public views until analyst approval
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
├── PLA Incursions — Taiwan MND daily 共軍動態 briefing (sectors, vessels,
│   coast-guard) + historical PLATracker CSV backfill (2020-09 → 2026-04)
│   → /api/military/incursions, /api/military/zones
└── Maritime & Coast Guard (Steps 2n, 2o, 2p) — GFW 4Wings coast-guard and civilian
    fleet AIS presence across 12 zones, GFW Sentinel-1 SAR dark-vessel radar detections,
    and Taiwan CGA monthly/annual enforcement PDFs → /api/military/coast-guard/*,
    /api/military/maritime/*

Event clustering (Step 4) — related articles grouped within a 48-hour window by
Jaccard similarity on title keywords (threshold 0.25) or TF-IDF cosine of the English
title + summary (≥0.15, with a 0.10 group-average guard), followed by cluster-consensus
topic_secondary backfill across multi-article clusters.

Storage: SQLite in WAL mode with full-text search (FTS5 unicode61 + Chinese trigram);
versioned schema migrations (db/migrations/ + scripts/migrate.py) applied on deploy.
```

## Tech stack

| Layer | Technology |
|-------|------------|
| Backend API | FastAPI (Python) |
| Database | SQLite (WAL mode) with FTS5 (Latin unicode61 + Chinese trigram), versioned migrations |
| AI Pipeline | Google Gemini 3.1 Flash Lite (Tier 1, via Batch API by default) + Gemini 3.8 Flash (Tier 2 / poll extraction) |
| Model audit | OpenRouter (DeepSeek V4.1 Flash + frozen V4 Flash / Kimi K3 baselines; admin experiment, never feeds editorial queues) |
| Scraping | feedparser, BeautifulSoup, httpx, Playwright (China Times headful Chromium on Xvfb, CIFER, pollster sites), pdfplumber (MAC poll and CGA enforcement PDFs) |
| Frontend | React 19, Recharts, react-leaflet, Tailwind CSS 4 |
| RSS proxy | RSSHub (self-hosted Docker) |
| Web server | Nginx (reverse proxy + static serving) |
| Process manager | systemd |
| Hosting | Ionos VPS S+, Ubuntu 24.04, nightly zstd backups to Cloudflare R2 |

## Topic taxonomy (24 categories + `NOT_RELEVANT`)

| Group | Code | Description |
|-------|------|-------------|
| **Military & Security** | `MIL_EXERCISE` | Named PLA or ROC drills, live-fire exercises, joint readiness patrols near Taiwan |
| **Military & Security** | `MIL_MOVEMENT` | Routine ADIZ sorties, median-line crossings, naval transits, surveillance patrols |
| **Military & Security** | `MIL_HARDWARE` | Specific weapons platforms, indigenous submarines (Hai Kun), carriers, missile systems |
| **Military & Security** | `MIL_POLICY` | Defence budgets, conscription, Han Kuang doctrine, MND/MOD posture and deterrence policy |
| **Military & Security** | `ARMS_SALES` | US or third-party weapons packages, FMS notifications, export licences, deliveries |
| **Military & Security** | `MARITIME_GREY` | Coast guard patrols (CCG/CGA), Kinmen/Matsu restricted waters, fishing boarding, dredging, undersea cables |
| **Military & Security** | `SEC_LAWFARE` | Espionage prosecutions, National Security Act / Anti-Infiltration cases, PRC secession bounties |
| **Military & Security** | `INFO_CYBER` | Hacking, APT intrusions, critical-infrastructure cyberattacks, state botnets, AI deepfakes, app data-security bans |
| **Cross-Strait & Sovereignty** | `POL_TONGDU` | 統獨 sovereignty rhetoric, One China / 1992 Consensus framing, Lai speeches, TAO/MAC ideological rebuttals |
| **Cross-Strait & Sovereignty** | `CROSS_STRAIT_REG` | Taiwan MAC/NIA administrative regulation of cross-strait people flows, 陸配 residency/household rules, civil-servant travel bans |
| **Cross-Strait & Sovereignty** | `CULTURE` | Cultural, religious (Mazu), youth, academic, media, entertainment, and sporting exchanges or naming disputes |
| **Cross-Strait & Sovereignty** | `UNITED_FRONT_INTEG` | PRC Fujian demonstration zone, incentives for Taiwanese residents/youth, mainland residence permits (台灣居民居住證) |
| **Cross-Strait & Sovereignty** | `PARTY_VISIT` | KMT, TPP, or non-ruling Taiwanese delegation visits to the mainland and Straits Forum attendance |
| **Diplomacy & Foreign** | `US_RELATIONS` | US-Taiwan and US-PRC political/strategic relations, Trump-Xi summits, Congressional Taiwan bills, AIT statements |
| **Diplomacy & Foreign** | `INTL_RELATIONS` | Non-US third-country parliamentary motions, G7/EU/Japan/Philippine statements on cross-strait stability, formal ROC allies |
| **Diplomacy & Foreign** | `DIP_VISIT` | Foreign parliamentary or official delegations visiting Taiwan, and Taiwanese officials travelling or transiting abroad |
| **Diplomacy & Foreign** | `INT_ORG` | Taiwan's participation or exclusion in WHA/WHO, ICAO, INTERPOL, CPTPP, APEC, and UN Resolution 2758 debates |
| **Diplomacy & Foreign** | `DIP_SANCTIONS` | Formal state sanctions, entity-list designations, travel bans, and diplomatic downgrades |
| **Domestic & HK** | `POL_DOMESTIC_TW` | Domestic Taiwanese elections, Legislative Yuan partisan battles, recalls, cabinet appointments, judicial cases |
| **Domestic & HK** | `POL_DOMESTIC_PRC` | PRC internal CCP governance, NPC/CPPCC sessions, economic management, and non-military purges |
| **Domestic & HK** | `HK_MAC` | Hong Kong and Macao national security trials, Article 23, media closures, and "One Country, Two Systems" credibility |
| **Economy, Tech & Links** | `ECON_TRADE` | Cross-strait and US-Taiwan trade, tariffs, ECFA suspensions, agricultural/food bans, supply-chain investment, energy security |
| **Economy, Tech & Links** | `SCI_TECH` | Semiconductors (TSMC), wafer fabs, AI R&D, chip export controls, space and biotechnology |
| **Economy, Tech & Links** | `TRANSPORT` | Direct flights, Mini-Three-Links (小三通) ferries, M503 flight routes, tourist group corridors, shipping lanes |
| **Gate** | `NOT_RELEVANT` | Article does not meet the cross-strait relevance threshold (filtered out of public views) |

## Sentiment axis (with score bands)

| Score | Label | Meaning |
|-------|-------|---------|
| −1.0 to −0.3 | Hostile | Article frames the other side negatively: threatening, antagonistic, confrontational |
| −0.3 to +0.3 | Neutral | Factual reporting without strong positive or negative framing of the other side |
| +0.3 to +1.0 | Cooperative | Warm, engaging framing: shared identity, dialogue, trade, people-to-people ties |

Sentiment measures **how the source frames the opposing side of the
strait**, not geopolitical stability. The axis is **bidirectional**:
a PRC outlet publishing a hostile piece about Lai Ching-te and a
Taiwan outlet publishing a hostile piece about PLA exercises both
score negative. Taiwan-US military cooperation does not score as
cross-strait cooperative.

A Taiwanese politician opposing formal Taiwan independence scores
**neutral** (a mainstream within-Taiwan position rather than a
cross-strait signal). A PRC official invoking anti-independence
language to deny ROC sovereignty scores **hostile**. Every
non-neutral score carries a one-sentence `sentiment_reasoning` field
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
| CT Cross-Strait (中時兩岸) | blue | HTML scraper (Chromium) |
| CT Politics (中時政治) | blue | HTML scraper (Chromium) |
| CT Military (中時軍事) | blue | HTML scraper (Chromium) |
| CT Opinion (中時言論) | blue | HTML scraper (Chromium) |
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
| RTHK Greater China (香港電台大灣區) | state_official | RSS (RSSHub) |
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

## API surface

Full Swagger UI at `/docs` when the backend is running. Selected
endpoints below.

```
Articles & analysis
├── GET    /api/articles/               — filtered feed; ?include_pending=true for admin
├── GET    /api/articles/{id}           — single article with full details
├── POST   /api/articles/{id}/approve   — mark article analyst-approved
└── PATCH  /api/articles/{id}/translation — override headline, summary, key quote

Stats & key figures
├── GET    /api/stats/                  — dashboard summary, scoped aggregations + global baselines
│                                         (admin: ?alt_model=&alt_arm= re-aggregates from an alt-model sweep)
├── GET    /api/stats/entities          — entity leaderboard
├── GET    /api/stats/key-figures(/candidates)
├── POST   /api/stats/key-figures/statements/{id}/approve  (and /dismiss)
└── POST   /api/notes                   — analyst commentary and topic/sentiment overrides

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

Military & Maritime
├── GET    /api/military/incursions(/monthly|/summary)
├── GET    /api/military/zones          — ADIZ sector heatmap
├── GET    /api/military/exercises(/summary|/candidates)
├── POST   /api/military/exercises/{id}/(approve|dismiss|merge)
├── PATCH  /api/military/exercises/{id}
├── GET    /api/military/coast-guard/(summary|monthly|daily|zones|vessels|enforcement)
├── PATCH  /api/military/coast-guard/vessels/{mmsi}
└── GET    /api/military/maritime/(summary|monthly|zones|civil/vessels)

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

Cross-Strait Visits
├── GET    /api/visits/                 — approved cross-strait visits with coverage counts
├── GET    /api/visits/monthly          — monthly stacked bars by direction
├── GET    /api/visits/summary          — 90-day KPI strip and frequent travellers
├── GET    /api/visits/{id}/coverage    — Taiwan vs PRC vs international coverage comparison
├── GET    /api/visits/candidates       — admin: pending visit queue
└── POST   /api/visits/{id}/(approve|dismiss|merge)

Positions, Site Copy, Name Registry & Alt-Model Experiment
├── GET    /api/positions/              — curated Positions & Legal Status reference content
├── PATCH  /api/positions/              — admin inline editing of reference text
├── GET    /api/copy/                   — editable site prose (42+ keys)
├── PATCH  /api/copy/{key}              — admin inline editing of site prose
├── GET    /api/names/(candidates|approved) — admin: Name Registry romanisation queue
├── POST   /api/names/{id}/(approve|reject)
├── GET    /api/alt-models/summary      — admin: per-(model, arm) sweep aggregates vs production
├── GET    /api/alt-models/article/{id} — admin: per-article alt-model rows
└── GET    /api/alt-models/refusals     — admin: refusal browser

Review
├── GET    /review/queue                — admin: articles pending human review
├── POST   /review/{id}/resolve         — confirm / override / dismiss
└── GET    /review/stats                — admin: pending/resolved + pending_approval
```

## Dashboard features

```
React Dashboard (grouped navigation: Feed · Security ▾ · Economy ▾ · Politics ▾ · Admin ▾ · About)
├── Signal Feed — twin-rail Morning Brief layout (stats rail | 820px article column | social rail)
│   with side-first outlet attribution, alignment wash, and event clustering
├── Top of the Brief (priority/flash signals grouped one lead card per topic)
├── Voices strip (10 curated key figures with portraits, Chinese titles, party colours, curation modal)
├── Social Pulse rail (Weibo cross-strait items + PTT trending)
├── Strait Watch hairline gauges (overall + PRC / TW / HK/Macao / International + by political camp)
├── Stat Spotlight (rotating sidebar card cycling one fresh headline figure per top-level section)
├── Sentiment trend chart and 24-category topic breakdown chart (Recharts)
├── Security ▾ Military — PLA incursion KPIs, ADIZ heatmap, Taiwan Strait map, Exercise Tracker
├── Security ▾ Maritime — Coast Guard AIS presence (GFW 4Wings) paired with Taiwan CGA enforcement
│   statistics, plus civilian fleet presence and Sentinel-1 SAR dark-vessel radar detections
├── Economy ▾ Indicators — TW-vs-PRC trade, multi-reporter verification panels, investment by industry
├── Economy ▾ Trade Access — regulatory asymmetry strip, suspension waves, searchable item register
├── Economy ▾ People — bidirectional residency permits, policy timeline, paired monthly visitor flows
├── Politics ▾ Polls — presidential approval composite, NCCU flagship trends, two-tier question browser
├── Politics ▾ Diplomacy — world choropleth of third-country stance, voices pins, country drill-in
├── Politics ▾ Visits — cross-strait delegation timeline, paired avatars, cross-side coverage comparison
├── Politics ▾ Positions — curated cross-strait positions and legal formulations dossier
├── Admin ▾ Review — Tier-3 human review queue with side-by-side Model Read vs Desk override
├── Admin ▾ Names — romanisation review queue for Taiwan-side person entities (name_registry)
├── Admin ▾ Alt Models + feed model lens — DeepSeek V4.1 Flash + frozen V4 Flash / Kimi K3 comparison
└── Dark/light theme toggle + inline admin prose editing (<Copy>)
```

## Design principles

- **Chinese-language sources are primary.** English versions of Chinese outlets break stories later and with less analytical depth.
- **Chinese on the page only when it is the source's own words.** UI chrome, captions, and caveats are English only; Chinese characters appear only for source headlines, quotes, official formulations, poll option labels, and gazetted names.
- **Bias labels reflect editorial reality.** CNA is `green_leaning` (state-controlled under DPP), not centrist. UDN is `blue`, not merely blue-leaning.
- **The sentiment axis and topic taxonomy are bidirectional.** Destabilising actions, legal warfare, and administrative regulations from either side register on symmetrical instruments.
- **Human judgment overrides AI.** Every article and side-extracted candidate requires explicit analyst sign-off before reaching public views.

## Model strategy

The pipeline uses Google Gemini 3.1 Flash Lite as the primary
classification engine (via the Gemini Batch API by default) with
Gemini 3.8 Flash for blind escalation review on flagged articles and
for poll-question extraction.

In mid-2026 the approved corpus (15,400+ articles) was audited
against DeepSeek V4 Flash and a stratified Kimi K3 sample on
Western-hosted OpenRouter endpoints using the byte-identical
production prompt, alongside a same-model Gemini control rerun and a
direct-question censorship battery. The structured analytical task
produced zero refusals, no romanisation or title-dropping tells, and
summary entity omission at the Gemini control noise floor. Following
the November 2026 rework to the 24-category taxonomy, the daily
incremental comparison sweep runs on **DeepSeek V4.1 Flash**
(`deepseek/deepseek-v4.1-flash-1017`) under the 24-category schema.
