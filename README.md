# Cross-Strait Signal

An open-source intelligence dashboard monitoring PRC-Taiwan cross-strait
dynamics through automated bilingual Chinese-language media analysis.
~30 active sources from both sides of the strait, scraped continuously
and run through a three-tier AI pipeline behind a human editorial gate.

**Live instance:** https://strait-signal.net
**GitHub:** https://github.com/Parkemoon/cross-strait-signal

---

## What it does

- Reads Chinese-language primary sources from the PRC, Taiwan, Hong Kong, Singapore, and the UK via RSS feeds and bespoke HTML and browser scrapers for sites without usable feeds.
- Classifies each article along three axes (topic, sentiment, urgency), extracts named entities and attributed quotes, and produces an English summary plus a translation of the key quote.
- Tracks parallel structured datasets that contextualise the news feed:
  - **Economy, Trade Access, and People:** bilateral trade with multi-reporter verification, trade-access asymmetry (what each side allows the other to ship), investment by industry, and bidirectional residency stocks and visitor flows.
  - **Military:** daily PLA incursion counts, ADIZ sector heatmaps, and a geocoded cross-strait military exercise tracker.
  - **Maritime (`Security > Maritime`):** Global Fishing Watch AIS presence for China Coast Guard, Taiwan Coast Guard Administration, and civilian fishing and non-fishing fleets across 12 maritime zones, paired with Sentinel-1 SAR dark-vessel radar detections and Taiwan CGA monthly and annual enforcement statistics.
  - **Diplomacy (`Politics > Diplomacy`):** a world choropleth where each country's fill is the aggregate of its government-tier statements on Taiwan and a separate pin layer carries non-official voices (lawmakers, former officials), making parliamentary divergence from executive posture visible at a glance.
  - **Cross-Strait Visits (`Politics > Visits`):** structured tracking of cross-strait political, party, academic, and municipal delegations, with side-by-side Taiwan and PRC media coverage for each trip.
  - **Taiwan Polling (`Politics > Polls`):** domestic pollster ingestion (My-Formosa, TVBS, ETtoday, MAC PDFs, and the NCCU long series) with canonical `question_key` series for cross-pollster trend charts.
  - **Positions & Legal Status (`Politics > Positions`):** a hand-curated reference dossier comparing official formulations, constitutional texts, and party stances across key actors.
- Enforces consistent bilingual romanisation (Wade-Giles/Tongyong for Taiwan, Hanyu Pinyin for the PRC, surname-first for Japanese officials) through a live Name Registry (`Admin > Names`) backed by Wikidata SPARQL, grounded web search, and ~1,100 canonical glossary entries.
- Holds every article and side-extracted candidate behind an analyst-approval gate. Nothing reaches the public feed until a human has confirmed or corrected the AI output.
- Publishes a public read-only build and a separate admin build; write controls do not exist in the public bundle.
- Re-scrapes every six hours via cron so approved articles typically reach the public feed within hours of original publication.

## Why it exists

Built for analysts, journalists, and researchers who need to read
Chinese-language primary sources on cross-strait dynamics but lack
the time or the language. There is no accessible, bilingual tool
that combines Chinese-language primary sources with structured
analytical output. English-language coverage of PRC-Taiwan dynamics
is slower, less detailed, and stripped of the linguistic nuance
that signals policy shifts. The standard alternative is hiring a
Mandarin-reading analyst.

This system processes Chinese government, military, and partisan media
in minutes, extracts structured intelligence, and flags escalation
signals. The AI layer accelerates analysis; native Mandarin reading
by the operator verifies it before publication.

The sentiment axis is deliberately **bidirectional**. Destabilising
moves from either side score equally: PLA exercises and DPP
sovereignty rhetoric register on the same instrument. This dashboard
measures cross-strait friction without picking a side.

## Methodology

### Topic taxonomy

24 bilaterally balanced categories across five functional groups:

