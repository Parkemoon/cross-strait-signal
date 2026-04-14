# Cross-Strait Signal

An open-source intelligence dashboard monitoring PRC-Taiwan cross-strait dynamics through automated bilingual Chinese-language media analysis.

---

Cross-Strait Signal scrapes Chinese-language news sources from both sides of the Taiwan Strait, processes them through a multi-tier AI pipeline, and serves results through a React dashboard backed by a FastAPI API. The system is designed to surface destabilising signals from **both** sides — including Taiwanese actions (independence-by-stealth, constitutional norm erosion) — not as a "China bad, Taiwan good" instrument.

**Live instance:** `https://strait-signal.net`  
**GitHub:** `https://github.com/Parkemoon/cross-strait-signal`

---

## What it does

- Scrapes ~30 active sources across PRC, Taiwan, Hong Kong, Singapore, and the UK — including RSS feeds and bespoke HTML scrapers for sites without usable feeds (TAO, MFA, Guancha, Haixia Daobao, PLA Daily, YDN, LTN Defence, UDN sections)
- Directional relevance filtering — PRC/HK/SG sources checked for Taiwan mentions; Taiwan sources checked for PRC/mainland/HK mentions — before any API calls are made, saving ~80% of processing costs
- Three-tier AI analysis: Google Gemini 2.5 Flash Lite for initial processing → Gemini 2.5 Flash for escalation review → human review queue for model disagreements
- Structured analytical output per article: topic classification (27 categories), sentiment scoring (−1.0 to +1.0), urgency grading, escalation signal detection, named entity extraction, and Chinese→English translation
- Full editorial approval gate — every article is held from the public feed until the analyst explicitly approves it, ensuring no AI translation errors or misclassifications reach readers
- Inline translation editing on headline, summary, and key quote — corrected fields highlighted amber to distinguish human-verified text from raw AI output
- Human review queue flags articles where the two AI models disagree on sentiment, topic, or escalation status — translation editing available within the queue, auto-approves on resolution
- Analyst commentary layer allows human override of AI classifications at any point
- Source bias tracking — each source tagged with editorial alignment (green / green_leaning / blue / centrist / state_official / state_nationalist)
- Social Pulse panel — Weibo hot search top 50 (cross-strait items highlighted) and PTT BBS trending posts, with AI translation and inline analyst correction; lives in a persistent right-hand column
- Key Figures panel — curated roster of 10 senior PRC and Taiwan officials; AI extracts attributed quotes and actions per figure as pending candidates, requiring analyst approval before display to prevent misattribution
- React dashboard with dark/light theme, priority signals section, filterable article feed, event clustering, Key Figures panel, Social Pulse column, and review queue UI — fully responsive with mobile tab navigation
- Two-build deployment: public read-only build (`strait-signal.net`) hides all write controls at build time; admin build (`admin.strait-signal.net`) exposes the full editorial interface
- REST API with filtering by topic, sentiment, source place (PRC / Taiwan / HK/Macao / International), urgency, escalation status, and bilingual full-text search

---

## Why it exists

There is no accessible, bilingual tool for tracking cross-strait signals that combines Chinese-language primary sources with structured analytical output. English-language coverage of PRC-Taiwan dynamics is slower, less detailed, and often stripped of the linguistic nuance that signals policy shifts.

This tool processes Chinese government and military media in minutes, extracts structured intelligence, and flags escalation signals — work that would take a monolingual analyst hours. The AI layer accelerates analysis; native Mandarin reading ability verifies it.

---

