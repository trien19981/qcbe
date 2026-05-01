-- Migration: processing_jobs table
-- Tracks RQ worker job state for document version embedding pipeline.
-- Run once on the remote DB before deploying the worker service.

CREATE TABLE IF NOT EXISTS processing_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_version_id  UUID NOT NULL REFERENCES doc_versions(id) ON DELETE CASCADE,
    -- queued | running | done | failed
    status          TEXT NOT NULL DEFAULT 'queued',
    attempt         INT  NOT NULL DEFAULT 0,
    error_message   TEXT,
    rq_job_id       TEXT,
    enqueued_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_processing_jobs_doc_version_id
    ON processing_jobs (doc_version_id);

CREATE INDEX IF NOT EXISTS ix_processing_jobs_status
    ON processing_jobs (status);
