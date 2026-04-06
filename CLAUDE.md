# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Cross-Strait Signal** is an open-source intelligence dashboard monitoring PRC-Taiwan cross-strait dynamics through automated bilingual (Chinese-English) media analysis. It scrapes 11 active news sources, processes articles through a multi-tier AI pipeline, and serves results via a React dashboard backed by FastAPI.

**Critical design intent**: The sentiment axis is bidirectional — destabilising signals from BOTH sides (PLA exercises AND DPP sovereignty moves) register equally. This is not a "China bad, Taiwan good" instrument.

## Commands

### Backend Setup
```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
pip install -r requirements.txt
python scripts/init_db.py
python scripts/seed_sources.py
```

### Running the App (2 terminals)
```bash
# Terminal 1 — FastAPI backend (http://localhost:8000)
python -m uvicorn api.main:app --reload --port 8000

# Terminal 2 — React frontend (http://localhost:3000)
cd frontend && npm start
```

### Pipeline (Scrape + AI Analysis + Clustering)
```bash
python scripts/run_pipeline.py
```

### Frontend
```bash
cd frontend
npm install
npm run build
npm test
```

### API Docs
Interactive Swagger UI at `http://localhost:8000/docs` when backend is running.

## Architecture

### Data Flow
```
11 RSS/HTML sources
    → Keyword pre-filter (directional: saves ~80% API cost)
    → Tier 1 AI: Gemini 2.5 Flash Lite (topic, sentiment, entities, urgency)
    → Tier 2 AI: Gemini 2.5 Flash (escalation review, conditional)
    → Tier 3: Human review queue (model disagreements)
    → SQLite + FTS5
    → FastAPI routes
    → React dashboard
```

### Three-Tier AI Pipeline (`scraper/processors/ai_pipeline.py`)
- **Tier 1**: Gemini 2.5 Flash Lite — classifies all pre-filtered articles
- **Tier 2**: Gemini 2.5 Flash — re-reviews only escalation-flagged articles
- **Tier 3**: Human review queue — for articles where Tier 1 and Tier 2 disagree; articles stay hidden from dashboard until resolved

### Keyword Pre-Filter (`scraper/processors/keyword_filter.py`)
Directional logic:
- PRC/Singapore sources: must mention Taiwan, ROC, or relevant territories
- Taiwan sources: must mention PRC, mainland, Hong Kong, or Macau

### Event Clustering (`scripts/cluster_events.py`)
Groups related articles within a 48-hour window using Jaccard similarity on title keywords (threshold: 0.25).

### Database Schema (`db/schema.sql`)
SQLite with FTS5 full-text search. Key tables:
- **articles**: raw scraped content, `ai_processed` flag, unique constraint on URL
- **ai_analysis**: structured AI output — `topic_primary`, `sentiment`, `sentiment_score` (−1.0 to +1.0), `urgency`, `is_escalation_signal`, `needs_human_review`, confidence
- **entities**: named entities with type (person, military_unit, ship, aircraft, location, organisation, weapon_system) and geocoding fields
- **analyst_notes**: human editorial commentary with sentiment/topic override capability
- **articles_fts**: FTS5 virtual table for bilingual full-text search

### API Layer (`api/routes/`)
- `articles.py`: GET `/api/articles` (8 filter params), cluster, hide, signal endpoints
- `stats.py`: dashboard aggregations, entity leaderboard
- `notes.py`: CRUD for analyst notes with AI override support
- `review.py`: review queue — confirm / override / dismiss

### Frontend (`frontend/src/`)
React 19 + Recharts + Tailwind CSS 4. State management lives in `App.js`. Key components:
- `FilterBar.jsx`: topic, sentiment, source_country, urgency, escalation, search filters
- `ArticleCard.jsx`: article display with inline sentiment/topic override and analyst notes
- `ReviewQueue.js`: human review UI
- `SignalCharts.jsx`: sentiment trend + topic breakdown charts
- `StatsSidebar.jsx`: dashboard gauges by country and bias label
- `FlashTraffic.jsx`: priority signals section

## Environment

Requires `.env` in project root:
```
GEMINI_API_KEY=your_key_here
```

## Key Domain Concepts

**Topic taxonomy (13 categories)**: `MIL_EXERCISE`, `MIL_MOVEMENT`, `MIL_HARDWARE`, `DIP_STATEMENT`, `DIP_VISIT`, `DIP_SANCTIONS`, `ECON_TRADE`, `ECON_INVEST`, `POL_DOMESTIC`, `POL_TONGDU`, `INFO_WARFARE`, `LEGAL_GREY`, `HUMANITARIAN`

**POL_TONGDU** (統獨): Captures both unification rhetoric AND independence moves — bidirectional by design.

**Sentiment values**: `destabilising` / `stabilising` / `neutral` / `ambiguous` with numeric score

**Urgency levels**: `flash` / `priority` / `routine`

**Source bias labels**: `green`, `green_leaning`, `blue`, `centrist`, `state_official`, `state_nationalist`

**Active sources**: CNA (green_leaning), Liberty Times (green), Xinhua, People's Daily, China News Service, Global Times, The Paper, Guangming Daily, MFA Spokesperson, Taiwan Affairs Office, Zaobao (centrist/Singapore)

## Important Behaviors

- Articles with `needs_human_review = 1` and unresolved status are **hidden from the public feed** until reviewed
- Chinese-language sources are treated as primary — they break stories earlier
- Bias labels reflect editorial reality and should not be softened (e.g. CNA is green_leaning, not neutral)
- The human review queue and inline analyst overrides exist because political classification requires editorial judgment — AI output is a starting point, not final word
