# Cross-Strait Signal

An open-source intelligence dashboard monitoring PRC-Taiwan cross-strait
dynamics through automated bilingual Chinese-language media analysis.
~30 active sources from both sides of the strait, scraped continuously
and run through a three-tier AI pipeline behind a human editorial gate.

**Live instance:** https://strait-signal.net
**GitHub:** https://github.com/Parkemoon/cross-strait-signal

---

## What it does

- Reads Chinese-language primary sources from PRC, Taiwan, Hong Kong, Singapore, and the UK — RSS feeds and bespoke HTML scrapers for sites without usable feeds.
- Classifies each article along three axes (topic, sentiment, urgency), extracts named entities and attributed quotes, and produces an English summary plus translation of the key quote.
- Tracks parallel structured datasets that contextualise the news feed: bilateral trade with multi-reporter verification, trade-access asymmetry (what each side allows the other to ship), bidirectional residency stocks and flows, PLA incursion counts, and a cross-strait military exercise tracker.
- Holds every article behind an analyst-approval gate. Nothing reaches the public feed until a human has confirmed the AI's call (or corrected it).
- Surfaces a poll tracker covering Taiwan's main pollsters with canonical question_keys for cross-pollster trend charts (Lai approval, 統獨 position, KMT chair trust, etc.).
- Publishes a public read-only build and a separate admin build — write controls don't exist in the public bundle.

## Why it exists

There is no accessible, bilingual tool that combines Chinese-language
primary sources with structured analytical output. English-language
coverage of PRC-Taiwan dynamics is slower, less detailed, and stripped
of the linguistic nuance that signals policy shifts. The standard
alternative is hiring a Mandarin-reading analyst.

This system processes Chinese government, military, and partisan media
in minutes, extracts structured intelligence, and flags escalation
signals — work that would take a monolingual analyst hours. The AI
layer accelerates analysis; native Mandarin reading by the operator
verifies it before publication.

The sentiment axis is deliberately **bidirectional**. Destabilising
moves from either side score equally — PLA exercises and DPP
sovereignty rhetoric register on the same instrument. This is not a
"China bad, Taiwan good" dashboard; it's an attempt to measure
cross-strait friction without picking a side.

## Methodology

### Topic taxonomy

28 categories spanning military activity (`MIL_EXERCISE`,
`MIL_MOVEMENT`, `MIL_HARDWARE`, `MIL_POLICY`, `ARMS_SALES`,
`LEGAL_GREY`), diplomacy and political contact (`DIP_STATEMENT`,
`DIP_VISIT`, `DIP_SANCTIONS`, `PARTY_VISIT`, `INT_ORG`), the
US-PRC-Taiwan triangle (`US_PRC`, `US_TAIWAN`), economic and
technological flows (`ECON_TRADE`, `ECON_INVEST`, `ENERGY`,
`SCI_TECH`), domestic politics (`POL_DOMESTIC_TW`, `POL_DOMESTIC_PRC`,
`POL_TONGDU`), information and cyber operations (`INFO_WARFARE`,
`CYBER`), and a handful of less-obvious categories (`HK_MAC`,
`CULTURE`, `SPORT`, `TRANSPORT`, `HUMANITARIAN`). Boundaries at the
edges are fuzzy by design — see Limitations.

### Sentiment axis

`hostile` / `cooperative` / `neutral` / `mixed` plus a numeric score
from −1.0 (most hostile) to +1.0 (most cooperative). Measures how
positively or negatively the article frames the **opposing side of
the strait** — not geopolitical "stability" in the abstract. A PRC
source covering Taiwan is rated on how it portrays Taiwan; a Taiwan
source on how it portrays the PRC. Taiwan-US military cooperation is
scored neutral-to-hostile (from the cross-strait frame), not
cooperative. KMT visits to the mainland score cooperative regardless
of how a Taiwanese viewer feels about them.

