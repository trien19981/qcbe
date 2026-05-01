-- Pending invitations for project member invites (MEMBER_MANAGEMENT_DESIGN.md)
CREATE TABLE IF NOT EXISTS pending_invitations (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  email       TEXT NOT NULL,
  role        TEXT NOT NULL DEFAULT 'qc',
  invited_by  UUID REFERENCES users(id) ON DELETE SET NULL,
  token       UUID NOT NULL DEFAULT gen_random_uuid(),
  expires_at  TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '7 days'),
  created_at  TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT uq_pending_inv_project_email UNIQUE (project_id, email)
);

CREATE INDEX IF NOT EXISTS idx_pending_inv_token ON pending_invitations(token);
CREATE INDEX IF NOT EXISTS idx_pending_inv_project ON pending_invitations(project_id);
CREATE INDEX IF NOT EXISTS idx_pending_inv_expires ON pending_invitations(expires_at);