## Architecture

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
├── Tier 1: Gemini 2.5 Flash Lite — topic, sentiment, entities, urgency
├── Tier 2: Gemini 2.5 Flash — escalation review for flagged articles
├── Tier 3: Human review queue — model disagreement resolution
│            (translation editing + auto-approve on resolution)
│
Editorial Approval Gate
└── All articles held from public feed until analyst explicitly approves
│
Social Translation (separate lightweight pipeline)
└── Gemini 2.5 Flash Lite — batch-translates Weibo/PTT titles only
│
Storage: SQLite with full-text search (FTS5)
│
FastAPI Backend
├── GET /api/articles — filtered article feed; ?include_pending=true for admin (shows unapproved)
├── GET /api/articles/{id} — single article with full details
├── POST /api/articles/{id}/approve — mark article as analyst-approved for public feed
├── PATCH /api/articles/{id}/translation — override headline, summary, or key quote translation
├── GET /api/stats — dashboard summary (topic breakdown, sentiment trend, entities)
├── GET /api/stats/entities — entity leaderboard by mention count
├── POST /api/notes — analyst commentary with sentiment/topic/score override
├── GET /api/social/ — latest Weibo top 50 + PTT trending posts
├── PATCH /api/social/{id}/translation — save analyst translation correction
├── GET /api/stats/key-figures — latest approved statement per curated figure
├── GET /api/stats/key-figures/candidates — pending statements grouped by figure
├── POST /api/stats/key-figures/statements/{id}/approve — approve a candidate
├── POST /api/stats/key-figures/statements/{id}/dismiss — dismiss a candidate
├── GET /review/queue — articles pending human review
├── POST /review/{id}/resolve — resolve review with confirm/override/dismiss
├── GET /review/stats — pending/resolved counts + pending_approval count
└── GET /docs — interactive API documentation
│
React Dashboard
├── Priority Signals (flash/priority urgency articles)
├── Key Figures panel (10 curated officials, portraits, latest approved statement, curation modal)
├── Signal Feed (filterable article list with event clustering; filter by PRC / Taiwan / HK/Macao / International)
├── Social Pulse column (Weibo cross-strait items + PTT trending, persistent right-hand column)
├── Strait Watch gauges (overall + PRC / TW / HK/Macao / International + by political camp)
├── Sentiment trend chart and topic breakdown chart (Recharts)
├── Inline editorial overrides (sentiment, topic, score on any article card)
├── Inline translation editing (headline, summary, key quote — amber highlight on override)
├── Editorial approval gate (pending articles shown with amber border + approve/dismiss buttons)
├── Analyst commentary per article
├── Review Queue (human review UI with translation editing + confirm/override/dismiss)
└── Dark/light theme toggle
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI (Python) |
| Database | SQLite |
| AI Pipeline | Google Gemini 2.5 Flash Lite + Flash |
| Scraping | feedparser, BeautifulSoup, httpx |
| Frontend | React 19, Recharts |
| RSS proxy | RSSHub (self-hosted Docker) |
| Web Server | Nginx (reverse proxy + static serving) |
| Process Manager | systemd |
| Hosting | Ionos VPS S+, Ubuntu 24.04 |

---

## Source List

### Bias Labels

| Label | Meaning |
|-------|---------|
| `green` | Explicitly pro-independence editorial line |
| `green_leaning` | State-controlled under DPP-led government |
| `blue` | Consistent KMT-aligned editorial line |
| `centrist` | Editorially independent |
| `state_official` | PRC state media or government organ |
| `state_nationalist` | PRC nationalist commentary |

### Active Sources

**Taiwan**

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

**PRC**

| Source | Bias | Method |
|--------|------|--------|
| Xinhua Chinese (新华社) | state_official | RSS |
| People's Daily Politics (人民日报台湾) | state_official | RSS (RSSHub) |
| China News Service (中国新闻网) | state_official | RSS |
| Global Times (环球时报台海) | state_nationalist | RSS (RSSHub) |
| The Paper (澎湃新聞) | state_official | RSS (RSSHub) |
| PRC MFA Spokesperson (外交部发言人) | state_official | HTML scraper |
| Taiwan Affairs Office (国台办) | state_official | HTML scraper |
| Guancha (观察者网) | state_nationalist | HTML scraper |
| Haixia Daobao (海峽導報) | state_official | HTML scraper |
| PLA Daily (解放軍報) | state_official | HTML scraper |

**Hong Kong**

| Source | Bias | Method |
|--------|------|--------|
| RTHK Greater China (香港電台大灣區) | state_official | RSS |
| Ming Pao Cross-Strait (明報兩岸) | centrist | RSS |
| Ming Pao Editorial (明報社評) | centrist | RSS |
| Ming Pao Opinion (明報觀點) | centrist | RSS |