Every directional score must include a `sentiment_reasoning` line
quoting the specific phrase or framing that drove it — both as an
audit trail for the analyst and as a constraint that prevents the
model from emitting a score without textual evidence.

### Source bias

Each source is hand-labelled with one of seven bias categories. The
labels reflect editorial reality, not political diplomacy.

| Label | Meaning |
|-------|---------|
| `green` | Explicitly pro-independence editorial line |
| `green_leaning` | State-controlled under the current DPP government |
| `centrist` | Editorially independent |
| `blue_leaning` | KMT-sympathetic but not party-aligned |
| `blue` | Consistent KMT-aligned editorial line |
| `state_official` | PRC state media or government organ |
| `state_nationalist` | PRC nationalist commentary |

The bias label is *not* used to weight or filter content. It exists
so a reader can interpret a hostile score from CNA differently than
the same score from Global Times. Source bias correlates with
sentiment by construction — that correlation is part of the signal,
not a flaw to be normalised away.

### Model strategy

Three tiers:

1. **Tier 1 — Gemini 3.1 Flash Lite.** Classifies every article that
   passes the directional keyword pre-filter. Outputs topic,
   sentiment, urgency, entities, key quote, summary. Side-extracts
   poll questions, military exercise candidates, and key figure
   statements where applicable. Temperature 0.1, medium thinking.
2. **Tier 2 — Gemini 3.5 Flash.** Re-reviews articles Tier 1 flagged
   as escalation signals or `flash` urgency. The two tiers'
   sentiment, topic, and escalation calls are compared.
3. **Tier 3 — human review queue.** Articles where Tier 1 and Tier 2
   disagree are held off the public feed until the analyst resolves
   them.

The keyword pre-filter is directional: PRC/HK/SG sources must mention
Taiwan to proceed; Taiwan sources must mention PRC/HK/Macau. Articles
the filter rejects never reach the AI API, which cuts ~80% of
processing cost.

Glossary injection (pre-analysis) and entity canonical normalisation
(post-analysis) handle two failure modes that the bare model gets
wrong: romanising Chinese names in Wade-Giles vs Hanyu Pinyin
depending on the entity's jurisdiction, and attributing roles to
former officeholders based on stale training data. The Wikidata-sourced
current officials roster covers ~28 positions across TW/US/PRC/JP and
is refreshed manually.

### Accuracy

<!-- Generated by scripts/accuracy_report.py — last 180 days,
     2025-11-28 → 2026-05-27. Re-run to refresh. -->

Snapshot over the last 180 days. The analyst engaged with 7,710
articles, approving 6,001 and dismissing 1,709 (22.2%).

**Caveat to read first.** Explicit topic / sentiment relabels are
rare in practice — the analyst more often dismisses an article than
relabels it. The override rates below are a lower bound on
analyst-AI disagreement, not a measure of model accuracy. The
per-topic **dismissal rate** is the more informative signal because
it captures the dominant correction action.

**Explicit overrides on approved articles:**

| Field                 | Override rate | Count |
|-----------------------|---------------|-------|
| Topic relabel         | 0.05%         | 3     |
| Sentiment relabel     | 0.10%         | 6     |
| Title translation     | 8.5%          | 510   |
| Summary translation   | 7.9%          | 472   |
| Key-quote translation | 0.42%         | 25    |

Tier 1 / Tier 2 escalation review disagreement: 114 flagged, 114
resolved, 0 open.

**Per-topic dismissal rate** — of articles the analyst touched in
each category, what fraction was dismissed? High dismissal = model
surfacing weakly-relevant articles. Categories with <20 touched
articles in window are omitted.

