-- S15 Tách Figma sync ra khỏi luồng tài liệu gốc
-- Figma data giờ lưu vào figma_artifacts thay vì doc_versions/documents
-- Idempotent — safe to re-run.

-- ---------------------------------------------------------------------------
-- 1. Bảng chứa kết quả sync từ Figma (thay thế doc_version cho figma_frame)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS figma_artifacts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  screen_name     TEXT NOT NULL,
  file_key        TEXT NOT NULL,
  node_id         TEXT NOT NULL,
  node_url        TEXT,
  markdown        TEXT,
  screenshot_url  TEXT,
  sync_status     TEXT NOT NULL DEFAULT 'pending'
                  CHECK (sync_status IN ('pending', 'syncing', 'synced', 'failed')),
  error_message   TEXT,
  last_synced_at  TIMESTAMPTZ,
  created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE (project_id, screen_name, node_id)
);

CREATE INDEX IF NOT EXISTS idx_figma_artifacts_project_screen
  ON figma_artifacts(project_id, screen_name);

CREATE INDEX IF NOT EXISTS idx_figma_artifacts_status
  ON figma_artifacts(sync_status)
  WHERE sync_status IN ('pending', 'failed');

-- ---------------------------------------------------------------------------
-- 2. Thêm figma_artifact_id vào chunks, cho phép doc_version_id nullable
--    Invariant: đúng một trong hai cột phải có giá trị
-- ---------------------------------------------------------------------------
ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS figma_artifact_id UUID
  REFERENCES figma_artifacts(id) ON DELETE CASCADE;

ALTER TABLE chunks
  ALTER COLUMN doc_version_id DROP NOT NULL;

-- ---------------------------------------------------------------------------
-- 3. Thêm figma_artifact_id vào screen_external_links_v2
--    Figma links dùng figma_artifact_id, Backlog links vẫn dùng doc_version_id
-- ---------------------------------------------------------------------------
ALTER TABLE screen_external_links_v2
  ADD COLUMN IF NOT EXISTS figma_artifact_id UUID
  REFERENCES figma_artifacts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_screen_ext_links_v2_artifact
  ON screen_external_links_v2(figma_artifact_id)
  WHERE figma_artifact_id IS NOT NULL;
