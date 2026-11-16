-- One row per analysed article
CREATE TABLE IF NOT EXISTS analyses (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    url             TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    source          TEXT NOT NULL,
    published_at    TIMESTAMPTZ NOT NULL,
    summary         TEXT NOT NULL,
    subject         TEXT NOT NULL,
    sentiment       TEXT NOT NULL CHECK (sentiment IN ('positive', 'neutral', 'negative')),
    sentiment_score REAL NOT NULL CHECK (sentiment_score BETWEEN -1 AND 1),
    reason          TEXT NOT NULL,
    text_source     TEXT NOT NULL CHECK (text_source IN ('full_text', 'snippet')),
    model           TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