- **Military and security (8):** `MIL_EXERCISE`, `MIL_MOVEMENT`, `MIL_HARDWARE`, `MIL_POLICY`, `ARMS_SALES`, `MARITIME_GREY`, `SEC_LAWFARE`, and `INFO_CYBER`
- **Cross-strait and sovereignty (5):** `POL_TONGDU`, `CROSS_STRAIT_REG`, `CULTURE`, `UNITED_FRONT_INTEG`, and `PARTY_VISIT`
- **Diplomacy and foreign relations (5):** `US_RELATIONS`, `INTL_RELATIONS`, `DIP_VISIT`, `INT_ORG`, and `DIP_SANCTIONS`
- **Domestic politics and Hong Kong/Macao (3):** `POL_DOMESTIC_TW`, `POL_DOMESTIC_PRC`, and `HK_MAC`
- **Economy, technology, and transport (3):** `ECON_TRADE`, `SCI_TECH`, and `TRANSPORT`

In November 2026 the taxonomy was reworked from its initial 28 categories into these 24 categories following an empirical audit of 25,213 approved articles using bilingual sentence embeddings (`paraphrase-multilingual-mpnet-base-v2`) and 5-fold stratified cross-validation. The rework retired catch-all speech buckets (`DIP_STATEMENT`), folded sparse economic sub-categories (`ECON_INVEST`, `ENERGY`) into `ECON_TRADE`, consolidated `US_PRC` and `US_TAIWAN` into `US_RELATIONS`, and introduced targeted categories that separate physical maritime grey-zone actions (`MARITIME_GREY`) from espionage prosecutions and judicial lawfare (`SEC_LAWFARE`), and Taiwanese entry or residency regulations (`CROSS_STRAIT_REG`) from PRC united-front integration drives (`UNITED_FRONT_INTEG`). Out-of-fold macro F1 improved from 0.675 under the 28-category schema to 0.755 under the 24-category schema. During event clustering (Step 4), articles with no `topic_secondary` that cluster alongside articles carrying a different primary topic inherit the cluster's secondary angle so multi-dimensional stories remain discoverable under both topic filters.

### Sentiment axis

`hostile` / `cooperative` / `neutral` / `mixed` plus a numeric score
from −1.0 (most hostile) to +1.0 (most cooperative). Measures how
positively or negatively the article frames the **opposing side of
the strait**, rather than geopolitical stability in the abstract. A PRC
source covering Taiwan is rated on how it portrays Taiwan; a Taiwan
source on how it portrays the PRC. Taiwan-US military cooperation is
scored neutral-to-hostile from the cross-strait frame, not
cooperative. KMT visits to the mainland score cooperative regardless
of how a Taiwanese voter feels about them.

`mixed` is the label for articles that genuinely carry both clearly
hostile and clearly cooperative framing, such as a PRC editorial
threatening Taiwan militarily while praising specific cross-strait
cultural exchanges. The numeric score in `mixed` cases sits near
zero, reflecting cancellation rather than absence of framing. It
exists as a distinct label so a downstream analyst can flag these
for closer reading rather than treating them as neutral factual
reporting.

Every directional score must include a `sentiment_reasoning` line
quoting the specific phrase or framing that drove it, providing an
audit trail for the analyst and constraining the model from emitting
a score without textual evidence. A deterministic post-extraction
check also flags reported-speech inversions (where an outlet quotes
a spokesperson from the other side and the model accidentally scores
the quoted speaker's hostility rather than the reporting outlet's
framing) to the human review queue.

### Source bias

Each source is hand-labelled with one of eight bias categories. The
labels reflect editorial reality rather than diplomatic hedging.

| Label | Meaning |
|-------|---------|
| `green` | Explicitly pro-independence editorial line |
| `green_leaning` | State-controlled under the current DPP government |
| `centrist` | Editorially independent |
| `china_centrist` | Editorially moderate but Beijing-accommodating (distinct from a PRC state organ) |
| `blue_leaning` | KMT-sympathetic but not party-aligned |
| `blue` | Consistent KMT-aligned editorial line |
| `state_official` | PRC state media or government organ |
| `state_nationalist` | PRC nationalist commentary |