**International**

| Source | Bias | Method |
|--------|------|--------|
| Zaobao Cross-Strait (联合早报中港台) | centrist | RSS (RSSHub) |
| BBC Chinese (BBC中文) | centrist | RSS |

**Social (not in article pipeline)**

| Source | Method |
|--------|--------|
| Weibo Hot Search (微博热搜) | JSON API |
| PTT Military / Gossiping / HatePolitics | HTML scraper |

### Deactivated

- **Guangming Daily (光明日報)** — anyfeeder proxy dead, rarely cross-strait relevant

---

## Topic Taxonomy

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

`POL_TONGDU` (統獨) rather than `POL_UNIFICATION` — the bidirectional framing reflects that both independence moves and unification rhetoric shift the status quo.

---

## Sentiment Axis

| Score | Label | Meaning |
|-------|-------|---------|
| −1.0 to −0.3 | Hostile | Article frames the other side negatively — threatening, antagonistic, confrontational |
| −0.3 to +0.3 | Neutral | Factual reporting without strong positive or negative framing of the other side |
| +0.3 to +1.0 | Cooperative | Warm, engaging framing — shared identity, dialogue, trade, people-to-people ties |

Sentiment measures **how the source frames the opposing side of the strait**, not geopolitical stability. For PRC sources: how does the article portray Taiwan? For Taiwan sources: how does it portray the PRC? The axis is **bidirectional** — a PRC outlet publishing a hostile piece about Lai Ching-te and a Taiwan outlet publishing a hostile piece about PLA exercises both score negative. Taiwan-US military cooperation does not score as cross-strait cooperative.

---

## Model Strategy

The pipeline uses Google Gemini 2.5 Flash Lite as the default processing engine (cost-effective, strong Chinese-language performance) with Gemini 2.5 Flash for escalation review on flagged articles. DeepSeek was evaluated and rejected due to documented political censorship on cross-strait topics — it consistently refused to analyse or misclassified content involving Taiwan independence, PLA exercises, and cross-strait political dynamics.

---

## Setup

```bash
git clone https://github.com/Parkemoon/cross-strait-signal.git
cd cross-strait-signal
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
GEMINI_API_KEY=your_gemini_key_here
```

Initialise the database and seed sources:

```bash
python scripts/init_db.py
python scripts/seed_sources.py
```

Run the full pipeline (scrape + analyse):

```bash
python scripts/run_pipeline.py
```

Start the API server and React dashboard:

```bash
# Terminal 1 — API
python -m uvicorn api.main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm start
```

API docs available at `http://localhost:8000/docs`  
Dashboard available at `http://localhost:3000`

---

## Deployment

### RSSHub

