"""RQ worker tasks and enqueue helpers for the document processing pipeline."""

import asyncio
import uuid
from datetime import UTC, datetime

from redis import Redis
from rq import Queue, Retry, get_current_job

from app.config import settings


# ---------------------------------------------------------------------------
# RQ task — semantic diff analysis
# ---------------------------------------------------------------------------

def analyze_diff_semantic(diff_review_id: str) -> None:
    """Compute semantic diff for a diff_review using chunk embeddings.

    Called by the RQ worker. Failures are swallowed so the router's basic-diff
    fallback can take over after the 5-minute grace window.
    """
    async def _run() -> None:
        from app.database import engine
        from app.diff_analysis import analyze_diff_semantic_async

        try:
            await analyze_diff_semantic_async(diff_review_id)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def enqueue_diff_analysis(diff_review_id: str) -> str:
    """Enqueue a semantic diff analysis job. Returns the RQ job ID."""
    conn = Redis.from_url(settings.redis_url)
    q = Queue("document_processing", connection=conn)
    rq_job = q.enqueue(
        analyze_diff_semantic,
        diff_review_id,
        job_timeout=300,
    )
    return rq_job.id


# ---------------------------------------------------------------------------
# RQ task — must be a top-level sync function so RQ can import it by path.
# ---------------------------------------------------------------------------

def process_document_version(version_id: str, job_db_id: str) -> None:
    """Process one document version: extract → chunk → embed.

    Called by the RQ worker. Uses asyncio.run() to drive the async pipeline.
    On failure the exception is re-raised so RQ can apply its retry schedule.
    """
    # Capture RQ job ID before entering the new event loop (thread-local access).
    current_rq_job = get_current_job()
    rq_job_id: str | None = current_rq_job.id if current_rq_job else None

    async def _run() -> None:
        # Late imports so the worker process only loads DB models when a task starts.
        from app.database import AsyncSessionLocal, engine
        from app.document_processing import process_version_async
        from app.models.document import DocVersion
        from app.models.processing_job import ProcessingJob

        job_uuid = uuid.UUID(job_db_id)
        version_uuid = uuid.UUID(version_id)

        try:
            # ── Mark job as running ──────────────────────────────────────
            async with AsyncSessionLocal() as session:
                job = await session.get(ProcessingJob, job_uuid)
                if job is None:
                    return
                job.status = "running"
                job.started_at = datetime.now(UTC)
                job.attempt += 1
                if rq_job_id:
                    job.rq_job_id = rq_job_id
                await session.commit()

            # ── Run the pipeline ─────────────────────────────────────────
            await process_version_async(version_id)

            # ── Mark job as done ─────────────────────────────────────────
            async with AsyncSessionLocal() as session:
                job = await session.get(ProcessingJob, job_uuid)
                if job:
                    job.status = "done"
                    job.finished_at = datetime.now(UTC)
                    job.error_message = None
                    await session.commit()

        except Exception as exc:
            # ── Mark job as failed ───────────────────────────────────────
            async with AsyncSessionLocal() as session:
                job = await session.get(ProcessingJob, job_uuid)
                if job:
                    job.status = "failed"
                    job.finished_at = datetime.now(UTC)
                    job.error_message = str(exc)[:2000]
                    await session.commit()

            # ── Mark version as rejected ─────────────────────────────────
            # process_version_async resets it to "processing" on retry start,
            # so this is only the terminal state if RQ exhausts all retries.
            async with AsyncSessionLocal() as session:
                v = await session.get(DocVersion, version_uuid)
                if v:
                    v.status = "rejected"
                    v.updated_at = datetime.now(UTC)
                    await session.commit()

            raise  # Let RQ apply retry schedule.

        finally:
            # Dispose the connection pool so the next asyncio.run() call
            # gets a fresh pool bound to the new event loop.
            await engine.dispose()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Enqueue helper — sync so it can be called via asyncio.to_thread from routers.
# ---------------------------------------------------------------------------

