# Cross-Strait Signal

**An open-source intelligence dashboard monitoring PRC-Taiwan dynamics through automated bilingual media analysis.**

Cross-Strait Signal scrapes Chinese-language government, military, and media sources from both sides of the Taiwan Strait, processes them through a multi-tier AI analytical pipeline, and serves the results through a React dashboard and filterable REST API.

## What it does

- **Scrapes 8 active sources** across the PRC and Taiwan — 国台办 (Taiwan Affairs Office) press conferences, MFA spokesperson transcripts, Xinhua (新华社), CNA Chinese (中央社), People's Daily (人民日报), China News Service (中国新闻网), Global Times (环球时报), and Liberty Times (自由時報)
- **Directional relevance filtering** — PRC sources checked for Taiwan mentions; Taiwan sources checked for PRC/mainland/HK mentions — before any API calls are made, saving ~80% of processing costs
- **Three-tier AI analysis**: Google Gemini 2.5 Flash Lite for initial processing → Gemini 2.5 Flash for escalation review → human review queue for model disagreements
- **Structured analytical output** per article: topic classification (13 categories), sentiment scoring (-1.0 to +1.0), urgency grading, escalation signal detection, named entity extraction, and Chinese→English translation
- **Human review queue** flags articles where the two AI models disagree on sentiment, topic, or escalation status — allowing editorial override before publication to the dashboard
- **Analyst commentary layer** allows human override of AI classifications at any point
- **Source bias tracking** — each source tagged with editorial alignment (green / green_leaning / blue / state_official / state_nationalist)
- **React dashboard** with dark/light theme, priority signals section, filterable article feed, and review queue UI
- **REST API** with filtering by topic, sentiment, source country, urgency, escalation status, and bilingual full-text search

## Why it exists

There is no accessible, bilingual tool for tracking cross-strait signals that combines Chinese-language primary sources with structured analytical output. English-language coverage of PRC-Taiwan dynamics is slower, less detailed, and often stripped of the linguistic nuance that signals policy shifts.

This tool processes Chinese government and military media in minutes, extracts structured intelligence, and flags escalation signals — work that would take a monolingual analyst hours. The AI layer accelerates analysis; native Mandarin reading ability verifies it.

## Architecture

```
Sources (PRC + Taiwan, Chinese-language priority)
├── RSS scraper (CNA Chinese, Xinhua, People's Daily, China News Service,
│               Global Times, Liberty Times)
├── HTML scrapers (国台办 weekly pressers, MFA spokesperson transcripts)
│
Keyword Pre-filter (directional — no API calls)
├── PRC sources: must mention Taiwan/ROC territory to proceed
├── TW sources: must mention PRC/mainland/HK/Macau to proceed
│
Three-Tier AI Analysis Pipeline
├── Tier 1: Gemini 2.5 Flash Lite — topic, sentiment, entities, urgency
├── Tier 2: Gemini 2.5 Flash — escalation review for flagged articles
├── Tier 3: Human review queue — model disagreement resolution
│
Storage: SQLite with full-text search (FTS5)
│
FastAPI Backend
├── GET /api/articles — filtered article list with AI analysis and entities
├── GET /api/articles/{id} — single article with full details
├── GET /api/stats — dashboard summary (topic breakdown, sentiment trend, entities)
├── GET /api/stats/entities — entity leaderboard by mention count
├── POST /api/notes — analyst commentary with sentiment/topic override
├── GET /review/queue — articles pending human review
├── POST /review/{id}/resolve — resolve review with confirm/override/dismiss
├── GET /review/stats — pending/resolved review counts
├── GET /docs — interactive API documentation
│
React Dashboard
├── Priority Signals (flash/priority urgency articles)
├── Signal Feed (filterable article list)
├── Stats Sidebar (topic breakdown, sentiment gauge, entity tracker)
├── Review Queue (human review UI with override capability)
└── Dark/light theme toggle
```

## Source list

| Source | Country | Language | Bias | Type |
|--------|---------|----------|------|------|
| CNA Chinese (中央社) | TW | zh-tw | green_leaning | State media |
| Liberty Times (自由時報) | TW | zh-tw | green | Independent |
| Xinhua (新华社) | PRC | zh-cn | state_official | State media |
| People's Daily Politics (人民日报) | PRC | zh-cn | state_official | State media |
| China News Service (中国新闻网) | PRC | zh-cn | state_official | State media |
| Global Times (环球时报) | PRC | zh-cn | state_nationalist | State media |
| PRC MFA Spokesperson (外交部) | PRC | zh-cn | state_official | Government |
| Taiwan Affairs Office (国台办) | PRC | zh-cn | state_official | Government |

## Topic taxonomy

| Code | Description |
|------|-------------|
| `MIL_EXERCISE` | PLA drills, live-fire exercises, joint exercises near Taiwan |
| `MIL_MOVEMENT` | Troop deployments, naval transits, ADIZ incursions |
| `MIL_HARDWARE` | Weapons systems, procurement, missile deployments |
| `DIP_STATEMENT` | MFA remarks, TAO statements, official warnings |
| `DIP_VISIT` | Leader travel, delegation visits, ally engagement |
| `DIP_SANCTIONS` | Trade restrictions, entity listings, diplomatic downgrades |
| `ECON_TRADE` | Cross-strait trade, supply chain, ECFA |
| `ECON_INVEST` | FDI flows, business restrictions, tech sector |
| `POL_DOMESTIC` | Taiwan elections, party dynamics, PRC internal politics |
| `POL_TONGDU` | One China references, reunification rhetoric, sovereignty claims |
| `INFO_WARFARE` | Disinformation, cognitive warfare, media manipulation |
| `LEGAL_GREY` | Coast guard activity, sand dredging, cable incidents |
| `HUMANITARIAN` | People-to-people exchange, cultural events, humanitarian issues |

## Model strategy

The pipeline uses **Google Gemini 2.5 Flash Lite** as the default processing engine (cost-effective, strong Chinese-language performance) with **Gemini 2.5 Flash** for escalation review on flagged articles. DeepSeek was evaluated and rejected due to documented political censorship on cross-strait topics. The `POL_TONGDU` (統獨) classification deliberately captures the full unification-independence spectrum rather than framing cross-strait dynamics as a one-directional PRC threat.

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
ANTHROPIC_API_KEY=your_anthropic_key_here
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

## Roadmap

- [x] Multi-source bilingual scraping (RSS + HTML)
- [x] Directional keyword pre-filter (saves ~80% API costs)
- [x] Three-tier AI analysis pipeline with human review queue
- [x] Source bias taxonomy (green / blue / state_official / state_nationalist)
- [x] FastAPI backend with filtering and full-text search
- [x] Analyst commentary and classification override
- [x] React dashboard with dark/light theme
- [x] Priority signals section and review queue UI
- [ ] Sentiment trend visualisation
- [ ] Topic breakdown chart
- [ ] Automated scheduling (APScheduler)
- [ ] VPS deployment
- [ ] UDN HTML scraper (RSS feed deprecated)
- [ ] Provincial PRC media sources (Fujian, Shanghai, Guangdong)
- [ ] Social media signal layer (Weibo, PTT)
- [ ] Leader activity tracker
- [ ] Map layer (geocoded entity plotting)
- [ ] ADS-B / AIS data integration (Phase 3)

## Built by

**Ed Moon** — Bilingual English-Mandarin analyst and former News Director at TaiwanPlus, with a decade of senior editorial experience in Taiwan. MA Taiwan Studies (SOAS).

## License

MIT
