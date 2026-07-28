-- Alt-model comparison experiment (Chinese LLMs via OpenRouter).
-- One row per (article, model, arm) sweep result. NOT an editorial queue:
-- no review columns, never feeds the public feed or the pending queues.
-- Refusals are first-class outcomes — a 'refused' row is a finding, not
-- a failure. See scripts/sweep_alt_models.py.

CREATE TABLE IF NOT EXISTS alt_model_analysis (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id          INTEGER NOT NULL REFERENCES articles(id),
    model               TEXT NOT NULL,      -- OpenRouter slug ('deepseek/deepseek-v4-flash') or Gemini model (control arm)
    arm                 TEXT NOT NULL CHECK (arm IN ('neutral','originator','control')),
    outcome             TEXT NOT NULL CHECK (outcome IN ('ok','refused','parse_error','api_error')),
    -- comparison fields (NULL unless outcome='ok')
    topic_primary       TEXT,
    topic_secondary     TEXT,
    sentiment           TEXT,
    sentiment_score     REAL,
    sentiment_reasoning TEXT,
    urgency             TEXT,
    summary_en          TEXT,
    is_escalation_signal BOOLEAN,
    -- refusal / error evidence
    finish_reason       TEXT,               -- provider finish_reason ('stop','content_filter','length',...)
    refusal_text        TEXT,               -- the model's refusal wording (outcome='refused')
    error_text          TEXT,               -- HTTP/exception or JSON-parse detail
    -- provenance / audit
    provider_requested  TEXT,               -- JSON array sent as provider.only
    provider_used       TEXT,               -- who actually served it (response 'provider')
    prompt_sha256       TEXT,               -- hash of the exact prompt sent (prompt-drift attribution)
    raw_response        TEXT,               -- full response body JSON (side-extract arrays stay in here)
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    total_tokens        INTEGER,
    latency_ms          INTEGER,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (article_id, model, arm)
);
CREATE INDEX IF NOT EXISTS idx_alt_model_article ON alt_model_analysis(article_id);
CREATE INDEX IF NOT EXISTS idx_alt_model_outcome ON alt_model_analysis(model, arm, outcome);
