-- S16 Add embed status fields for figma_artifacts
-- Purpose: split "ingest/sync" (fetch+markdown+screenshot) from "embed" (chunk+embeddings)
-- Idempotent — safe to re-run.

ALTER TABLE figma_artifacts
  ADD COLUMN IF NOT EXISTS embed_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (embed_status IN ('pending', 'embedding', 'embedded', 'failed'));

ALTER TABLE figma_artifacts
  ADD COLUMN IF NOT EXISTS embed_error_message TEXT;

ALTER TABLE figma_artifacts
  ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_figma_artifacts_embed_status
  ON figma_artifacts(embed_status)
  WHERE embed_status IN ('pending', 'failed');

