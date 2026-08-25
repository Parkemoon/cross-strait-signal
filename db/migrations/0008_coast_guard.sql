-- Coast Guard tracker (Phase 2e, 2026-08-25). Four-flag coast-guard presence
-- around Taiwan from AIS via Global Fishing Watch's 4Wings presence report:
-- China CCG, Taiwan CGA, Japan JCG, US USCG. See COAST_GUARD_TRACKER_SCOPE.md.
--
-- No editorial gate on presence rows: they are deterministic aggregates of a
-- third-party dataset (GFW), not AI extractions. The roster IS reviewable —
-- a mis-classified hull (a fishing boat named "COAST GUARD") is the failure
-- mode, so coast_guard_vessels.status lets an analyst confirm/reject.

CREATE TABLE IF NOT EXISTS coast_guard_vessels (
    mmsi            TEXT PRIMARY KEY,           -- self-reported MMSI (identity key in GFW)
    vessel_id       TEXT,                       -- GFW vessel id (stable across MMSI changes? no — per identity)
    name            TEXT,                       -- latest AIS shipname
    flag            TEXT,                       -- ISO3 as reported (may be spoofed — see anomaly_flags)
    force           TEXT NOT NULL CHECK (force IN ('CCG','CGA','JCG','USCG')),
    hull_no         TEXT,                       -- parsed from name where present (CCG 14608, CGA 5002, ...)
    imo             TEXT,
    callsign        TEXT,
    first_seen      TEXT,                       -- GFW transmissionDateFrom (date)
    last_seen       TEXT,                       -- GFW transmissionDateTo (date)
    source          TEXT NOT NULL DEFAULT 'gfw_identity'
                        CHECK (source IN ('gfw_identity','presence','manual')),
    status          TEXT NOT NULL DEFAULT 'auto'
                        CHECK (status IN ('auto','confirmed','rejected')),
    anomaly_flags   TEXT,                       -- JSON array: ['mid_mismatch','name_change',...]
    notes           TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per (day, zone, hull): hours of AIS presence inside the zone
-- polygon (sum over GFW 0.01° cells), cell count, mean position, first entry
-- / last exit timestamps. Aggregated from the 4Wings report — GFW is the
-- source of the point-in-polygon, we never see raw positions.
CREATE TABLE IF NOT EXISTS coast_guard_presence (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,                  -- YYYY-MM-DD (UTC)
    zone_id     TEXT NOT NULL,                  -- data/coast_guard_zones.geojson feature id
    mmsi        TEXT NOT NULL,
    force       TEXT NOT NULL CHECK (force IN ('CCG','CGA','JCG','USCG')),
    name        TEXT,
    flag        TEXT,
    hours       REAL NOT NULL,
    cells       INTEGER NOT NULL,
    lat         REAL,                           -- hours-weighted mean cell centre
    lon         REAL,
    entry_ts    TEXT,
    exit_ts     TEXT,
    vessel_id   TEXT,
    UNIQUE (date, zone_id, mmsi)
);
CREATE INDEX IF NOT EXISTS idx_cg_presence_zone_date ON coast_guard_presence(zone_id, date);
CREATE INDEX IF NOT EXISTS idx_cg_presence_mmsi_date ON coast_guard_presence(mmsi, date);
CREATE INDEX IF NOT EXISTS idx_cg_presence_date ON coast_guard_presence(date);

-- Pull ledger: one row per (zone, period) request, so the backfill is
-- resumable and the health check can see the newest successful pull.
CREATE TABLE IF NOT EXISTS coast_guard_pulls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id       TEXT NOT NULL,
    period_start  TEXT NOT NULL,
    period_end    TEXT NOT NULL,                -- inclusive
    rows_total    INTEGER,                      -- rows GFW returned (all vessels, post server-side filter)
    rows_kept     INTEGER,                      -- coast-guard rows after classification
    status        TEXT NOT NULL CHECK (status IN ('ok','error')),
    error         TEXT,
    pulled_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cg_pulls_zone ON coast_guard_pulls(zone_id, period_end);
