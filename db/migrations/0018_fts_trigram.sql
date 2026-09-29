-- Chinese full-text search, and a narrower FTS update trigger (2026-09-29).
--
-- articles_fts uses FTS5's default unicode61 tokenizer, which has no Chinese
-- word segmentation: a run of Han characters up to the next punctuation mark is
-- a single token, so MATCH '賴清德' only finds articles where the name stands
-- between punctuation marks (616 of 4,593 on staging). articles_fts stays for
-- Latin-script queries, where whole-word matching is right ('PLA' must not
-- match 'place'). articles_fts_zh indexes the original-language title and body
-- with the trigram tokenizer, so any run of 3+ characters is searchable.
-- detail='none' keeps it at about 40% of the detail='full' size (about 0.6 GB
-- instead of 1.4 GB on prod) but cannot run phrase queries, so
-- api/routes/articles.py ANDs the term's trigrams to find candidates and
-- confirms each one with LIKE. Terms under 3 characters use LIKE alone.
--
-- articles_au used to fire on every UPDATE of articles (approvals, cluster
-- ids, scan stamps), deleting and re-inserting up to 25,000 characters of
-- index data each time. Both update triggers now fire only when an indexed
-- column changes.
--
-- The rebuild takes about 75 s on staging and about 4 minutes on prod, holding
-- the write lock. Mirrored in db/schema.sql.

DROP TRIGGER IF EXISTS articles_au;
CREATE TRIGGER articles_au
AFTER UPDATE OF title_original, title_en, content_original, content_en ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title_original, title_en, content_original, content_en)
    VALUES('delete', old.id, old.title_original, old.title_en, old.content_original, old.content_en);
    INSERT INTO articles_fts(rowid, title_original, title_en, content_original, content_en)
    VALUES (new.id, new.title_original, new.title_en, new.content_original, new.content_en);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts_zh USING fts5(
    title_original,
    content_original,
    content='articles',
    content_rowid='id',
    tokenize='trigram',
    detail='none'
);

CREATE TRIGGER IF NOT EXISTS articles_zh_ai AFTER INSERT ON articles BEGIN
    INSERT INTO articles_fts_zh(rowid, title_original, content_original)
    VALUES (new.id, new.title_original, new.content_original);
END;
CREATE TRIGGER IF NOT EXISTS articles_zh_ad AFTER DELETE ON articles BEGIN
    INSERT INTO articles_fts_zh(articles_fts_zh, rowid, title_original, content_original)
    VALUES('delete', old.id, old.title_original, old.content_original);
END;
CREATE TRIGGER IF NOT EXISTS articles_zh_au
AFTER UPDATE OF title_original, content_original ON articles BEGIN
    INSERT INTO articles_fts_zh(articles_fts_zh, rowid, title_original, content_original)
    VALUES('delete', old.id, old.title_original, old.content_original);
    INSERT INTO articles_fts_zh(rowid, title_original, content_original)
    VALUES (new.id, new.title_original, new.content_original);
END;

INSERT INTO articles_fts_zh(articles_fts_zh) VALUES('rebuild');

-- The rebuild wrote the whole index through the WAL (0016); copy it into the
-- database file and shrink the -wal file now rather than leaving ~0.5 GB of it
-- behind while the API holds connections. A busy result just means a reader was
-- mid-query; the next automatic checkpoint finishes the job.
PRAGMA wal_checkpoint(TRUNCATE);
