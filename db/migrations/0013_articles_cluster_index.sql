-- Index articles.event_cluster_id (2026-09-08). The feed's cluster-siblings
-- endpoint looks articles up by cluster id; without an index each lookup is
-- a full scan of ~185k rows (~240 ms on prod). (The visits coverage endpoint
-- used it too until 2026-09-13, when cluster siblings were dropped from it.)
-- Mirrored in db/schema.sql.
CREATE INDEX IF NOT EXISTS idx_articles_cluster ON articles(event_cluster_id);