The bias label is *not* used to weight or filter content. It exists
so a reader can interpret a hostile score from CNA differently than
the same score from Global Times. Source bias correlates with
sentiment by construction, and that correlation is part of the
signal rather than a flaw to be normalised away.

### Model strategy

Three tiers:

1. **Tier 1 (Gemini 3.1 Flash Lite).** Classifies every article that
   passes the directional keyword pre-filter. Outputs topic,
   sentiment, urgency, entities, key quote, and summary. Side-extracts
   poll questions, military exercise candidates, key figure
   statements, and third-country diplomatic stances where applicable.
   Runs at medium thinking depth through the Gemini Batch API by
   default (~50% token discount, collected within the same pipeline
   tick or the next).
2. **Tier 2 (Gemini 3.8 Flash).** Blindly re-reviews articles Tier 1
   flagged as escalation signals or `flash` urgency using shared
   classification and sentiment rules. The two tiers' sentiment,
   topic, and escalation calls are compared.
3. **Tier 3 (Human review queue).** Articles where Tier 1 and Tier 2
   disagree, or where post-extraction validation flags a sentiment
   band mismatch or reported-speech inversion, are held off the
   public feed until the analyst resolves them.

Before Tier 1 runs, Step 2m deterministically hides same-outlet
duplicate re-pushes (identical or near-identical content within 72
hours) so SEO rewrites do not consume API tokens, while preserving
cross-outlet syndication as analytical signal. The directional
keyword pre-filter then requires PRC/HK/SG sources to mention Taiwan
and Taiwan sources to mention the PRC, Hong Kong, or Macau, cutting
~80% of raw scrape volume before any LLM call.

Glossary injection (pre-analysis), entity canonical normalisation
(post-analysis), and the automated Name Registry lookup pass (Step
3f) handle two failure modes that bare models get wrong: romanising
Chinese names in Wade-Giles vs Hanyu Pinyin depending on the
person's jurisdiction (even when a Taiwanese figure is written in
Simplified Chinese by a PRC outlet), and attributing roles to former
officeholders based on stale training data. The Wikidata-sourced
current officials roster covers ~28 positions across TW/US/PRC/JP and
is refreshed via `scripts/refresh_officials.py`.

### Accuracy

<!-- Generated by scripts/accuracy_report.py — last 180 days,
     2026-05-05 → 2026-11-01. Re-run to refresh. -->

Snapshot over the last 180 days. The analyst engaged with 20,836 articles, approving 19,158 and dismissing 1,678 (8.1%). This is post-filter volume: the directional keyword pre-filter rejects ~80% of raw scraped articles upstream, before any API calls, so this figure represents the cross-strait-relevant subset rather than total scraping throughput.

### Override rates on approved articles

Every stored override is a real analyst reclassification: the admin UI only transmits override fields when the analyst explicitly chose to override in the review queue or selected a new value on the article card.

| Field                 | Override rate | Count |
|-----------------------|---------------|-------|
| Topic relabel         | 1.1% | 217 |
| Sentiment relabel     | 1.0% | 184 |
| Title translation     | 0.8% | 159 |
| Summary translation   | 0.8% | 158 |
| Key-quote translation | 0.0% | 7 |

Tier 1 and Tier 2 disagree on **3.1% of approved articles** (596 of 19,158 in window); all currently resolved.

### Where the analyst reclassifies TO

Categories the analyst most often promotes articles INTO. Reveals where the AI misses the framing on first pass. Only targets with ≥3 overrides shown.

| Target topic | Count |
|--------------|-------|
| US_RELATIONS | 83 |
| POL_TONGDU | 52 |
| INT_ORG | 12 |
| DIP_VISIT | 12 |
| HK_MAC | 10 |
| POL_DOMESTIC_TW | 9 |
| ARMS_SALES | 8 |
| CULTURE | 6 |
| MIL_POLICY | 5 |
| MARITIME_GREY | 4 |
| INTL_RELATIONS | 4 |
| SEC_LAWFARE | 3 |

### Per-topic dismissal rate

Of articles the analyst touched in each category, what fraction was dismissed? High dismissal indicates the model is surfacing weakly relevant articles. Categories with <20 touched articles in window are omitted.