| Topic | Approved | Dismissed | Dismiss % |
|-------|----------|-----------|-----------|
| POL_DOMESTIC_TW | 1184 | 726 | 38.0% |
| DIP_STATEMENT | 844 | 121 | 12.5% |
| MIL_POLICY | 576 | 97 | 14.4% |
| POL_TONGDU | 461 | 51 | 10.0% |
| ECON_TRADE | 343 | 162 | 32.1% |
| PARTY_VISIT | 378 | 24 | 6.0% |
| DIP_VISIT | 320 | 56 | 14.9% |
| CULTURE | 211 | 144 | 40.6% |
| US_PRC | 235 | 18 | 7.1% |
| US_TAIWAN | 222 | 16 | 6.7% |
| SCI_TECH | 141 | 77 | 35.3% |
| MIL_EXERCISE | 161 | 23 | 12.5% |
| MIL_MOVEMENT | 141 | 13 | 8.4% |
| INT_ORG | 125 | 7 | 5.3% |
| POL_DOMESTIC_PRC | 92 | 38 | 29.2% |
| TRANSPORT | 99 | 26 | 20.8% |
| ARMS_SALES | 111 | 13 | 10.5% |
| INFO_WARFARE | 87 | 21 | 19.4% |
| ECON_INVEST | 33 | 29 | 46.8% |
| CYBER | 50 | 3 | 5.7% |
| MIL_HARDWARE | 46 | 6 | 11.5% |
| LEGAL_GREY | 46 | 4 | 8.0% |
| HUMANITARIAN | 44 | 2 | 4.3% |
| HK_MAC | 22 | 12 | 35.3% |
| ENERGY | 17 | 6 | 26.1% |
| SPORT | 11 | 11 | 50.0% |

Three findings worth reading honestly:

- **High-volume categories the model handles cleanly:** PARTY_VISIT
  (6.0% dismissal), POL_TONGDU (10.0%), DIP_STATEMENT (12.5%),
  MIL_POLICY (14.4%). When the keyword filter accepts an article
  classified into one of these, the analyst almost always keeps it.
- **Categories where the model surfaces noise:** CULTURE (40.6%),
  POL_DOMESTIC_TW (38.0%), SCI_TECH (35.3%), HK_MAC (35.3%),
  ECON_TRADE (32.1%). The keyword pre-filter accepts these but the
  cross-strait angle often turns out weak on read. The analyst
  layer is doing meaningful filtering here.
- **Translation correction is the real human work** — 8.5% of
  approved articles needed a title fix, 7.9% a summary fix. That's
  the load-bearing analyst contribution at the per-article level
  (vs. relabelling, which essentially never happens).

Re-run `python scripts/accuracy_report.py` for a fresh snapshot, or
`--markdown` to regenerate this block.

## Sources

### Active Taiwan-side sources

| Source | Bias | Method |
|--------|------|--------|
| LTN (自由時報) — Politics / World / Business / Defence | green | RSS + HTML |
| CNA (中央社) — Politics / Mainland / International / Finance | green_leaning | RSS |
| YDN (青年日報) | green_leaning | HTML scraper |
| CT (中時) — Cross-Strait / Politics / Military / Opinion | blue | RSS (via RSSHub) |
| UDN (聯合報) — Cross-Strait / Breaking / International / Business | blue | HTML scraper |

### Active PRC and HK sources

| Source | Bias | Method |
|--------|------|--------|
| Xinhua (新华社) | state_official | RSS |
| People's Daily (人民日报台湾) | state_official | RSS via RSSHub |
| China News Service (中国新闻网) | state_official | RSS |
| TAO (国台办) | state_official | HTML scraper |
| MFA (外交部) | state_official | HTML scraper |
| PLA Daily (解放军报) | state_official | HTML scraper |
| Global Times (环球时报台海) | state_nationalist | RSS via RSSHub |
| Guancha (观察者网) | state_nationalist | HTML scraper |
| Haixia Daobao (海峡导报) | state_nationalist | HTML scraper |
| The Paper (澎湃新闻) | state_official | RSS |
| RTHK Greater China (after NSL) | state_official | RSS |
| Ming Pao | centrist | RSS |
| Zaobao (Singapore) | centrist | RSS |
| BBC Chinese | centrist | RSS (summary only — body is Next.js CSR) |

