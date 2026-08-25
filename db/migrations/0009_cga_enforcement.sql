-- CGA enforcement statistics (Phase 2e, Part B — the bi-directional mirror of
-- coast_guard_presence). Taiwan's Coast Guard Administration publishes, in its
-- monthly 績效統計月報 and annual 海巡統計年報, the vessels it EXPELLED (驅離)
-- and DETAINED (扣留) for trespass fishing, split by nationality (大陸籍 /
-- 外國籍 / 無籍) and by county (金門縣, 連江縣=Matsu, 澎湖縣, ...). Official
-- statistics: deterministic parse, no AI, no review gate — same status as
-- economic_indicators. See COAST_GUARD_TRACKER_SCOPE.md Part B.

CREATE TABLE IF NOT EXISTS cga_enforcement (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    period        TEXT NOT NULL,          -- 'YYYY' (annual) or 'YYYY-MM' (month)
    granularity   TEXT NOT NULL CHECK (granularity IN ('year','month','half')),
    region        TEXT NOT NULL,          -- 'TW' national, or county name as printed (金門縣, 連江縣, 澎湖縣, ...)
    category      TEXT NOT NULL CHECK (category IN ('fishing_prc','fishing_foreign','fishing_stateless','fishing_all')),
    cases         INTEGER,                -- 案件數 (only meaningful for fishing_all)
    expelled      INTEGER,                -- 驅離 vessels
    detained      INTEGER,                -- 扣留 vessels
    fined_vessels INTEGER,                -- 裁罰 (護永專案 summary only)
    fines_ntd_m   REAL,                   -- 罰鍰 NT$ million (護永專案 summary only)
    confiscated   INTEGER,                -- 沒入 (護永專案 summary only)
    source        TEXT NOT NULL CHECK (source IN ('monthly','yearbook','manual')),
    source_ref    TEXT,                   -- report label, e.g. '115年06月績效統計月報 表8-3' or the image URL
    source_url    TEXT,
    scraped_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (period, granularity, region, category, source)
);
CREATE INDEX IF NOT EXISTS idx_cga_enf_period ON cga_enforcement(period, region);