Several sources (People's Daily, Global Times, The Paper, Zaobao, RTHK, China Times sections) are fetched via a self-hosted RSSHub instance. Run it as a Docker container with Chromium bundled (required for China Times):

```bash
docker run -d --name rsshub --restart always -p 1200:1200 diygod/rsshub:chromium-bundled
```

### Server Setup

```bash
cd /var/www
git clone https://github.com/Parkemoon/cross-strait-signal.git
cd cross-strait-signal
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
python scripts/init_db.py
python scripts/seed_sources.py
```

### systemd Service

```ini
# /etc/systemd/system/cross-strait-signal.service
[Unit]
Description=Cross-Strait Signal API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/var/www/cross-strait-signal
Environment=PATH=/var/www/cross-strait-signal/venv/bin
ExecStart=/var/www/cross-strait-signal/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Nginx Config

Two server blocks — one per domain, both proxying to the same FastAPI backend.

**Public** (`/etc/nginx/sites-available/cross-strait-signal-public`):
```nginx
server {
    listen 80;
    server_name strait-signal.net www.strait-signal.net;

    root /var/www/cross-strait-signal/frontend/build-public;
    index index.html;

    location / { try_files $uri $uri/ /index.html; }

    location /api/ {
        limit_except GET { deny all; }
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Admin** (`/etc/nginx/sites-available/cross-strait-signal-admin`):
```nginx
server {
    listen 80;
    server_name admin.strait-signal.net;

    auth_basic "Cross-Strait Signal";
    auth_basic_user_file /etc/nginx/.htpasswd;

    root /var/www/cross-strait-signal/frontend/build;
    index index.html;

    location / { try_files $uri $uri/ /index.html; }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /review/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
}
```

### Cron Schedule

```bash
# Pipeline runs twice daily — 7am and 7pm BST (6am/6pm UTC)
0 6,18 * * * cd /var/www/cross-strait-signal && /var/www/cross-strait-signal/venv/bin/python scripts/run_pipeline.py >> /var/log/cross-strait-pipeline.log 2>&1
```

### Deploy Workflow

```bash
# Local — commit, push, then SSH to server
git push
ssh root@<your-server>
cd /var/www/cross-strait-signal && ./server_deploy.sh
```

`server_deploy.sh` runs `git pull`, builds both frontend versions (`npm run build` for admin, `npm run build:public` for public), and restarts the service.

---

## Design Principles

- **Chinese-language sources are primary.** English versions of Chinese outlets break stories later and with less analytical depth.
- **Bias labels reflect editorial reality, not diplomatic hedging.** CNA is `green_leaning` (state-controlled under DPP), not centrist. UDN is `blue` (consistent editorial line), not merely blue-leaning.
- **The sentiment axis is bidirectional.** Destabilising actions from either side register on the same scale.
- **POL_TONGDU not POL_UNIFICATION.** The 統獨 spectrum runs in both directions.
- **Human judgment overrides AI.** The review queue, inline overrides, and translation editing exist because AI classification and translation of politically sensitive content requires editorial judgment.
- **Every article requires analyst approval.** Nothing reaches the public dashboard without explicit sign-off. AI-flagged articles are additionally routed through the review queue before approval.

---

## Roadmap

- [x] Multi-source bilingual scraping (RSS + HTML)
- [x] Directional keyword pre-filter (saves ~80% API costs)
- [x] Three-tier AI analysis pipeline with human review queue
- [x] Source bias taxonomy (green / blue / state_official / state_nationalist)
- [x] FastAPI backend with filtering and full-text search
- [x] Analyst commentary and classification override
- [x] React dashboard with dark/light theme
- [x] Priority signals section and review queue UI
- [x] Sentiment trend visualisation
- [x] Topic breakdown chart
- [x] Event clustering (Jaccard similarity, 48-hour window)
- [x] Automated scheduling (cron, twice daily)
- [x] VPS deployment
- [x] UDN HTML scraper (4 sections)
- [x] Provincial PRC media sources (海峽導報, 解放軍報, 观察者网)
- [x] LTN Defence scraper
- [x] YDN (ROC MND newspaper) scraper
- [x] Source badges colour-coded by political bias
- [x] Social media signal layer (Weibo hot search + PTT trending)
- [x] Key Figures panel with manual curation workflow (attributed quotes/actions, analyst approval)
- [x] Public read-only dashboard (`strait-signal.net`) — write controls hidden at build time
- [x] Domain name + SSL (`strait-signal.net` / `admin.strait-signal.net`, Cloudflare proxy)
- [x] Mobile-responsive layout with tab navigation
- [x] Editorial approval gate — all articles held from public feed until analyst sign-off
- [x] Inline translation editing (headline, summary, key quote) with amber override indicator
- [x] China Times sections via self-hosted RSSHub (chromium-bundled)
- [x] HK sources — RTHK Greater China, Ming Pao (Cross-Strait, Editorial, Opinion)
- [x] International Chinese-language sources — BBC Chinese, Zaobao
- [ ] Map layer (geocoded entity plotting)
- [ ] ADS-B / AIS data integration (Phase 3)

---

## Author

Ed Moon — bilingual English-Mandarin analyst, former Supervising Editor at TaiwanPlus.  
Substack: [The East and Back](https://theeastandback.substack.com)

---

## License

[GPL-3.0](LICENSE)
