-- S14 Screen-level external links (support multiple Figma links per screen)
-- Requires: projects, documents, doc_versions, users, external_integrations, screen_external_links
-- Idempotent — safe to re-run.

-- ---------------------------------------------------------------------------
-- 1) Create screen_external_links_v2
--    - Link is now at (project_id, screen_name, type, external_id)
--    - Multiple figma_frame links per screen are allowed
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS screen_external_links_v2 (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  screen_name     TEXT NOT NULL,
  type            TEXT NOT NULL CHECK (type IN ('figma_frame', 'backlog_issue')),
  -- Figma: node id (e.g. "123:456"), Backlog: issue key/id (e.g. "PROJ-142" or "142")
  external_id     TEXT NOT NULL,
  external_url    TEXT,
  -- Document-level target remains optional (for sync into a specific doc stream)
  document_id     UUID REFERENCES documents(id) ON DELETE SET NULL,
  -- Last successful synced doc_version
  doc_version_id  UUID REFERENCES doc_versions(id) ON DELETE SET NULL,
  sync_status     TEXT NOT NULL DEFAULT 'pending'
                  CHECK (sync_status IN ('pending', 'syncing', 'synced', 'failed')),
  error_message   TEXT,
  last_synced_at  TIMESTAMPTZ,
  created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- prevent exact duplicate links per screen
  UNIQUE (project_id, screen_name, type, external_id)
);

CREATE INDEX IF NOT EXISTS idx_screen_ext_links_v2_project_screen
  ON screen_external_links_v2(project_id, screen_name);

CREATE INDEX IF NOT EXISTS idx_screen_ext_links_v2_document
  ON screen_external_links_v2(document_id)
  WHERE document_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_screen_ext_links_v2_status
  ON screen_external_links_v2(sync_status)
  WHERE sync_status IN ('pending', 'failed');

CREATE INDEX IF NOT EXISTS idx_screen_ext_links_v2_type
  ON screen_external_links_v2(type);

-- ---------------------------------------------------------------------------
-- 2) Backfill data from old screen_external_links (document-level)
--    - Resolve screen_name + project_id from documents
-- ---------------------------------------------------------------------------
INSERT INTO screen_external_links_v2 (
  id,
  project_id,
  screen_name,
  type,
  external_id,
  external_url,
  document_id,
  doc_version_id,
  sync_status,
  error_message,
  last_synced_at,
  created_by,
  created_at,
  updated_at
)
SELECT
  sel.id,
  d.project_id,
  d.screen_name,
  sel.type,
  sel.external_id,
  sel.external_url,
  sel.document_id,
  sel.doc_version_id,
  sel.sync_status,
  sel.error_message,
  sel.last_synced_at,
  sel.created_by,
  COALESCE(sel.created_at, now()),
  COALESCE(sel.updated_at, now())
FROM screen_external_links sel
JOIN documents d ON d.id = sel.document_id
ON CONFLICT (project_id, screen_name, type, external_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 3) Optional compatibility view for existing read paths
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_screen_external_links_legacy AS
SELECT
  v2.id,
  v2.document_id,
  v2.type,
  v2.external_id,
  v2.external_url,
  v2.doc_version_id,
  v2.sync_status,
  v2.error_message,
  v2.last_synced_at,
  v2.created_by,
  v2.created_at,
  v2.updated_at
FROM screen_external_links_v2 v2
WHERE v2.document_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 4) Keep old table for rollback safety (no DROP here)
-- ---------------------------------------------------------------------------
-- NOTE:
-- - app layer should be migrated to use screen_external_links_v2.
-- - after full cutover, you may archive/drop screen_external_links in a later migration.
