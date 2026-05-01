import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal, engine

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
# Tắt noise từ các thư viện bên thứ ba
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
from app.exceptions import ApiError, api_error_handler
from app.models.processing_job import ProcessingJob
from app.redis_client import close_redis
from app.routers import auth, chat, chunks, documents, embeddings, health, invitations, project_documents, project_documents_upload, project_members, projects


async def _recover_stale_jobs() -> None:
    """Re-enqueue processing_jobs stuck in 'running' for more than 15 minutes.

    This covers the case where the worker process died mid-task and never
    updated the job status back to 'failed'.
    """
    from app.worker import enqueue_version_processing

    stale_cutoff = datetime.now(UTC) - timedelta(minutes=15)
    async with AsyncSessionLocal() as session:
        stale = (
            await session.execute(
                select(ProcessingJob).where(
                    ProcessingJob.status == "running",
                    ProcessingJob.started_at < stale_cutoff,
                )
            )
        ).scalars().all()

        for job in stale:
            rq_job_id = await asyncio.to_thread(
                enqueue_version_processing, str(job.doc_version_id), str(job.id)
            )
            job.status = "queued"
            job.rq_job_id = rq_job_id
            job.started_at = None

        if stale:
            await session.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await _recover_stale_jobs()
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(title="QCMaster API", lifespan=lifespan)
app.add_exception_handler(ApiError, api_error_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(project_documents.router, prefix="/api/v1/projects", tags=["project-documents"])
app.include_router(project_documents_upload.router, prefix="/api/v1", tags=["project-documents-upload"])
app.include_router(project_members.router, prefix="/api/v1/projects", tags=["project-members"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(chunks.router, prefix="/api/v1", tags=["chunks"])
app.include_router(embeddings.router, prefix="/api/v1", tags=["embeddings"])
app.include_router(invitations.router, prefix="/api/v1", tags=["invitations"])


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "QCMaster API", "docs": "/docs"}
