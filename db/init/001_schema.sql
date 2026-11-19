-- Schema for the ESG Greenwashing Detector.
-- Runs once, when the Postgres container first initialises its data volume.
-- The Spring API validates its entities against this; the Python workers write to it directly.

CREATE EXTENSION IF NOT EXISTS vector;

-- One uploaded BRSR PDF. Status moves forward through the pipeline:
-- UPLOADED (API) -> PARSING -> PARSED (parser worker) -> ANALYZING -> ANALYZED (analyzer worker).
CREATE TABLE reports (
    id                BIGSERIAL PRIMARY KEY,
    company           TEXT        NOT NULL,
    fiscal_year       INT         NOT NULL CHECK (fiscal_year BETWEEN 2000 AND 2100),
    original_filename TEXT        NOT NULL,
    storage_key       TEXT        NOT NULL UNIQUE,  -- file name inside REPORTS_DIR
    sha256            CHAR(64)    NOT NULL UNIQUE,
    page_count        INT,
    status            TEXT        NOT NULL DEFAULT 'UPLOADED'
                      CHECK (status IN ('UPLOADED', 'PARSING', 'PARSED', 'ANALYZING', 'ANALYZED', 'FAILED')),
    error             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX reports_company_idx ON reports (lower(company));

-- A retrievable piece of a report: a run of prose, or a table (or a slice of a long table's rows).
CREATE TABLE chunks (
    id          BIGSERIAL PRIMARY KEY,
    report_id   BIGINT   NOT NULL REFERENCES reports (id) ON DELETE CASCADE,
    seq         INT      NOT NULL,                 -- reading order within the report
    kind        TEXT     NOT NULL CHECK (kind IN ('text', 'table')),
    section     CHAR(1)  CHECK (section IN ('A', 'B', 'C')),  -- BRSR section; NULL = outside the BRSR
    principle   SMALLINT CHECK (principle BETWEEN 1 AND 9),   -- only set inside Section C
    heading     TEXT,                              -- nearest sub-heading, e.g. 'Essential Indicators'
    page_start  INT      NOT NULL,                 -- 1-based
    page_end    INT      NOT NULL,
    text        TEXT     NOT NULL,
    word_count  INT      NOT NULL,
    embedding   vector(384),                       -- BAAI/bge-small-en-v1.5, normalised
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    UNIQUE (report_id, seq)
);
CREATE INDEX chunks_report_idx    ON chunks (report_id);
CREATE INDEX chunks_tsv_idx       ON chunks USING gin (tsv);
CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);

-- Baseline: the original FinBERT heuristic, scored per text chunk. Kept as the number to beat.
CREATE TABLE baseline_scores (
    chunk_id   BIGINT PRIMARY KEY REFERENCES chunks (id) ON DELETE CASCADE,
    esg_label  TEXT   NOT NULL,
    esg_score  REAL   NOT NULL,
    tone_label TEXT   NOT NULL,
    tone_score REAL   NOT NULL,
    risk_score REAL   NOT NULL,   -- 0..100
    flagged    BOOLEAN NOT NULL,  -- vague and hyped, per the old rule
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Phase 2: sentences that make an environmental claim.
CREATE TABLE claims (
    id                BIGSERIAL PRIMARY KEY,
    report_id         BIGINT NOT NULL REFERENCES reports (id) ON DELETE CASCADE,
    chunk_id          BIGINT NOT NULL REFERENCES chunks (id) ON DELETE CASCADE,
    sentence          TEXT   NOT NULL,
    char_start        INT,
    char_end          INT,
    claim_score       REAL   NOT NULL,  -- classifier confidence that this is an environmental claim
    specificity_score REAL,             -- higher = more specific
    prominence        REAL,             -- weight used in the report risk score
    model             TEXT   NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX claims_report_idx ON claims (report_id);

-- Phase 3: passages retrieved as possible support for a claim.
CREATE TABLE evidence (
    claim_id        BIGINT NOT NULL REFERENCES claims (id) ON DELETE CASCADE,
    chunk_id        BIGINT NOT NULL REFERENCES chunks (id) ON DELETE CASCADE,
    rank            INT    NOT NULL,
    retrieval_score REAL,
    rerank_score    REAL,
    PRIMARY KEY (claim_id, chunk_id)
);

-- Phase 3: the judgement on each claim, with the chunks it cites.
CREATE TABLE verdicts (
    id              BIGSERIAL PRIMARY KEY,
    claim_id        BIGINT NOT NULL REFERENCES claims (id) ON DELETE CASCADE,
    label           TEXT   NOT NULL CHECK (label IN ('substantiated', 'vague', 'unsupported')),
    confidence      REAL,
    reason          TEXT,
    cited_chunk_ids BIGINT[] NOT NULL DEFAULT '{}',
    model           TEXT   NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX verdicts_claim_idx ON verdicts (claim_id);
