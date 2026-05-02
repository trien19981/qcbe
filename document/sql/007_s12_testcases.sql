-- S12 TC list: columns on testcases + generate jobs (idempotent).
-- Requires existing tables: projects, users, testcases, testcase_chunk_links, chunks, doc_versions, documents.

ALTER TABLE testcases ADD COLUMN IF NOT EXISTS screen_name TEXT NOT NULL DEFAULT '';
ALTER TABLE testcases ADD COLUMN IF NOT EXISTS expected_result TEXT;
ALTER TABLE testcases ADD COLUMN IF NOT EXISTS needs_review BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE testcases ADD COLUMN IF NOT EXISTS tc_sequential INT;
ALTER TABLE testcases ADD COLUMN IF NOT EXISTS tc_id TEXT;
ALTER TABLE testcases ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_testcases_needs_review
  ON testcases(project_id, needs_review)
  WHERE needs_review = true;

CREATE INDEX IF NOT EXISTS idx_testcases_screen_status
  ON testcases(project_id, screen_name, status);

CREATE INDEX IF NOT EXISTS idx_testcases_priority
  ON testcases(project_id, priority);

CREATE INDEX IF NOT EXISTS idx_testcases_search
  ON testcases USING gin (to_tsvector('simple', coalesce(title, '')));

CREATE TABLE IF NOT EXISTS tc_generate_jobs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  screen_name  TEXT NOT NULL,
  doc_types    TEXT[] NOT NULL,
  tc_type      TEXT NOT NULL,
  overwrite_existing BOOLEAN NOT NULL DEFAULT false,
  status       TEXT NOT NULL DEFAULT 'queued'
               CHECK (status IN ('queued','processing','done','failed')),
  progress     JSONB NOT NULL DEFAULT '{}'::jsonb,
  result       JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_message TEXT,
  created_by   UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE tc_generate_jobs ADD COLUMN IF NOT EXISTS overwrite_existing BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_tc_generate_jobs_project
  ON tc_generate_jobs(project_id, status);
