-- Test Viewpoints (TVP): bảng markdown TVP per màn hình + checklist 18 mục coverage.
-- Step 2 trong pipeline Q&A → TVP → TC.

CREATE TABLE IF NOT EXISTS test_viewpoints (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  screen_name     TEXT NOT NULL,
  qa_analysis_id  UUID REFERENCES qa_gap_analyses(id) ON DELETE SET NULL,
  status          TEXT NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft', 'approved', 'archived')),
  content_md      TEXT NOT NULL DEFAULT '',
  checklist_18    JSONB NOT NULL DEFAULT '[]'::jsonb,
  generated_by    UUID REFERENCES users(id) ON DELETE SET NULL,
  approved_by     UUID REFERENCES users(id) ON DELETE SET NULL,
  approved_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tvp_project_screen
  ON test_viewpoints(project_id, screen_name);

CREATE INDEX IF NOT EXISTS idx_tvp_project_status
  ON test_viewpoints(project_id, status);

CREATE TABLE IF NOT EXISTS tvp_jobs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  screen_name     TEXT NOT NULL,
  qa_analysis_id  UUID REFERENCES qa_gap_analyses(id) ON DELETE SET NULL,
  doc_types       TEXT[] NOT NULL DEFAULT '{}',
  tvp_id          UUID REFERENCES test_viewpoints(id) ON DELETE SET NULL,
  status          TEXT NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued', 'processing', 'done', 'failed')),
  progress        JSONB NOT NULL DEFAULT '{}'::jsonb,
  result          JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_message   TEXT,
  created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tvp_jobs_project_status
  ON tvp_jobs(project_id, status);