| Topic | Approved | Dismissed | Dismiss % |
|-------|----------|-----------|-----------|
| POL_DOMESTIC_TW | 2474 | 381 | 13.3% |
| POL_TONGDU | 2334 | 169 | 6.8% |
| MIL_POLICY | 2137 | 217 | 9.2% |
| CULTURE | 1624 | 54 | 3.2% |
| US_RELATIONS | 1370 | 86 | 5.9% |
| CROSS_STRAIT_REG | 1310 | 114 | 8.0% |
| ECON_TRADE | 1063 | 113 | 9.6% |
| SEC_LAWFARE | 888 | 72 | 7.5% |
| INTL_RELATIONS | 896 | 53 | 5.6% |
| UNITED_FRONT_INTEG | 789 | 34 | 4.1% |
| INT_ORG | 725 | 42 | 5.5% |
| ARMS_SALES | 720 | 41 | 5.4% |
| MARITIME_GREY | 728 | 27 | 3.6% |
| MIL_MOVEMENT | 584 | 32 | 5.2% |
| DIP_VISIT | 556 | 33 | 5.6% |
| SCI_TECH | 424 | 57 | 11.9% |
| MIL_EXERCISE | 397 | 37 | 8.5% |
| POL_DOMESTIC_PRC | 307 | 27 | 8.1% |
| INFO_CYBER | 306 | 16 | 5.0% |
| MIL_HARDWARE | 276 | 30 | 9.8% |
| PARTY_VISIT | 277 | 19 | 6.4% |
| TRANSPORT | 231 | 15 | 6.1% |
| HK_MAC | 158 | 8 | 4.8% |
| DIP_SANCTIONS | 137 | 1 | 0.7% |

Two patterns stand out in the 180-day window:

- **`US_RELATIONS` and `POL_TONGDU` account for the majority of topic overrides.** Merging `US_PRC` and `US_TAIWAN` into `US_RELATIONS` removed the artificial split on triangular Washington-Beijing-Taipei stories, but articles where a military or economic headline carries a primary US policy or sovereignty framing still require analyst promotion (`US_RELATIONS` 83 overrides, `POL_TONGDU` 52, `INT_ORG` 12, `DIP_VISIT` 12, `HK_MAC` 10).
- **Overall dismissal sits at 8.1% (down from 13.3% in August 2026 and 22.2% in May 2026).** Tightened relevance gate rules and same-outlet deduplication cut upstream noise substantially. Domestic Taiwan politics (`POL_DOMESTIC_TW`, 13.3%) and dual-use technology (`SCI_TECH`, 11.9%) still carry the highest dismissal shares because articles with passing mainland references occasionally clear the keyword filter, whereas targeted operational categories such as `MARITIME_GREY` (3.6%), `UNITED_FRONT_INTEG` (4.1%), and `INFO_CYBER` (5.0%) show very low dismissal rates.

Re-run `python scripts/accuracy_report.py` for a fresh snapshot, or
`--markdown` to regenerate this block.

### Auditing the model layer

A system that runs Chinese-language political content through an AI
model owes its readers an answer to the obvious question: what would
a *Chinese* model do differently? In August 2026 the approved
corpus (15,400+ articles) was re-run through DeepSeek V4 Flash and
a stratified sample through Moonshot's Kimi K3 using the
byte-identical production prompt, on Western-hosted endpoints so the
comparison isolates the models' trained behaviour from any
serving-layer filtering, plus an originator-endpoint arm for
DeepSeek. A same-model Gemini rerun served as the noise-floor
control (re-running the production model reproduces its own stored
topic ~71% of the time, which sets the ceiling any cross-model
agreement should be judged against).

