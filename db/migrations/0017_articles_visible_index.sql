-- Covering index for the public-visibility filter (2026-09-29). Every feed and
-- stats query tests is_hidden and analyst_approved, and those columns come after
-- content_original in the row, so reading them walks the article's overflow
-- pages (up to 25,000 characters of body text). With this index the visibility
-- test, the published_at window and the sources join never read the row.
--
-- Measured on a copy of prod (213k articles): /api/stats/?days=30 9.7 s -> 0.3 s
-- cold and 1.2 s -> 0.07 s warm; the public feed's first page 4.0 s -> 0.9 s
-- cold. ANALYZE was tried and left out: with statistics the planner answers the
-- topic and sentiment breakdowns by walking ai_analysis in index order and
-- reading every article row again (stats 0.07 s -> 0.33 s warm).
-- Mirrored in db/schema.sql.
CREATE INDEX IF NOT EXISTS idx_articles_visible
    ON articles(analyst_approved, is_hidden, published_at, source_id);
