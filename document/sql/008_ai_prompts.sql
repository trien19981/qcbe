-- Per-project overrides for business AI prompts (Q&A, suggested questions, TC generate).
-- Chunking prompts stay in code (llm_chunker.py).

CREATE TABLE IF NOT EXISTS ai_prompts (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  prompt_key   TEXT NOT NULL,
  content      TEXT NOT NULL,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by   UUID REFERENCES users(id) ON DELETE SET NULL,
  UNIQUE (project_id, prompt_key)
);

CREATE INDEX IF NOT EXISTS idx_ai_prompts_project ON ai_prompts(project_id);