The censorship hypothesis failed on the structured analytical task.
Across PLA drills, 台獨 rhetoric, and united-front coverage, the
article sweep recorded zero refusals, no switching of Taiwanese
names into Hanyu Pinyin, ~99% retention of Taiwanese presidential
and ministerial titles, and entity-omission rates in English
summaries at the Gemini rerun noise floor (with politically
sensitive entities omitted *less* often than average). A companion
direct-question battery confirmed that refusals in Chinese models
are triggered by bare interrogative prompts on domestic PRC taboo
subjects rather than third-person analytical extraction on Taiwan.
The real differences on the article corpus were analytic: a stricter
relevance gate that discarded soft-topic articles while keeping
sovereignty material, and boundary disputes on the fuzziest topic
pairs. Following the November 2026 rework to the 24-category
taxonomy, the ongoing OpenRouter comparison sweep runs on **DeepSeek
V4.1 Flash** (`deepseek/deepseek-v4.1-flash-1017`) under the updated
24-category prompt alongside the frozen August 2026 V4 Flash
reference baseline.

## Sources

### Active Taiwan-side sources

| Source | Bias | Method |
|--------|------|--------|
| LTN (自由時報) — Politics / World / Business / Defence | green | RSS + HTML |
| CNA (中央社) — Politics / Mainland / International / Finance | green_leaning | RSS |
| YDN (青年日報) | green_leaning | HTML scraper |
| CT (中時) — Cross-Strait / Politics / Military / Opinion | blue | HTML scraper (headful Chromium) |
| UDN (聯合報) — Cross-Strait / Breaking / International / Business | blue | HTML scraper |

### Active PRC, HK, and international sources

| Source | Bias | Method |
|--------|------|--------|
| Xinhua (新华社) | state_official | RSS |
| People's Daily (人民日报台湾) | state_official | RSS via RSSHub |
| China News Service (中国新闻网) | state_official | RSS |
| TAO (国台办) | state_official | HTML scraper |
| China Taiwan Net (中国台湾网, TAO news portal) | state_official | HTML scraper |
| MFA (外交部) | state_official | HTML scraper |
| PLA Daily (解放军报) | state_official | HTML scraper |
| Global Times (环球时报台海) | state_nationalist | RSS via RSSHub |
| Guancha (观察者网) | state_nationalist | HTML scraper |
| Haixia Daobao (海峡导报) | state_official | HTML scraper |
| The Paper (澎湃新闻) | state_official | RSS via RSSHub |
| RTHK Greater China (after NSL) | state_official | RSS via RSSHub |
| Ming Pao (Cross-Strait / Editorial / Opinion) | china_centrist | RSS |
| Zaobao (Singapore) | centrist | RSS via RSSHub |
| BBC Chinese | centrist | RSS (summary only; body is Next.js CSR) |

YDN is labelled `green_leaning` because it is MND state media under
the current DPP executive. The label tracks the government rather
than the publisher and should be reclassified if the executive
changes party. The same logic applied to RTHK after the National
Security Law.

Not listed above: three pollster-direct scrapers (My-Formosa, TVBS
Poll Center, ETtoday Polls) plus the deterministic MAC 即時民調 PDF
parser that feed the poll tracker rather than the article feed, and
the structured-data scrapers behind the Economy, Trade Access,
People, Military, and Maritime tabs (MAC open data, UN Comtrade, HK
CSD, BOFT, MoF, NIA, MND daily briefings, CIFER, Global Fishing
Watch 4Wings AIS and Sentinel-1 SAR, and Taiwan CGA monthly/annual
PDFs). The in-app About page carries the full roster.

## Limitations

What the system cannot do, or does imperfectly, ordered by impact on
the editorial product:

- **Residual noise in domestic and tech categories.** `POL_DOMESTIC_TW`
  (13.3% dismissal), `SCI_TECH` (11.9%), `MIL_HARDWARE` (9.8%), and
  `ECON_TRADE` (9.6%) still require steady analyst filtering because
  articles that mention the mainland in passing clear the directional
  keyword pre-filter even when their substance is domestic or global
  supply-chain news. Read what survives analyst approval rather than
  treating raw scrape volume as signal.
- **US-relations and sovereignty framing still require the most manual
  topic overrides.** Consolidating `US_PRC` and `US_TAIWAN` into
  `US_RELATIONS` eliminated the split between Washington-Beijing and
  Washington-Taipei labels, but `US_RELATIONS` (83 overrides in 180
  days) and `POL_TONGDU` (52) remain the top categories into which
  the analyst promotes articles when the AI's first pass latches onto
  a surface military or trade angle.
