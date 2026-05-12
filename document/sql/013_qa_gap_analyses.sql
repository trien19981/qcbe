-- Q&A Gap Analysis: 1 record / lần generate cho 1 màn hình + N items có cột Answer edit được.
-- Step 1 trong pipeline Q&A → TVP → TC.

CREATE TABLE IF NOT EXISTS qa_gap_analyses (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  screen_name     TEXT NOT NULL,
  doc_types       TEXT[] NOT NULL DEFAULT '{}',
  status          TEXT NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft', 'in_review', 'completed')),
  total_items     INT NOT NULL DEFAULT 0,
  answered_items  INT NOT NULL DEFAULT 0,
  generated_by    UUID REFERENCES users(id) ON DELETE SET NULL,
  generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qa_analyses_project_screen
  ON qa_gap_analyses(project_id, screen_name);

CREATE INDEX IF NOT EXISTS idx_qa_analyses_project_status
  ON qa_gap_analyses(project_id, status);

CREATE TABLE IF NOT EXISTS qa_gap_items (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  qa_analysis_id  UUID NOT NULL REFERENCES qa_gap_analyses(id) ON DELETE CASCADE,
  gap_id          TEXT NOT NULL,
  category        TEXT NOT NULL,
  gap_description TEXT NOT NULL,
  risk            TEXT NOT NULL
                  CHECK (risk IN ('High', 'Medium', 'Low')),
  question        TEXT NOT NULL,
  answer          TEXT,
  answer_status   TEXT NOT NULL DEFAULT 'open'
                  CHECK (answer_status IN ('open', 'answered', 'wont_fix', 'deferred')),
  answered_by     UUID REFERENCES users(id) ON DELETE SET NULL,
  answered_at     TIMESTAMPTZ,
  source_chunk_id UUID REFERENCES chunks(id) ON DELETE SET NULL,
  display_order   INT NOT NULL DEFAULT 0,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (qa_analysis_id, gap_id)
);

CREATE INDEX IF NOT EXISTS idx_qa_items_analysis
  ON qa_gap_items(qa_analysis_id);

CREATE INDEX IF NOT EXISTS idx_qa_items_status
  ON qa_gap_items(qa_analysis_id, answer_status);

CREATE TABLE IF NOT EXISTS qa_jobs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  screen_name     TEXT NOT NULL,
  doc_types       TEXT[] NOT NULL,
  qa_analysis_id  UUID REFERENCES qa_gap_analyses(id) ON DELETE SET NULL,
  status          TEXT NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued', 'processing', 'done', 'failed')),
  progress        JSONB NOT NULL DEFAULT '{}'::jsonb,
  result          JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_message   TEXT,
  created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qa_jobs_project_status
  ON qa_jobs(project_id, status);