YDN is labelled `green_leaning` because it is MND state media under
the current DPP executive. The label tracks the government, not the
publisher — reclassify if the executive changes party. Same logic
applied to RTHK after the National Security Law.

## Limitations

What the system can't do, or does badly. Listed in descending order
of how much they affect the editorial product.

- **High-noise categories** include `CULTURE`, `POL_DOMESTIC_TW`,
  `SCI_TECH`, `HK_MAC`, and `ECON_TRADE` — the analyst dismisses
  30–40% of articles in these categories rather than approving them.
  The keyword pre-filter accepts these articles but the cross-strait
  angle is often weak on read. Read what survives the analyst, not
  the raw topic feed.
- **Topic / sentiment labels are essentially never relabelled** (3
  topic relabels and 6 sentiment relabels in 6,001 approved articles).
  This is *not* evidence that the model is perfect — it means the
  analyst dismisses ambiguous articles rather than correcting their
  labels. The override-based agreement metric is a floor, not a
  ceiling.
- **Source bias correlates with sentiment by construction.** Green
  sources rate PRC moves more hostilely than centrist ones; PRC state
  media rates Taiwan moves more hostilely under DPP than under KMT
  governments. This is part of the signal, not a flaw — but a reader
  comparing absolute scores across sources without bias-controlling
  is reading noise.
- **TW-in-PRC residency data is hand-curated.** PRC bureaus do not
  publish machine-readable endpoints for 台胞证 issuance, census
  cross-tabs, or settler floor stocks. The data on People tab is
  manually compiled from the published bureaus' PDF/HTML snapshots
  and lags 6–12 months. PRC-in-Taiwan data is automated (NIA APIs).
- **No Cantonese sources.** Hong Kong coverage relies on Chinese-
  language outlets (RTHK, Ming Pao). Cantonese-only commentary is
  not represented.
- **Officials roster covers ~28 positions.** Lower-level officeholder
  hallucinations are possible; the model may attribute a role to a
  former occupant when the article references someone outside the
  roster. Wikidata refresh is manual (`scripts/refresh_officials.py`)
  — typically run after elections and cabinet reshuffles.
- **BBC Chinese body content is unavailable.** Article pages are
  Next.js client-side rendered; BeautifulSoup yields no text. Only
  the RSS `<description>` summary is stored — sufficient for keyword
  filtering and a usable AI classification, but not for a full read.
- **Topic boundaries fuzzy at the edges.** POL_TONGDU vs CULTURE vs
  HK_MAC overlap on identity-charged cultural exchange articles.
  ARMS_SALES vs MIL_HARDWARE vs MIL_POLICY overlap on weapons-platform
  procurement debates. The analyst override is the load-bearing
  resolution layer.
- **Translation accuracy depends on a hand-curated glossary.**
  ~600 terms covering politicians, military assets, institutions in
  both Simplified and Traditional Chinese. Niche policy terminology
  outside the glossary is romanised by the model with no human-curated
  authority — usually correct, occasionally wrong on first use of an
  obscure organisation.
- **Pollster-direct scrapers are 25,000-char capped.** Long-form
  releases above that (rare; My-Formosa monthlies are 18k) get truncated.
  The cap was 10,000 until 2026-05; releases above 10k chars were
  silently losing back-half questions for months until that bug was
  diagnosed and fixed. Fix shipped 2026-05-27.

## Author

Built and edited by [Ed Park](https://github.com/Parkemoon). I read
Mandarin; the AI accelerates the reading, I verify the output.
Feedback and corrections welcome via issues.

## Licence

MIT.

---

→ See [`docs/architecture.md`](docs/architecture.md) for the full
data-flow diagram, API surface, and DB schema overview.
→ See [`docs/deployment.md`](docs/deployment.md) for setup,
infrastructure, and operational notes (systemd, Nginx, cron, RSSHub).
→ See [`CHANGELOG.md`](CHANGELOG.md) for the development history.