- **The original AI classification is overwritten on manual override.**
  When the analyst overrides a topic, `ai_analysis.topic_primary` is
  updated in place and `analyst_notes.topic_override` records the
  chosen target, without preserving a separate column for the
  pre-override AI call. That allows exact measurement of override
  rates and reclassification targets, but not per-category precision
  before human review.
- **Source bias correlates with sentiment by construction.** Green
  sources rate PRC moves more hostilely than centrist ones; PRC state
  media rates Taiwan moves more hostilely under DPP than under KMT
  governments. This correlation is part of the signal, so comparing
  absolute scores across sources without controlling for alignment
  reads editorial baseline alongside event movement.
- **TW-in-PRC residency data is hand-curated.** PRC bureaus do not
  publish machine-readable endpoints for 台胞证 issuance, census
  cross-tabs, or settler floor stocks. The PRC-side series on the
  People tab are compiled from published PDF/HTML releases and lag
  6 to 12 months, whereas PRC-in-Taiwan series pull automatically
  from Taiwan NIA open data.
- **Sentinel-1 SAR maritime radar data lags ~2 months.** Global
  Fishing Watch publishes Sentinel-1 SAR dark-vessel detections
  roughly two months behind real time, whereas 4Wings AIS presence
  updates every few days. The Maritime tab displays scoped caveats
  whenever radar series or pre-2023 China Coast Guard AIS baselines
  are in view.
- **No Cantonese sources.** Hong Kong coverage relies on Standard
  Written Chinese outlets (RTHK, Ming Pao). Vernacular Cantonese
  commentary is not represented.
- **Officials roster covers ~28 positions.** Lower-level officeholder
  hallucinations remain possible when an article references someone
  outside `current_officials.json`. Wikidata refresh is run via
  `scripts/refresh_officials.py` after elections and cabinet
  reshuffles.
- **BBC Chinese body content is unavailable.** Article pages are
  Next.js client-side rendered and yield no article text to static
  fetching. Only the RSS `<description>` summary is stored, which is
  sufficient for keyword filtering and AI classification but not a
  full-text archive.
- **Topic boundaries remain adjacent on multi-angle stories.**
  `MARITIME_GREY` vs `MIL_MOVEMENT` on coast-guard patrols during
  joint drills, `POL_TONGDU` vs `UNITED_FRONT_INTEG` vs `CULTURE` on
  mainland exchange events, and `ARMS_SALES` vs `MIL_HARDWARE` on
  procurement debates require boundary judgment. Cluster-level
  `topic_secondary` propagation and analyst overrides handle the
  overlap.
- **Long-tail romanisation requires ongoing queue curation.** The
  committed glossary and canonical maps (~1,100 entries) plus the
  automated Step 3f Name Registry worker (Wikidata SPARQL + grounded
  search + Wade-Giles generation) resolve most recurring politicians
  and institutions, but newly surfaced Taiwanese local figures wait
  in the `Admin > Names` queue until an analyst approves their
  canonical spelling.
- **Pollster-direct scrapers are capped at 25,000 characters.**
  Long-form releases above that threshold (rare; My-Formosa monthly
  releases run ~18,000 characters) are truncated.

## Author

Ed Moon, bilingual English-Mandarin analyst and former Supervising
Editor at TaiwanPlus. I read Mandarin; the AI accelerates the
reading and I verify the output. Feedback and corrections welcome
via GitHub issues.

Substack: [The East and Back](https://theeastandback.substack.com)

## Licence

[GPL-3.0](LICENSE)

---

→ See [`docs/architecture.md`](docs/architecture.md) for the full
data-flow diagram, API surface, and DB schema overview.
→ See [`docs/deployment.md`](docs/deployment.md) for setup,
infrastructure, and operational notes (systemd, Nginx, cron, RSSHub).
→ See [`CHANGELOG.md`](CHANGELOG.md) for the development history.
