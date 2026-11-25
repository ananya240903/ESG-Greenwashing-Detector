-- Phase 4: regulation tagging. The BRSR topics a claim is about (nlp-analyzer/esg/claims/topics.py),
-- e.g. {ghg,water}. ghg, water, energy and waste are SEBI BRSR Core attributes.
ALTER TABLE claims ADD COLUMN IF NOT EXISTS topics TEXT[] NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS claims_topics_idx ON claims USING gin (topics);
