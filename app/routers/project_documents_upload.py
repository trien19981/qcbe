"""Upload new document (S4_UPLOAD_VERSION_DESIGN.md)."""

import asyncio
import time
import uuid
from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.deps import get_current_user
from app.exceptions import ApiError
from app.models.document import DocVersion, Document
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.worker import enqueue_version_processing
from app.project_access import is_system_admin, project_member_role, require_project_access
from app.r2_upload import upload_to_r2
from app.r2_presign import public_download_url
from app.redis_client import get_redis
from app.schemas.documents import ExistingDocumentSummary, UploadDocumentBodyDocument, UploadDocumentBodyVersion, UploadNewDocumentResponse202

router = APIRouter()

MAX_BYTES = 50 * 1024 * 1024
ALLOWED_DOC_TYPES = {"basic_design", "api_design", "detail_design", "testcase_manual"}

EXT_BY_DOC_TYPE: dict[str, set[str]] = {
    "basic_design": {".md"},
    "detail_design": {".md"},
    "api_design": {".md"},
    "testcase_manual": {".md"},
}


async def _rate_limit_minute(redis, key: str, limit: int) -> None:
    bucket = int(time.time() // 60)
    rkey = f"{key}:{bucket}"
    try:
        n = await redis.incr(rkey)
        if n == 1:
            await redis.expire(rkey, 120)
    except RedisError as exc:
        raise ApiError(
            503,
            "REDIS_UNAVAILABLE",
            "Không kết nối được Redis. Kiểm tra REDIS_URL và dịch vụ Redis đang chạy.",
        ) from exc
    if n > limit:
        raise ApiError(429, "TOO_MANY_REQUESTS", "Quá nhiều yêu cầu. Vui lòng thử lại sau.")


def _sanitize_filename(filename: str) -> str:
    # Keep key stable + safe for URLs
    name = "".join(c if c.isalnum() or c in "._-+" else "_" for c in filename)
    name = name.replace(" ", "_")
    return name[:120] if name else "file"


def _file_extension(filename: str) -> str:
    lower = (filename or "").lower()
    idx = lower.rfind(".")
    return lower[idx:] if idx >= 0 else ""


def _validate_file_for_doc_type(doc_type: str, filename: str) -> str:
    doc_type = (doc_type or "").lower().strip()
    if doc_type not in ALLOWED_DOC_TYPES:
        raise ApiError(422, "VALIDATION_ERROR", "doc_type không hợp lệ")
    ext = _file_extension(filename)
    allowed = EXT_BY_DOC_TYPE.get(doc_type, set())
    if ext not in allowed:
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", f"Loại file {ext or 'unknown'} không hỗ trợ cho {doc_type}")
    return ext


def _make_r2_key(project_id: uuid.UUID, document_id: uuid.UUID, version_no: int, filename: str) -> str:
    safe = _sanitize_filename(filename)
    suffix = safe
    # Use random prefix so key won't collide across retries
    return f"{project_id}/{document_id}/v{version_no}/{uuid.uuid4().hex}_{suffix}"


def _build_existing_document_summary(latest_doc: Document, version_count: int, latest: DocVersion | None) -> ExistingDocumentSummary:
    latest_version_no = latest.version_no if latest else 0
    latest_status = str(latest.status).lower() if latest else "approved"
    return ExistingDocumentSummary(
        id=latest_doc.id,
        screen_name=latest_doc.screen_name,
        doc_type=str(latest_doc.doc_type),
        version_count=version_count,
        latest_version_no=latest_version_no,
        latest_status=latest_status,
    )


@router.post("/projects/{project_id}/documents/upload", status_code=status.HTTP_202_ACCEPTED, response_model=UploadNewDocumentResponse202)
async def upload_new_document(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
    screen_name: str = Form(...),
    doc_type: str = Form(...),
    changelog_md: str | None = Form(None),
    description: str | None = Form(None),
    file: UploadFile = File(...),
) -> UploadNewDocumentResponse202:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:doc:upload:new:{user.id}", 20)

    await require_project_access(session, user, project_id)
    my_role = await project_member_role(session, user.id, project_id)
    if not (is_system_admin(user) or (my_role or "").lower() in {"owner", "pm"}):
        raise ApiError(403, "FORBIDDEN", "Bạn không có quyền upload tài liệu cho project này")

    sn = (screen_name or "").strip()
    dt = (doc_type or "").lower().strip()
    if not sn or len(sn) > 100:
        raise ApiError(422, "VALIDATION_ERROR", "Tên màn hình phải có độ dài từ 1 đến 100 ký tự")
    if dt not in ALLOWED_DOC_TYPES:
        raise ApiError(422, "VALIDATION_ERROR", "doc_type không hợp lệ")

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "File vượt quá giới hạn 50MB")

    _validate_file_for_doc_type(dt, file.filename or "")

    # Duplicate check
    existing = (
        await session.execute(
            select(Document).where(
                Document.project_id == project_id,
                Document.screen_name == sn,
                Document.doc_type == dt,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        vcount = int(
            (await session.execute(select(func.count()).select_from(DocVersion).where(DocVersion.document_id == existing.id))).scalar_one()
        )
        latest = (
            await session.execute(
                select(DocVersion).where(DocVersion.document_id == existing.id).order_by(DocVersion.version_no.desc()).limit(1)
            )
        ).scalars().first()

        summary = _build_existing_document_summary(existing, vcount, latest)
        raise ApiError(
            409,
            "DOCUMENT_EXISTS",
            f"Tài liệu {dt} cho màn hình {sn} đã tồn tại.",
            extra={"existing_document": summary.model_dump()},
        )

    document = Document(
        project_id=project_id,
        screen_name=sn,
        doc_type=dt,
        description=description.strip() if description else None,
        created_by=user.id,
    )
    session.add(document)
    await session.flush()

    version_no = 1
    r2_key = _make_r2_key(project_id, document.id, version_no, file.filename or f"v{version_no}")
    r2_url = public_download_url(r2_key) or r2_key

    # Upload original file to R2 first (so download/status endpoints have usable URLs)
    content_type = file.content_type or "application/octet-stream"
    await asyncio.to_thread(upload_to_r2, r2_key, content, content_type)

    version = DocVersion(
        document_id=document.id,
        version_no=version_no,
        r2_key=r2_key,
        r2_url=r2_url,
        status="processing",
        changelog_md=changelog_md.strip() if changelog_md else None,
        created_by=user.id,
    )
    session.add(version)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        # If race condition creates the document in the meantime
        existing2 = (
            await session.execute(
                select(Document).where(
                    Document.project_id == project_id,
                    Document.screen_name == sn,
                    Document.doc_type == dt,
                )
            )
        ).scalar_one_or_none()
        if existing2 is not None:
            vcount = int(
                (
                    await session.execute(
                        select(func.count()).select_from(DocVersion).where(DocVersion.document_id == existing2.id)
                    )
                ).scalar_one()
            )
            latest = (
                await session.execute(
                    select(DocVersion).where(DocVersion.document_id == existing2.id).order_by(DocVersion.version_no.desc()).limit(1)
                )
            ).scalars().first()
            summary = _build_existing_document_summary(existing2, vcount, latest)
            raise ApiError(
                409,
                "DOCUMENT_EXISTS",
                f"Tài liệu {dt} cho màn hình {sn} đã tồn tại.",
                extra={"existing_document": summary.model_dump()},
            ) from e
        raise

    await session.refresh(version)

    # Create processing job record, then enqueue to RQ worker.
    job = ProcessingJob(doc_version_id=version.id)
    session.add(job)
    await session.commit()
    await session.refresh(job)

    try:
        rq_job_id = await asyncio.to_thread(enqueue_version_processing, str(version.id), str(job.id))
    except RedisError as exc:
        raise ApiError(
            503,
            "QUEUE_UNAVAILABLE",
            "Không thể đưa tác vụ xử lý vào hàng đợi (Redis/RQ). Kiểm tra REDIS_URL và worker `rq worker ... document_processing`.",
        ) from exc
    job.rq_job_id = rq_job_id
    await session.commit()

    return UploadNewDocumentResponse202(
        document=UploadDocumentBodyDocument(
            id=document.id,
            project_id=document.project_id,
            screen_name=document.screen_name,
            doc_type=str(document.doc_type),
            description=document.description,
        ),
        version=UploadDocumentBodyVersion(
            id=version.id,
            version_no=version.version_no,
            status=str(version.status),
            r2_key=version.r2_key,
            created_at=version.created_at,
        ),
        job_id=str(job.id),
        message="File đã được tải lên. Đang xử lý tài liệu...",
    )

