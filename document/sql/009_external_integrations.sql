-- S13 External integrations: Figma + Backlog
-- Requires: projects, documents, doc_versions, users tables.
-- Idempotent — safe to re-run.

-- ---------------------------------------------------------------------------
-- 1. Extend doc_type_enum with backlog_issue
-- ---------------------------------------------------------------------------
DO $$ BEGIN
  ALTER TYPE doc_type_enum ADD VALUE IF NOT EXISTS 'backlog_issue';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- 2. Alter doc_versions: add source column, make r2_key / r2_url nullable
--    (external-synced versions have no R2 file)
-- ---------------------------------------------------------------------------
ALTER TABLE doc_versions
  ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'upload'
  CHECK (source IN ('upload', 'figma', 'backlog'));

ALTER TABLE doc_versions
  ALTER COLUMN r2_key DROP NOT NULL;

ALTER TABLE doc_versions
  ALTER COLUMN r2_url DROP NOT NULL;

-- ---------------------------------------------------------------------------
-- 3. external_integrations — project-level API credentials per provider
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS external_integrations (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  type       TEXT NOT NULL CHECK (type IN ('figma', 'backlog')),
  -- Figma: { "personal_access_token": "...", "file_key": "..." }
  -- Backlog: { "space_url": "https://xxx.backlog.com", "api_key": "...", "project_key": "PROJ" }
  config     JSONB NOT NULL DEFAULT '{}',
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE (project_id, type)
);

CREATE INDEX IF NOT EXISTS idx_ext_integrations_project
  ON external_integrations(project_id);

-- ---------------------------------------------------------------------------
-- 4. screen_external_links_v2 — per-screen link to a Figma frame or Backlog issue
--    Keyed by (project_id, screen_name) so links can exist before a document is created.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS screen_external_links_v2 (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  screen_name     TEXT NOT NULL,
  type            TEXT NOT NULL CHECK (type IN ('figma_frame', 'backlog_issue')),
  -- Figma: node_id (e.g. "123:456"), Backlog: issue key (e.g. "PROJ-42")
  external_id     TEXT NOT NULL,
  external_url    TEXT,
  -- Resolved after first sync; nullable until then
  document_id     UUID REFERENCES documents(id) ON DELETE SET NULL,
  -- Points to the doc_version created by the last successful sync
  doc_version_id  UUID REFERENCES doc_versions(id) ON DELETE SET NULL,
  sync_status     TEXT NOT NULL DEFAULT 'pending'
                  CHECK (sync_status IN ('pending', 'syncing', 'synced', 'failed')),
  error_message   TEXT,
  last_synced_at  TIMESTAMPTZ,
  created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE (project_id, screen_name, type, external_id)
);

CREATE INDEX IF NOT EXISTS idx_screen_ext_links_project
  ON screen_external_links_v2(project_id, screen_name);

CREATE INDEX IF NOT EXISTS idx_screen_ext_links_status
  ON screen_external_links_v2(sync_status)
  WHERE sync_status IN ('pending', 'failed');
