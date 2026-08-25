# Coast Guard Tracker — scoping note

*Drafted 2026-08-25. Status: DESIGN, nothing built. Decision points marked ⚑.*

> ## Update 2026-08-25 — design CONFIRMED against the live APIs (GFW-primary)
>
> **GFW is the primary source, not the enrichment.** The 4Wings `report` endpoint on `public-global-presence:latest` (resolves to v4.0) with `spatial-resolution=HIGH` (0.01° ≈ 1 km cells), `temporal-resolution=DAILY`, `group-by=VESSEL_ID` returns **per-hull, per-day, per-cell presence hours with entry/exit timestamps, MMSI, shipName, flag, vesselType** for ANY polygon, 2017 → ~5 days ago. Test: Kinmen box (118.05–118.65°E, 24.20–24.65°N), March 2024 (AMTI's peak month) → 114,541 vessel-day-cells, of which **1,796 rows = 21 CCG hulls**: CHINACOASTGUARD14608 present all 30 days (671 h), 14521 (25 d), 14609 (23 d), 14604, 14515, 14603, 2202, 2203, 2101, 2201… — the Fujian 14xxx series and the 2xxx cutters AMTI describes. This IS the backfill: the whole 2020–2026 series AMTI and CommonWealth built on commercial data is reproducible at daily/1 km resolution for $0. `filters[0]="flag in ('CHN')"` works (SQL-ish; `vesselType` is NOT filterable — filter client-side).
>
> **Rosters for all four flags resolve from the identity index** via `vessels/search?where=…` (SQL-ish; cannot be combined with `query`): CCG `flag='CHN' AND shipname LIKE '%COAST%' OR '%HAIJING%'` → 1,763 identity rows (~107 distinct hulls by name-match, 27 transmitting since 2025-01); **Taiwan CGA** hulls broadcast as `CG####` / `CG-###` / `CG5002 HSINCHU` (`flag='TWN' AND shipname LIKE 'CG%'` → 68 rows, e.g. CG5001, CG5002 HSINCHU, CG5005, CG603/605/610/611, CG-126/127/129, CG-1006/1007); **JCG** hulls resolve by class name (MIZUHO 431001410, AKITSUSHIMA 431004594/431005736 — build the list from the JCG fleet list, no name pattern); **USCG** as `CG …` / `CGC …` / `USCGC …` (425 rows, e.g. CGC MIDGETT 303868000 — Pacific-deployed cutters do broadcast).
>
> **Identity-manipulation findings, before any pipeline exists:** IMO 9756028 (5901-class) = MMSI 413482360 *ZHONGGUO HAIJING3901* 2015→2025-05-23, then MMSI 413875411 **"CAPTAIN ASLEEP"** 2025-05→2026-08; CHINACOASTGUARD14513 broadcasting under MMSI **766688888** (Venezuelan MID) in March 2024; CHINACOASTGUARD14057 under 431875271 (**Japanese MID**) 2024-03→2025-05; a `CHINAGUARDCOAST13022`. GFW's registry fusion catches these; the tracker should surface them as a first-class "identity anomalies" list.
>
> **Events API**: per-vessel queries are permitted (returned 0 for the CCG hulls tried — GFW computes loitering/port/gap events mainly for fishing/carrier fleets); region-filtered event queries return 403 on this token. Don't rely on it.
>
> **AISStream** (live) — smoke tests connect; 5-min sample: 74 vessels, ~22 msg/min, all inside 24.5–27.2°N / 120.7–122.6°E (north-Taiwan terrestrial receivers), nothing near Kinmen. 24 h run started 10:48 UTC 2026-08-25. Demoted to: live "today" layer where coverage exists + JCG/USCG transit spotting; the series and history come from GFW at a ~5-day lag.
>
> **Gotchas**: GFW gateway 403s (Cloudflare 1010) on Python's default User-Agent — send a real UA; `datasets/` listing needs `offset`; `:latest` keys the response by the resolved version (`public-global-presence:v4.0`) — read the first key, don't hard-code. Existing incident-level baseline to cross-check against: George Mason **Taiwan Security Monitor — China Coast Guard Incident Tracker** (tsm.schar.gmu.edu).
>
> **Revised architecture** (replaces §5): nightly GFW pull per zone polygon (daily/HIGH/VESSEL_ID, ~5-day lag) → `coast_guard_presence` (date, zone, flag, hull, hours, cells) filtered by roster + name regex → events derived from presence in restricted/prohibited polygons (analyst-gated) → encounter pass on same-day/same-cell CCG×{CGA,JCG,USCG} → API + Military tab; one-shot backfill 2017→. AISStream listener optional, phase 2. Cost still $0; effort drops to **~4 sittings** because there is no always-on service and no roster-bootstrap queue.

## 1. What we're building

A quantitative series for the one grey-zone actor that broadcasts its position on purpose: **coast guard presence around Taiwan**, from AIS. Four flags — China (CCG), Taiwan (CGA), Japan (JCG), US (USCG) — so the product reads as an *encounter* picture, not a China-only count.

Product, in order of ambition:

1. **Daily ship-days by zone and flag** → a `coast_guard_presence` table feeding the Military tab next to `pla_incursions` (same KPI strip / daily bars / zone heatmap treatment the ADIZ data already gets). Gives `LEGAL_GREY` a number it currently lacks.
2. **Incursion events** — a CCG hull entering Kinmen/Matsu restricted or prohibited waters, or crossing the median line, with timestamp + hull — a `coast_guard_events` table with the same editorial gate as `military_exercises` (pending → approved), rendered as pins on the existing Taiwan Strait map.
3. **Encounter overlay** — CGA/JCG/USCG hulls within N nm of a CCG hull at the same time. This is the CommonWealth/CSIS story and the split-screen angle: a feed article claiming "four CCG ships expelled" can be checked against the day's track data.

Reference work we are reproducing, not inventing: AMTI *A New Normal for the CCG at Kinmen and Matsu* (Dec 2024: 156 unique CCG hulls, 2,012 restricted/prohibited-water entries 2020–24, peak March 2024); CommonWealth/CSIS Futures Lab *Broken Chain* (Aug 2026: 140 CCG hulls, 1.8bn positions, drift from SW/median line to a ring around the island); CSIS *Signals in the Swarm* (Oct 2025: militia go-dark/go-bright framework on Spire data via GA Optix + Global Fishing Watch). Taiwan's own tally: CGA cites **117 CCG incursions into Kinmen restricted waters Feb 2024 → May 2026**, typically 4-ship formations ~4×/month (LTN, 2026).

## 2. Data sources — what's actually available

| Source | Cost | History | Positions per vessel? | Verdict |
|---|---|---|---|---|
| **AISStream.io** (websocket) | Free, no card | **None — live only**, no replay | Yes, full PositionReport + ShipStaticData | **Primary feed.** Bounding-box + up-to-200-MMSI filters, 3 connections/account. We must run our own always-on listener and build history from day one. Sept 2026: bandwidth caps on uncompressed connections — use `permessage-deflate`. Coverage in the strait is terrestrial-receiver dependent — **unverified** (⚑ needs a key + a 24h test). |
| **Global Fishing Watch API** | Free for non-commercial (we qualify: open-source, public good) | 2017 → ~5 days ago | **Not as tracks** — public v3 exposes Vessels (identity, all types), Events (fishing / encounter / loitering / port visit / AIS-gap), 4Wings (raster presence), Insights. Per-vessel lat/lon series is not a public endpoint as far as the docs show (⚑ confirm via key — GFW's map UI draws tracks, the API may gate them). | **Secondary.** Use Vessels API to resolve MMSIs → identity/flag, Events API for AIS-gap ("go dark") and loitering events on our hull list, 4Wings presence raster for the backfill picture. |
| MarineTraffic / VesselFinder / MyShipTracking | Web free; API paid | Paid | Web only | Manual lookup of a single hull (photos, IMO, class). Not a pipeline. |
| Spire / Starboard / Windward / Kpler | Commercial | Full | Yes | What AMTI/CSIS/CW used. Out of scope unless a research partner appears. |
| aisHub | Free **if you contribute a receiver** | None | Yes | Not for us (no antenna). |

**Consequence:** no free source gives us the 2020–2026 back-history AMTI and CW analysed. Our series starts the day the listener starts. The AMTI/CW/CGA numbers become the *published baseline* we chart against, not something we reproduce.

## 3. Hull roster (largely solved by GFW — see update at top)

No public MMSI list for any of the four coast guards was found (AMTI publishes militia lists, not CCG). Bootstrap from AIS itself:

- **MID prefixes**: China 412/413/414; Taiwan 416; Japan 431/432; US 338, 366–369.
- **Static-data name patterns** (from live `ShipStaticData` messages inside the bbox): CCG hulls broadcast as `CHINA COAST GUARD` / `CHINACOASTGUARD####` / `HAIJING ####` / `ZHONGGUOHAIJING`, ship type *Law enforcement*; CGA as `CG ###` / class names (Anping, Chiayi…), MID 416; JCG as class or pennant names (e.g. *Mizuho* MMSI 431001410, `PL`/`PLH` pennants), MID 431; USCG as `USCGC …` / `CGC`.
- Process: listener stores every static-data message with type=law-enforcement/military or a name match → weekly roster review in an admin queue (the `military_exercises` review pattern) → approved hulls go into a `coast_guard_vessels` table with flag, class, hull number, IMO, aliases. Roster is hand-curated after bootstrap, like `key_figures.json`.
- Cross-check hulls against MarineTraffic/VesselFinder pages (Navigator's hits) and Wikipedia class lists.
- Known limits: CCG rotates or omits MMSIs on some hulls (CGA notes AIS switched off during incursions); the 5901-class broadcasts under names like `CHINACOASTGUARD5901`. Expect the roster to grow for months.

## 4. Zone geometry

- **Kinmen / Matsu restricted + prohibited waters**: legal basis 兩岸人民關係條例 §29; MND 公告 1992-10-07, revised 1998-06-24, 2004-06-07, 2018-05-25. Published as **distance bands from baselines**, not lat/lon: Kinmen prohibited = 2,000 m (Daqian/Erdan), 4,000 m (Dongding, Wuqiu), 4,000–8,000 m (main island); restricted = 4,000–6,000 m; Matsu prohibited 4,000 m, restricted 4,000–6,000 m; Taiping 4,000 / 4,000–6,000 m. ⚑ We build polygons by buffering the island coastlines (Natural Earth is too coarse at this scale — use OSM coastline or the Kinmen 海岸地區範圍圖 PDF as the baseline source). Accept ±300 m error and say so.
- **Median line**: the conventional coordinates (the 1955 "Davis line", 2 waypoints) — already discussed in the Positions concept entry; MND publishes no polygon.
- **Taiwan 24 nm contiguous zone / 12 nm territorial sea** from the ROC baseline announcement (內政部 1999/2009) — public.
- **East-coast box, Pratas 24 nm, Bashi Channel**: our own analytical zones, labelled as such.
- Existing asset: `scripts/build_taiwan_strait_map.py` + the ADIZ sector SVG; Leaflet already used for exercises/diplomacy. Zones become a GeoJSON under `frontend/public/geo/`.

## 5. Architecture (fits the existing patterns)

```
AISStream websocket (bbox ≈ 21–27°N, 116–124°E; deflate)
    → ais_listener.py  (NEW: long-running systemd service, NOT a cron step;
                        reconnect/backoff; writes raw PositionReport rows
                        for MMSIs in the roster + ShipStaticData for
                        roster candidates; ~1 row / hull / minute)
    → ais_positions  (append-only; prune to 1 position / hull / 5 min after 30 d)
    → pipeline step (6-hourly, existing run_pipeline.py):
         - point-in-polygon against zones → coast_guard_presence (date, flag, zone, ship_days, hulls_json)
         - state machine per hull → coast_guard_events (enter/exit restricted|prohibited|median-line;
           status=pending, analyst gate)
         - proximity pass → encounters (CCG × {CGA,JCG,USCG} within 5 nm / same 30-min bin)
         - GFW Events API pull for roster hulls → AIS-gap events (go-dark) annotated on the timeline
    → /api/military/coast-guard/{summary,daily,events,encounters,vessels}
    → MilitaryTab: third section "Coast Guard" — KPI strip, daily bars by flag, zone heatmap,
      map with hull tracks for a selected day, review queue for events + roster
    → check_scraper_health.py: listener-liveness check (newest ais_positions row < 2 h)
```

DB: one migration `0008_coast_guard.sql` (four tables + indexes), mirrored in `schema.sql`.

## 6. Effort and cost

- Money: **$0** at this scope (AISStream free, GFW free non-commercial, no AI calls — this is deterministic geometry).
- Disk: ~30 hulls in-bbox × 1 pos/min ≈ 45k rows/day raw; with 5-min thinning after 30 d, <1 GB/yr.
- Build, in sittings: (1) listener + raw store + roster bootstrap queue — 1; (2) zones GeoJSON + presence/events pipeline + API — 1–2; (3) Military tab section + review queue — 1–2; (4) GFW enrichment + encounter pass — 1. **≈ 5 sittings** to a first public section, staged behind `!READ_ONLY` like Positions until the roster is trustworthy.
- Steady state: roster review ~weekly; event approvals daily alongside exercises.

## 7. Risks / honest caveats

- **Coverage** is the make-or-break unknown: AISStream depends on volunteer terrestrial receivers; Kinmen–Xiamen is well covered (dense coast), the east coast and Pratas may not be. Satellite AIS is what the commercial vendors add. Test before building.
- **No back-history**: the chart starts at launch. We should say so on the card and chart the AMTI/CGA baselines as reference lines.
- **AIS is self-reported**: spoofing and switch-offs are part of the behaviour (CSIS's whole point). Presence counts are a floor; "go-dark" events are a signal in themselves, not missing data — show them.
- **Roster false positives** (a CCG-named fishing vessel, MMSI reuse) → that is what the analyst gate is for; never auto-approve an event.
- **Non-commercial terms**: GFW is fine for the open dashboard; if the Substack ever paywalls, re-read GFW's terms.

## 8. Next actions

1. ⚑ **Ed**: create a free AISStream.io API key and a GFW API token (both self-serve; keys go in `.env` as `AISSTREAM_API_KEY`, `GFW_API_TOKEN` — never in chat).
2. **Claude**: 24-hour bbox coverage test on staging (count distinct MMSIs by MID prefix + law-enforcement type, by sub-area) — go/no-go on the east coast and Pratas; check whether GFW's Vessels API resolves the CCG hulls we see.
3. ⚑ **Ed**: decide zone set for v1 (proposal: Kinmen restricted+prohibited, Matsu restricted+prohibited, median line, 24 nm contiguous zone, east-coast box, Pratas 24 nm).
4. Then build in the order in §6, on staging.


---

# Part B — CGA enforcement: the mirror series (scoped 2026-08-25; **BUILT same day** — migration 0009, `cga_stats_scraper.py`, backfill, `/enforcement` endpoint + summary KPI; 5 yearbooks + 9 monthly reports ingested)

**Why.** Ed's challenge: the tracker as built counts PRC hulls inside lines Taiwan drew — one-directional by construction. The Taiwan-side coercive action in the same waters is the Coast Guard Administration's enforcement against PRC vessels: expulsions, detentions, fines, confiscations — thousands of boats a year, and the Feb 2024 Kinmen deaths were a CGA pursuit. Putting that series next to `coast_guard_presence` on the same chart, with dual-frame copy (Taipei: 越界/驅離 · Beijing: 兩岸漁民傳統作業 / 粗暴對待), is what makes the section bi-directional.

## B1. What the CGA publishes (verified 2026-08-25)

| Source | What | Cadence / depth | Format | Parse |
|---|---|---|---|---|
| **績效統計月報** (monthly performance report) — CGA site, `lp?ctNode=<month node>&mp=999`, chapters as `ct?xItem=…` pages | Ch. 捌 取締非法越區捕魚: **表8-1 by month** (cases; vessels total / 大陸籍 / 外國籍 / 無籍; split 扣留 detention vs 驅離 expelling; annual rows 2013→ plus each month of the current year), **表8-2 by unit**, **表8-3 by county** (金門縣 / 連江縣=Matsu / 澎湖縣 / …). Ch. 拾壹 其他海巡績效: **表11-1** incl. 取締越界非捕魚船舶 (dredgers and other non-fishing trespass). | Monthly; latest = 115年06月 (June 2026), released ~late July. Homepage sidebar links the latest ~5 months; the parent index node (8757) 404s to curl — ⚑ discover by walking the sidebar + remembering seen nodes, or by the newer-month node-id monotonicity. | PDF, one table per file, `public/Attachment/f<13-digit>.pdf` | `pdfplumber.extract_tables()` returns clean cells; digits are space-split in `extract_text()` ("1 ,141") — use the table cells, strip spaces/commas. Older reports (≤2024) were ONE narrative PDF (海巡績效統計概況) with the same Table 8 inside — the parser needs both shapes (⚑ find the cut-over). |
| **海巡統計年報** (yearbook) 110–114年 (2021–2025), same chapter/table layout | Annual backfill: 表8-1 carries 2013→ annual totals in every edition; 表8-3 per-county per year | Yearly | PDF | same |
| **護永專案 summary page** (`ct?xItem=101246`, updated 2026-04-20) | 2016H2→2026H1 annual: 驅離 (×10), 扣留, 裁罰, 罰鍰 NT$m, 沒入 for PRC fishing vessels; separate table for foreign vessels | Semi-annual | **Images** (PNG/JPG) | Transcribed by eye today (below) — validation set, not a scrape target |

**Transcribed 護永專案 series (PRC fishing vessels, 2016-07 → 2026-06)** — 驅離 / 扣留 / 裁罰 / 罰鍰 NT$m / 沒入:
2016H2 488/53/47/45.9/5 · 2017 718/77/49/43.0/22 · 2018 1,293/86/61/60.9/23 · 2019 1,003/81/67/54.8/20 · 2020 1,697/19/13/14.9/6 · 2021 1,786/28/23/36.1/5 · 2022 1,271/20/19/16.5/1 · 2023 1,009/28/26/22.0/2 · 2024 1,135/9/7/7.0/1 · 2025 907/15/4/4.0/10 · 2026H1 385/11/3/2.7/8 · total 11,692/427/319/307.8/103.
Yearbook 表8-1 annual PRC 驅離 (calendar years): 2013 1,324 · 2014 2,334 · 2015 1,991 · 2016 1,282 · 2017 718 · 2018 1,293 · 2019 1,003 · 2020 1,697 · 2021 1,786 · 2022 1,271 · 2023 1,006 · 2024 1,135 · 2025 907 (consistent with the image series where they overlap). PRC 扣留: 2013 988 · 2014 648 · 2015 85 … 2025 15 — the 2013→2015 collapse in detentions (988 → 85) with expulsions steady is itself a policy story (the shift from seizure to expulsion).
Dredgers: 4,649 expelled 2018–2020 (Audit report via LTN), 86% at Taiwan Shoal (Penghu) — lives in 表11 取締越界非捕魚船舶, not in Table 8.

**Not published as statistics**: CCG incursion counts (the "117 since Feb 2024" figure is press-release prose) — that side stays with the GFW series.

## B2. Design

- **Table** `cga_enforcement` (period `YYYY-MM` or `YYYY` with `granularity`, `region` = national | county code, `category` = fishing_prc | fishing_foreign | fishing_stateless | nonfishing_trespass, `cases`, `expelled`, `detained`, `fined_vessels`, `fines_ntd_m`, `confiscated`, `source` = monthly | yearbook | manual, `source_url`, unique on (period, region, category, source)). Deterministic, no AI, no review gate (official statistics) — same status as `economic_indicators`.
- **Scraper** `scraper/scrapers/cga_stats_scraper.py`: (1) homepage sidebar → newest month node; (2) chapter 捌 + 拾壹 pages → attachment PDFs; (3) pdfplumber tables → rows for the current year's months (national) + 表8-3 county rows for the year-to-date; (4) upsert. Pipeline step next to Step 2n (monthly cadence — skip unless a new node appears). Health check: `cga_enforcement` newest period ≤ 60 days old.
- **Backfill** `scripts/backfill_cga_enforcement.py`: yearbooks 110–114 → annual 2013→ national + county; monthly 2021→ from whichever monthly reports remain reachable (⚑ index discovery); the 護永專案 transcription above seeded as `source='manual'` for 2016H2→ with the image URL as `source_url`.
- **API** `/api/military/coast-guard/enforcement?region=&months=` + fold into `summary` (a second KPI: "PRC vessels expelled by CGA, trailing 12 months").
- **Frontend**: the Coast Guard section opens with a **paired chart** — left: CCG hull-days in Kinmen/Matsu waters (GFW); right: PRC vessels expelled/detained by the CGA, Kinmen + Matsu counties (表8-3) — same time axis, same visual weight, per [[feedback-analyst-charts]] (no manufactured composite, symmetric summarisation). Zone cards carry both readings (Taipei / Beijing). Vocabulary in the UI: "presence" and "enforcement", not "incursion" and "expelled", except inside quoted official figures.
- **Effort**: ~2 sittings (scraper + backfill + API = 1; frontend pairing folded into the Coast Guard frontend sitting).

## B3. Caveats to carry into the UI
- CGA counts are *enforcement events*, a function of patrol effort as much as of PRC behaviour (2020's spike coincided with the dredger surge AND a CGA fuel budget of NT$600m).
- Counties ≠ zones: 表8-3 gives 金門縣 / 連江縣, not the restricted-waters polygons — the pairing is "same waters, different bookkeeping".
- Neither side publishes the other's frame: the CGA has no "PRC coast guard incursions" table and the CCG publishes nothing at all — the tracker's two halves come from GFW (behaviour) and the CGA (enforcement), and the Beijing reading is copy, not data.
