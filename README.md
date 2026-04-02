# Cross-Strait Signal

**An open-source intelligence dashboard monitoring PRC-Taiwan dynamics through automated bilingual media analysis.**

Cross-Strait Signal scrapes Chinese- and English-language government, military, and media sources from both sides of the Taiwan Strait, processes them through an AI analytical pipeline for translation, entity extraction, topic classification, and escalation detection, and serves the results through a filterable REST API.

## What it does

- **Scrapes 10+ sources** across the PRC and Taiwan — including 国台办 (Taiwan Affairs Office) press conferences, MFA spokesperson transcripts, Xinhua, CNA (中央社), People's Daily, and China News Service
- **AI-powered analysis** classifies each article by topic (13 categories), sentiment (-1.0 to +1.0), urgency level, and escalation signal detection using Google Gemini 2.5 Flash
- **Bilingual entity extraction** identifies leaders, military units, locations, organisations, and weapon systems from Chinese-language source material
- **Analyst commentary layer** allows human editorial override of AI classifications — the tool augments judgment, it doesn't replace it
- **REST API** with full filtering by topic, sentiment, source country, urgency, escalation status, and bilingual full-text search

## Why it exists

There is no accessible, bilingual tool for tracking cross-strait signals that combines Chinese-language primary sources with structured analytical output. English-language coverage of PRC-Taiwan dynamics is slower, less detailed, and often stripped of the linguistic nuance that signals policy shifts.

This tool processes Chinese government and military media in minutes, extracts structured intelligence, and flags escalation signals — work that would take a monolingual analyst hours. The AI layer accelerates analysis; native Mandarin reading ability verifies it.

## Architecture

```
Sources (PRC + Taiwan, Chinese-language priority)
├── RSS scraper (CNA, Xinhua, People's Daily, China News Service, Liberty Times, Taipei Times)
├── HTML scrapers (国台办 weekly pressers, MFA spokesperson transcripts)
│
AI Analysis Pipeline (Gemini 2.5 Flash)
├── Topic classification (13 categories: MIL_EXERCISE, DIP_STATEMENT, POL_TONGDU, etc.)
├── Sentiment scoring (-1.0 conciliatory → +1.0 escalatory)
├── Named entity extraction (people, military units, ships, locations, organisations)
├── Escalation signal detection with urgency grading (flash / priority / routine)
├── Chinese → English translation
│
Storage: SQLite with full-text search (FTS5)
│
FastAPI Backend
├── GET /api/articles — filtered article list with AI analysis and entities
├── GET /api/articles/{id} — single article with full details
├── GET /api/stats — dashboard summary (topic breakdown, sentiment trend, top entities)
├── GET /api/stats/entities — entity leaderboard by mention count
├── POST /api/notes — analyst commentary with sentiment/topic override
├── GET /docs — interactive API documentation
```

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

Chinese-developed AI models (e.g. DeepSeek) were evaluated and rejected for this project. Their political censorship on cross-strait topics — documented by Taiwan's NSB and multiple independent researchers — would corrupt the analytical layer. A model that refuses to classify PLA exercises as escalatory, or that outputs PRC party-line positions as objective analysis, is worse than useless for intelligence monitoring.

The pipeline uses **Google Gemini 2.5 Flash** as the default processing engine (uncensored, strong Chinese-language performance, cost-effective) with **Anthropic Claude Haiku** available for escalation review on flagged articles.

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

Start the API server:

```bash
python -m uvicorn api.main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs`

## Roadmap

- [x] Multi-source bilingual scraping (RSS + HTML)
- [x] AI analysis pipeline with structured JSON output
- [x] FastAPI backend with filtering and search
- [x] Analyst commentary and classification override
- [ ] React dashboard with dark/light theme
- [ ] Sentiment trend visualisation
- [ ] Leader activity tracker
- [ ] Map layer (geocoded entity plotting)
- [ ] Automated scheduling (cron/APScheduler)
- [ ] Docker Compose deployment
- [ ] ADS-B / AIS data integration (Phase 3)

## Built by

**Ed Moon** — Bilingual English-Mandarin analyst with a decade of senior editorial experience in Taiwan. Former Supervising Editor / News Director at TaiwanPlus; previously Editor at The China Post. MA Taiwan Studies (SOAS), BA Contemporary Chinese Studies (Nottingham).

This project demonstrates the intersection of Mandarin fluency, editorial judgment, and technical capability for intelligence production. The AI layer doesn't replace domain expertise — it makes it scalable.

## License

MIT
