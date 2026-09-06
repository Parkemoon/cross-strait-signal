-- Maritime civilian-fleet + dark-vessel layer (Phase 2g, 2026-09-04) — the
-- "militia / dredger" layer of the Maritime tab, named after what is actually
-- measured. Three feeds, all deterministic third-party aggregates (Global
-- Fishing Watch), no editorial gate:
--
--   maritime_civil_daily     per (day, zone, flag, class) hull-days for the
--                            NON-coast-guard rows of the SAME 4Wings presence
--                            pull Step 2n already makes (zero extra API cost).
--                            CHN + TWN flags only — the big zones are pulled with
--                            a flag filter, so other flags are not comparable
--                            across zones.
--   maritime_civil_presence  per-hull rows for the subset worth naming: every
--                            CHN hull in the small zones (Kinmen / Matsu /
--                            Pratas / Taiwan Bank), CHN non-fishing ("OTHER")
--                            hulls everywhere, and any hull on the published
--                            militia roster (data/maritime_militia_roster.json)
--                            wherever it appears.
--   maritime_sar_daily       Sentinel-1 SAR vessel detections per (day, zone,
--                            matched-to-AIS?, flag, class) from GFW's
--                            public-global-sar-presence dataset. Unmatched
--                            detections = radar sees a hull, no AIS matched —
--                            the ceiling that pairs with the AIS-visible floor.
--
-- GFW's presence vesselType is COARSE (FISHING / CARGO / OTHER / PASSENGER /
-- GEAR / SEISMIC_VESSEL); dredgers, tugs and supply ships are all OTHER and
-- GFW's public identity index exposes nothing finer (probed 2026-09-04), so
-- no row here claims "dredger". Militia identification is roster-based only
-- (AMTI/C4ADS appendices) — a documented public identification, never ours.

CREATE TABLE IF NOT EXISTS maritime_civil_daily (
    date          TEXT NOT NULL,                  -- YYYY-MM-DD (UTC)
    zone_id       TEXT NOT NULL,                  -- data/coast_guard_zones.geojson feature id
    flag          TEXT NOT NULL,                  -- ISO3 as broadcast (CHN / TWN)
    vessel_class  TEXT NOT NULL,                  -- GFW coarse vesselType, upper-case; '' -> 'UNKNOWN'
    hull_days     INTEGER NOT NULL,               -- distinct MMSIs present that day
    hours         REAL NOT NULL,                  -- sum of GFW hour-cells
    UNIQUE (date, zone_id, flag, vessel_class)
);
CREATE INDEX IF NOT EXISTS idx_mcd_zone_date ON maritime_civil_daily(zone_id, date);
CREATE INDEX IF NOT EXISTS idx_mcd_date ON maritime_civil_daily(date);

CREATE TABLE IF NOT EXISTS maritime_civil_presence (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL,
    zone_id       TEXT NOT NULL,
    mmsi          TEXT NOT NULL,
    flag          TEXT,
    vessel_class  TEXT NOT NULL,
    name          TEXT,
    hours         REAL NOT NULL,
    cells         INTEGER NOT NULL,
    lat           REAL,                           -- hours-weighted mean cell centre
    lon           REAL,
    entry_ts      TEXT,
    exit_ts       TEXT,
    vessel_id     TEXT,
    UNIQUE (date, zone_id, mmsi)
);
CREATE INDEX IF NOT EXISTS idx_mcp_zone_date ON maritime_civil_presence(zone_id, date);
CREATE INDEX IF NOT EXISTS idx_mcp_mmsi_date ON maritime_civil_presence(mmsi, date);
CREATE INDEX IF NOT EXISTS idx_mcp_date ON maritime_civil_presence(date);

-- One row per hull that has a per-hull presence row. militia_* columns are
-- filled ONLY from the published roster file (source + citation carried on
-- the row) — there is no analyst "confirm" here because nothing here is
-- verifiable from a desk (see feedback: only answerable review questions).
CREATE TABLE IF NOT EXISTS maritime_civil_vessels (
    mmsi             TEXT PRIMARY KEY,
    vessel_id        TEXT,
    name             TEXT,
    flag             TEXT,
    vessel_class     TEXT,
    first_seen       TEXT,
    last_seen        TEXT,
    militia_source   TEXT,                        -- short label, e.g. 'AMTI/C4ADS 2021 App. A'
    militia_url      TEXT,
    militia_name_zh  TEXT,
    militia_port     TEXT,
    notes            TEXT,
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS maritime_sar_daily (
    date          TEXT NOT NULL,
    zone_id       TEXT NOT NULL,
    matched       INTEGER NOT NULL CHECK (matched IN (0, 1)),  -- GFW matched the detection to an AIS identity
    flag          TEXT NOT NULL,                  -- '' when unmatched or unknown
    vessel_class  TEXT NOT NULL,                  -- '' when unmatched
    detections    INTEGER NOT NULL,               -- SAR detections (per satellite pass, NOT hull-days)
    vessels       INTEGER NOT NULL,               -- distinct matched vessel ids (0 when unmatched)
    UNIQUE (date, zone_id, matched, flag, vessel_class)
);
CREATE INDEX IF NOT EXISTS idx_msd_zone_date ON maritime_sar_daily(zone_id, date);
CREATE INDEX IF NOT EXISTS idx_msd_date ON maritime_sar_daily(date);

-- Pull ledger for both feeds (resumable backfill + health check), one row per
-- (kind, zone, period) request. 'civil' rows are logged by the presence pull
-- that feeds Step 2n; 'sar' rows by the SAR pull (Step 2p).
CREATE TABLE IF NOT EXISTS maritime_pulls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT NOT NULL CHECK (kind IN ('civil', 'sar')),
    zone_id       TEXT NOT NULL,
    period_start  TEXT NOT NULL,
    period_end    TEXT NOT NULL,                  -- inclusive
    rows_total    INTEGER,
    rows_kept     INTEGER,
    status        TEXT NOT NULL CHECK (status IN ('ok', 'error')),
    error         TEXT,
    pulled_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_maritime_pulls_kind_zone ON maritime_pulls(kind, zone_id, period_end);
