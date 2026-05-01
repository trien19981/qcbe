-- S9 Q&A Chat schema (chat_conversations, chat_messages, chat_citations, chat_suggested_questions)
-- Requires: pgcrypto for gen_random_uuid() (or use uuid-ossp if preferred).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS chat_conversations (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  created_by   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title        TEXT,
  scope_type   TEXT NOT NULL CHECK (scope_type IN ('project','screen','doc_type')),
  scope_config JSONB NOT NULL DEFAULT '{}',
  created_at   TIMESTAMPTZ DEFAULT now(),
  updated_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
  role            TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content         TEXT NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_citations (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id       UUID NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
  chunk_id         UUID REFERENCES chunks(id) ON DELETE SET NULL,
  citation_index   INT NOT NULL,
  badge_text       TEXT NOT NULL,
  doc_type         TEXT,
  screen_name      TEXT,
  section_name     TEXT,
  preview_text     TEXT,
  similarity_score FLOAT
);

CREATE TABLE IF NOT EXISTS chat_suggested_questions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
  question        TEXT NOT NULL,
  display_order   INT NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_chat_conv_project  ON chat_conversations(project_id);
CREATE INDEX IF NOT EXISTS idx_chat_conv_user     ON chat_conversations(created_by);
CREATE INDEX IF NOT EXISTS idx_chat_msg_conv      ON chat_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_chat_citations_msg ON chat_citations(message_id);
CREATE INDEX IF NOT EXISTS idx_chat_citations_chunk ON chat_citations(chunk_id);
CREATE INDEX IF NOT EXISTS idx_chat_suggested_conv ON chat_suggested_questions(conversation_id);

