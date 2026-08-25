# Coast Guard Tracker — scoping note

*Drafted 2026-08-25. Status: DESIGN, nothing built. Decision points marked ⚑.*

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

## 3. Hull roster (the hard part)

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
