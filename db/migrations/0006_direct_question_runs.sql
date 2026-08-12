-- Direct-question arm of the alt-model experiment (prompt-shape test).
-- One row per (question, lang, model, arm, run_idx) call — n=5 repeats per
-- cell, so this CANNOT share alt_model_analysis (article_id NOT NULL +
-- UNIQUE(article,model,arm) both fail). Separate table also keeps the two
-- regimes out of each other's aggregation scripts by construction.
-- NOT an editorial queue: never feeds the feed or any pending queue.
-- See scripts/sweep_direct_questions.py and data/direct_questions.json.

CREATE TABLE IF NOT EXISTS direct_question_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id         TEXT NOT NULL,      -- battery id ('A-01', 'C-03', ...)
    band                TEXT NOT NULL CHECK (band IN ('A','B','C','D')),
    lang                TEXT NOT NULL CHECK (lang IN ('en','zh','mixed')),
    run_idx             INTEGER NOT NULL,   -- 1..n (n=5 in the brief)
    model               TEXT NOT NULL,      -- OpenRouter slug or Gemini model (control)
    arm                 TEXT NOT NULL CHECK (arm IN ('neutral','originator','control')),
    -- auto-classification (conservative; every non-'answered' row goes to the
    -- hand-review JSONL — no refusal number is publishable unread)
    outcome             TEXT NOT NULL CHECK (outcome IN
                          ('answered','answered_with_caveat','deflected',
                           'refused','empty_or_error')),
    reviewed_outcome    TEXT CHECK (reviewed_outcome IS NULL OR reviewed_outcome IN
                          ('answered','answered_with_caveat','deflected',
                           'refused','empty_or_error')),  -- hand-review verdict, folded back later
    response_text       TEXT,               -- assistant message content
    reasoning_content   TEXT,               -- chain-of-thought where the endpoint exposes it
                                            -- (reasoning-then-refusal is the app-layer signature;
                                            --  its ABSENCE on Western hosts is itself a result)
    finish_reason       TEXT,
    refusal_text        TEXT,
    error_text          TEXT,
    -- provenance / audit (the piece claims things about weights — receipts)
    provider_requested  TEXT,               -- JSON array sent as provider.only
    provider_used       TEXT,
    prompt_sha256       TEXT,               -- exact prompt hash (Band C: the generated Tier-1 prompt)
    temperature_sent    REAL,               -- what we asked for; endpoints may ignore it
    raw_response        TEXT,
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    total_tokens        INTEGER,
    latency_ms          INTEGER,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (question_id, lang, model, arm, run_idx)
);

CREATE INDEX IF NOT EXISTS idx_direct_q_cell
    ON direct_question_runs(model, arm, band, lang, outcome);