def enqueue_version_processing(version_id: str, job_db_id: str) -> str:
    """Enqueue a document version processing job. Returns the RQ job ID."""
    conn = Redis.from_url(settings.redis_url)
    q = Queue("document_processing", connection=conn)
    rq_job = q.enqueue(
        process_document_version,
        version_id,
        job_db_id,
        retry=Retry(max=3, interval=[30, 120, 600]),
        job_timeout=3600,
    )
    return rq_job.id


def run_tc_generate_job_worker(job_id: str) -> None:
    """RQ entrypoint for S12 testcase generation."""
    from app.services.tc_generate_run import run_tc_generate_job_sync

    run_tc_generate_job_sync(job_id)


def enqueue_tc_generate(job_db_id: str) -> str:
    """Enqueue S12 testcase generation job. Returns RQ job id."""
    conn = Redis.from_url(settings.redis_url)
    q = Queue("document_processing", connection=conn)
    rq_job = q.enqueue(
        run_tc_generate_job_worker,
        job_db_id,
        job_timeout=3600,
    )
    return rq_job.id


def run_qa_generate_job_worker(job_id: str) -> None:
    """RQ entrypoint for Q&A Gap Analysis generation."""
    from app.services.qa_generate_run import run_qa_generate_job_sync

    run_qa_generate_job_sync(job_id)


def enqueue_qa_generate(job_db_id: str) -> str:
    """Enqueue Q&A Gap Analysis generation job. Returns RQ job id."""
    conn = Redis.from_url(settings.redis_url)
    q = Queue("document_processing", connection=conn)
    rq_job = q.enqueue(
        run_qa_generate_job_worker,
        job_db_id,
        job_timeout=1800,
    )
    return rq_job.id


def run_tvp_generate_job_worker(job_id: str) -> None:
    """RQ entrypoint for TVP generation."""
    from app.services.tvp_generate_run import run_tvp_generate_job_sync

    run_tvp_generate_job_sync(job_id)


def enqueue_tvp_generate(job_db_id: str) -> str:
    """Enqueue TVP generation job. Returns RQ job id."""
    conn = Redis.from_url(settings.redis_url)
    q = Queue("document_processing", connection=conn)
    rq_job = q.enqueue(
        run_tvp_generate_job_worker,
        job_db_id,
        job_timeout=1800,
    )
    return rq_job.id


def run_external_sync_job_worker(link_id: str) -> None:
    """RQ entrypoint for external sync (Figma/Backlog)."""

    async def _run() -> None:
        from app.database import engine
        from app.services.external_sync import sync_external_link_async

        try:
            await sync_external_link_async(link_id)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def enqueue_external_sync(link_id: str) -> str:
    """Enqueue external sync job. Returns RQ job id."""
    conn = Redis.from_url(settings.redis_url)
    q = Queue("document_processing", connection=conn)
    rq_job = q.enqueue(
        run_external_sync_job_worker,
        link_id,
        retry=Retry(max=3, interval=[30, 120, 600]),
        job_timeout=1800,
    )
    return rq_job.id


# ---------------------------------------------------------------------------
# RQ task — figma artifact embedding (chunk → embed) as a separate phase
# ---------------------------------------------------------------------------

def run_figma_artifact_embed_job_worker(figma_artifact_id: str) -> None:
    """RQ entrypoint for FigmaArtifact embed (chunk + embeddings)."""

    async def _run() -> None:
        from app.database import engine
        from app.services.external_sync import embed_figma_artifact_async

        try:
            await embed_figma_artifact_async(figma_artifact_id)
        finally:
            await engine.dispose()

    asyncio.run(_run())


def enqueue_figma_artifact_embedding(figma_artifact_id: str) -> str:
    """Enqueue FigmaArtifact embedding job. Returns RQ job id."""
    if not settings.figma_embedding_enabled:
        return "disabled"
    conn = Redis.from_url(settings.redis_url)
    q = Queue("document_processing", connection=conn)
    rq_job = q.enqueue(
        run_figma_artifact_embed_job_worker,
        figma_artifact_id,
        retry=Retry(max=3, interval=[30, 120, 600]),
        job_timeout=3600,
    )
    return rq_job.id
