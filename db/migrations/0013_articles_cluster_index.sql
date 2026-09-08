-- Index articles.event_cluster_id (2026-09-08). The feed's cluster-siblings
-- endpoint and the visits coverage endpoint both look articles up by cluster
-- id; without an index each lookup is a full scan of ~185k rows (~240 ms on
-- prod). Mirrored in db/schema.sql.
CREATE INDEX IF NOT EXISTS idx_articles_cluster ON articles(event_cluster_id);
