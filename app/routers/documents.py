"""Document versions, download, patch, delete (S3_DOCUMENT_LIST_DESIGN.md)."""

import asyncio
import mimetypes
import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from redis.exceptions import RedisError
from sqlalchemy import column, func, select, table, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.deps import get_current_user
from app.exceptions import ApiError
from app.models.document import Chunk, DocVersion, Document
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.worker import enqueue_version_processing
from app.project_access import can_patch_or_delete_document, is_system_admin, project_member_role, require_project_access
from app.r2_presign import public_download_url, try_presign_download
from app.r2_upload import upload_to_r2
from app.redis_client import get_redis
from app.schemas.documents import (
    ApproverBrief,
    DeleteVersionResponse,
    DocumentDeleteResponse,
    DocumentPatchBody,
    DocumentPatchResponse,
    DocUserBrief,
    DownloadUrlResponse,
    UploadVersionBodyVersion,
    UploadVersionPreviousVersion,
    UploadVersionResponse202,
    VersionEmbedProgress,
    VersionDetailOut,
    VersionsListResponse,
    VersionStatusResponse,
)
from app.schemas.viewer import (
    DocumentChunksOutlineResponse,
    DocumentViewerResponse,
    ViewerChunkOut,
    ViewerDocumentOut,
    ViewerFigmaFrameOut,
    ViewerUserBrief,
    ViewerVersionItem,
    ViewerVersionOut,
)

router = APIRouter()

MAX_BYTES = 50 * 1024 * 1024
ALLOWED_DOC_TYPES = {"basic_design", "api_design", "detail_design", "testcase_manual"}

EXT_BY_DOC_TYPE: dict[str, set[str]] = {
    "basic_design": {".md"},
    "detail_design": {".md"},
    "api_design": {".md"},
    "testcase_manual": {".md"},
}

_chunks = table("chunks", column("id"), column("doc_version_id"))
_chunks_full = table(
    "chunks",
    column("id"),
    column("doc_version_id"),
    column("chunk_index"),
    column("content_text"),
    column("metadata"),
    column("token_count"),
)
_doc_versions = table(
    "doc_versions",
    column("id"),
    column("document_id"),
    column("version_no"),
    column("status"),
    column("changelog_md"),
    column("created_at"),
    column("created_by"),
    column("approved_at"),
)
_documents = table("documents", column("id"), column("project_id"), column("screen_name"), column("doc_type"))
_users = table("users", column("id"), column("full_name"))
_tc_links = table("testcase_chunk_links", column("chunk_id"), column("testcase_id"))
_figma_frames = table(
    "figma_frames",
    column("id"),
    column("document_id"),
    column("frame_id"),
    column("frame_name"),
    column("figma_url"),
    column("snapshot_url"),
    column("synced_at"),
)


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


async def _document_or_404(session: AsyncSession, document_id: uuid.UUID) -> Document:
    d = await session.get(Document, document_id)
    if d is None:
        raise ApiError(404, "NOT_FOUND", "Document không tồn tại")
    return d


async def _load_users(session: AsyncSession, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not user_ids:
        return {}
    res = await session.execute(select(User).where(User.id.in_(user_ids)))
    return {u.id: u for u in res.scalars().all()}


def _user_brief(u: User | None) -> DocUserBrief | None:
    if u is None:
        return None
    return DocUserBrief(id=u.id, full_name=u.full_name, avatar_url=u.avatar_url)


def _approver_brief(u: User | None) -> ApproverBrief | None:
    if u is None:
        return None
    return ApproverBrief(id=u.id, full_name=u.full_name)


def _filename_from_key(r2_key: str, screen_name: str, doc_type: str, version_no: int) -> str:
    ext = ""
    if "." in r2_key.rsplit("/", 1)[-1]:
        ext = "." + r2_key.rsplit(".", 1)[-1]
    safe_screen = "".join(c if c.isalnum() or c in "._-" else "_" for c in screen_name)[:80]
    return f"{safe_screen}_{doc_type}_v{version_no}{ext}"


def _sanitize_filename(filename: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._-+" else "_" for c in (filename or ""))
    safe = safe.replace(" ", "_")
    return safe[:120] if safe else "file"


def _file_extension(filename: str) -> str:
    lower = (filename or "").lower()
    idx = lower.rfind(".")
    return lower[idx:] if idx >= 0 else ""


def _validate_file_for_doc_type(doc_type: str, filename: str) -> None:
    dt = (doc_type or "").lower().strip()
    if dt not in ALLOWED_DOC_TYPES:
        raise ApiError(422, "VALIDATION_ERROR", "doc_type không hợp lệ")
    ext = _file_extension(filename)
    allowed = EXT_BY_DOC_TYPE.get(dt, set())
    if ext not in allowed:
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", f"Loại file {ext or 'unknown'} không hỗ trợ cho {dt}")


def _make_r2_key(project_id: uuid.UUID, document_id: uuid.UUID, version_no: int, filename: str) -> str:
    safe = _sanitize_filename(filename)
    return f"{project_id}/{document_id}/v{version_no}/{uuid.uuid4().hex}_{safe}"


@router.get("/{document_id}/versions", response_model=VersionsListResponse)
async def list_document_versions(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    document_id: uuid.UUID,
) -> VersionsListResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:doc:ver:{user.id}", 120)

    d = await _document_or_404(session, document_id)
    await require_project_access(session, user, d.project_id)

    vers = (
        (
            await session.execute(
                select(DocVersion).where(DocVersion.document_id == document_id).order_by(DocVersion.version_no.desc())
            )
        )
        .scalars()
        .all()
    )
    if not vers:
        dt = d.doc_type if isinstance(d.doc_type, str) else str(d.doc_type)
        return VersionsListResponse(
            document_id=d.id,
            screen_name=d.screen_name,
            doc_type=dt,
            versions=[],
            total_versions=0,
        )

    max_no = max(v.version_no for v in vers)
    vids = [v.id for v in vers]
    uids: set[uuid.UUID] = set()
    for v in vers:
        if v.created_by:
            uids.add(v.created_by)
        if v.approved_by:
            uids.add(v.approved_by)
    umap = await _load_users(session, uids)

    chunk_rows = (
        await session.execute(select(Chunk.doc_version_id, func.count()).where(Chunk.doc_version_id.in_(vids)).group_by(Chunk.doc_version_id))
    ).all()
    chunk_map = {r[0]: int(r[1]) for r in chunk_rows}

    out: list[VersionDetailOut] = []
    for v in vers:
        st = v.status if isinstance(v.status, str) else str(v.status)
        dt = d.doc_type if isinstance(d.doc_type, str) else str(d.doc_type)
        out.append(
            VersionDetailOut(
                id=v.id,
                version_no=v.version_no,
                status=st,
                r2_url=v.r2_url,
                changelog_md=v.changelog_md,
                created_at=v.created_at,
                created_by=_user_brief(umap.get(v.created_by)) if v.created_by else None,
                approved_by=_approver_brief(umap.get(v.approved_by)) if v.approved_by else None,
                approved_at=v.approved_at,
                chunk_count=chunk_map.get(v.id, 0),
                is_latest=v.version_no == max_no,
            )
        )

    dt = d.doc_type if isinstance(d.doc_type, str) else str(d.doc_type)
    return VersionsListResponse(
        document_id=d.id,
        screen_name=d.screen_name,
        doc_type=dt,
        versions=out,
        total_versions=len(out),
    )


def _doc_type_from_doc(d: Document) -> str:
    return d.doc_type if isinstance(d.doc_type, str) else str(d.doc_type)


def _can_view_unapproved_versions(user: User, project_role: str | None) -> bool:
    # Spec: all_versions excludes draft/rejected for QC/Dev. PM/Admin/Owner can see more.
    if is_system_admin(user):
        return True
    return (project_role or "").lower() in {"owner", "pm"}


@router.get("/{document_id}/viewer", response_model=DocumentViewerResponse)
async def get_document_viewer(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    document_id: uuid.UUID,
    version_id: Annotated[uuid.UUID | None, Query()] = None,
    include_tc_count: Annotated[bool, Query()] = True,
) -> DocumentViewerResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:doc:viewer:{user.id}", 60)

    d = await _document_or_404(session, document_id)
    await require_project_access(session, user, d.project_id)
    role = await project_member_role(session, user.id, d.project_id)

    # Decide current version
    current_vid: uuid.UUID | None = None
    if version_id is not None:
        v = await session.get(DocVersion, version_id)
        if v is None or v.document_id != document_id:
            raise ApiError(404, "NOT_FOUND", "Version không tồn tại")
        current_vid = v.id
    else:
        # Default: latest approved version
        vr = (
            await session.execute(
                select(DocVersion)
                .where(DocVersion.document_id == document_id, DocVersion.status == "approved")
                .order_by(DocVersion.version_no.desc())
                .limit(1)
            )
        ).scalars().first()
        if vr is None:
            latest_any = (
                await session.execute(
                    select(DocVersion)
                    .where(DocVersion.document_id == document_id)
                    .order_by(DocVersion.version_no.desc())
                    .limit(1)
                )
            ).scalars().first()
            extra = {}
            if latest_any is not None:
                extra["latest_version"] = {
                    "id": latest_any.id,
                    "version_no": latest_any.version_no,
                    "status": str(latest_any.status).lower(),
                }
            raise ApiError(404, "NO_APPROVED_VERSION", "Tài liệu này chưa có version nào được duyệt.", extra=extra)
        current_vid = vr.id

    # all_versions for toolbar dropdown
    allowed_statuses = {"approved", "ready_for_review", "processing"}
    versions_q = (
        await session.execute(
            select(DocVersion)
            .where(DocVersion.document_id == document_id)
            .order_by(DocVersion.version_no.desc())
        )
    ).scalars().all()

    all_versions: list[ViewerVersionItem] = []
    for v in versions_q:
        st = str(v.status).lower()
        if st not in allowed_statuses:
            # draft/rejected only visible to PM/Admin/Owner
            if not _can_view_unapproved_versions(user, role):
                continue
        all_versions.append(
            ViewerVersionItem(
                id=v.id,
                version_no=v.version_no,
                status=st,
                is_current=(v.id == current_vid),
            )
        )

    cv = await session.get(DocVersion, current_vid)
    if cv is None:
        raise ApiError(404, "NOT_FOUND", "Version không tồn tại")

    # created_by brief
    created_by_brief: ViewerUserBrief | None = None
    if cv.created_by:
        ur = await session.execute(select(_users.c.full_name).where(_users.c.id == cv.created_by))
        fullname = ur.scalar_one_or_none()
        if fullname:
            created_by_brief = ViewerUserBrief(id=cv.created_by, full_name=fullname)

    # chunks for the version
    if include_tc_count:
        tc_count_sub = (
            select(_tc_links.c.chunk_id, func.count(_tc_links.c.testcase_id).label("tc_count"))
            .group_by(_tc_links.c.chunk_id)
            .subquery()
        )
        cr = await session.execute(
            select(
                _chunks_full.c.id,
                _chunks_full.c.chunk_index,
                _chunks_full.c.content_text,
                _chunks_full.c.metadata,
                _chunks_full.c.token_count,
                func.coalesce(tc_count_sub.c.tc_count, 0).label("tc_count"),
            )
            .select_from(_chunks_full.outerjoin(tc_count_sub, tc_count_sub.c.chunk_id == _chunks_full.c.id))
            .where(_chunks_full.c.doc_version_id == current_vid)
            .order_by(_chunks_full.c.chunk_index.asc())
        )
    else:
        cr = await session.execute(
            select(
                _chunks_full.c.id,
                _chunks_full.c.chunk_index,
                _chunks_full.c.content_text,
                _chunks_full.c.metadata,
                _chunks_full.c.token_count,
            )
            .where(_chunks_full.c.doc_version_id == current_vid)
            .order_by(_chunks_full.c.chunk_index.asc())
        )

    chunks: list[ViewerChunkOut] = []
    for r in cr.all():
        meta = r.metadata if isinstance(r.metadata, dict) else None
        chunks.append(
            ViewerChunkOut(
                id=r.id,
                chunk_index=int(r.chunk_index),
                content_text=r.content_text,
                metadata=meta,
                token_count=r.token_count,
                tc_count=int(r.tc_count) if include_tc_count else None,
            )
        )

    # figma frames (optional)
    figma_frames: list[ViewerFigmaFrameOut] | None = None
    dt = _doc_type_from_doc(d)
    if dt == "figma":
        fr = await session.execute(
            select(
                _figma_frames.c.frame_id,
                _figma_frames.c.frame_name,
                _figma_frames.c.figma_url,
                _figma_frames.c.snapshot_url,
                _figma_frames.c.synced_at,
            )
            .where(_figma_frames.c.document_id == document_id)
            .order_by(_figma_frames.c.synced_at.desc().nullslast())
        )
        figma_frames = [
            ViewerFigmaFrameOut(
                frame_id=r.frame_id,
                frame_name=r.frame_name,
                figma_url=r.figma_url,
                snapshot_url=r.snapshot_url,
                synced_at=r.synced_at,
            )
            for r in fr.all()
        ]

    return DocumentViewerResponse(
        document=ViewerDocumentOut(
            id=d.id,
            screen_name=d.screen_name,
            doc_type=dt,
            project_id=d.project_id,
        ),
        version=ViewerVersionOut(
            id=cv.id,
            version_no=cv.version_no,
            status=str(cv.status).lower(),
            changelog_md=cv.changelog_md,
            created_at=cv.created_at,
            created_by=created_by_brief,
            approved_at=cv.approved_at,
        ),
        all_versions=all_versions,
        chunks=chunks,
        total_chunks=len(chunks),
        figma_frames=figma_frames,
    )


@router.get("/{document_id}/chunks", response_model=DocumentChunksOutlineResponse)
async def get_document_chunks_outline(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    document_id: uuid.UUID,
    version_id: Annotated[uuid.UUID | None, Query()] = None,
) -> DocumentChunksOutlineResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:doc:outline:{user.id}", 60)

    d = await _document_or_404(session, document_id)
    await require_project_access(session, user, d.project_id)

    # choose version: explicit or latest approved (fallback latest any)
    if version_id is None:
        vr = (
            await session.execute(
                select(DocVersion)
                .where(DocVersion.document_id == document_id, DocVersion.status == "approved")
                .order_by(DocVersion.version_no.desc())
                .limit(1)
            )
        ).scalars().first()
        if vr is None:
            vr = (
                await session.execute(
                    select(DocVersion).where(DocVersion.document_id == document_id).order_by(DocVersion.version_no.desc()).limit(1)
                )
            ).scalars().first()
        if vr is None:
            raise ApiError(404, "NOT_FOUND", "Document không có version")
        version_id = vr.id
    else:
        v = await session.get(DocVersion, version_id)
        if v is None or v.document_id != document_id:
            raise ApiError(404, "NOT_FOUND", "Version không tồn tại")

    tc_count_sub = (
        select(_tc_links.c.chunk_id, func.count(_tc_links.c.testcase_id).label("tc_count"))
        .group_by(_tc_links.c.chunk_id)
        .subquery()
    )
    cr = await session.execute(
        select(
            _chunks_full.c.id,
            _chunks_full.c.chunk_index,
            _chunks_full.c.metadata,
            _chunks_full.c.token_count,
            func.coalesce(tc_count_sub.c.tc_count, 0).label("tc_count"),
        )
        .select_from(_chunks_full.outerjoin(tc_count_sub, tc_count_sub.c.chunk_id == _chunks_full.c.id))
        .where(_chunks_full.c.doc_version_id == version_id)
        .order_by(_chunks_full.c.chunk_index.asc())
    )
    chunks = []
    for r in cr.all():
        meta = r.metadata if isinstance(r.metadata, dict) else None
        section = (meta or {}).get("section")
        chunks.append(
            {
                "id": r.id,
                "chunk_index": int(r.chunk_index),
                "section": section,
                "token_count": r.token_count,
                "tc_count": int(r.tc_count),
            }
        )

    return DocumentChunksOutlineResponse(
        document_id=document_id,
        version_id=version_id,
        chunks=chunks,
        total=len(chunks),
    )


@router.post(
    "/{document_id}/versions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadVersionResponse202,
)
async def upload_document_version(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    document_id: uuid.UUID,
    file: UploadFile = File(...),
    changelog_md: str = Form(...),
) -> UploadVersionResponse202:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:doc:upload:ver:{user.id}", 20)

    d = await _document_or_404(session, document_id)
    await require_project_access(session, user, d.project_id)

    # Permissions: owner/admin or project PM (S4)
    role = await project_member_role(session, user.id, d.project_id)
    if not (is_system_admin(user) or (role or "").lower() in {"owner", "pm"}):
        raise ApiError(403, "FORBIDDEN", "Bạn không có quyền upload version tài liệu")

    if d.doc_type is None:
        raise ApiError(422, "VALIDATION_ERROR", "Document không có doc_type hợp lệ")

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "File vượt quá giới hạn 50MB")

    dt = _doc_type_from_doc(d)
    _validate_file_for_doc_type(dt, file.filename or "")

    # Compute next version no
    latest = (
        await session.execute(
            select(DocVersion)
            .where(DocVersion.document_id == document_id)
            .order_by(DocVersion.version_no.desc())
            .limit(1)
        )
    ).scalars().first()

    latest_status = str(latest.status).lower() if latest else None
    if latest and latest_status == "processing":
        raise ApiError(
            409,
            "VERSION_PROCESSING",
            "Version đang được xử lý. Vui lòng chờ hoàn thành trước khi upload tiếp.",
            extra={
                "processing_version": {
                    "id": latest.id,
                    "version_no": latest.version_no,
                    "status": latest_status,
                }
            },
        )

    next_version_no = (latest.version_no + 1) if latest else 1

    cl = (changelog_md or "").strip()
    if next_version_no >= 2:
        if not cl or len(cl) < 10:
            raise ApiError(400, "BAD_REQUEST", "Changelog quá ngắn hoặc thiếu. Ít nhất 10 ký tự")
    if next_version_no == 1 and not cl:
        # allow empty for version 1, though versions endpoint usually used >= 2
        cl = None

    r2_key = _make_r2_key(d.project_id, d.id, next_version_no, file.filename or f"v{next_version_no}")
    r2_url = public_download_url(r2_key) or r2_key

    content_type = file.content_type or "application/octet-stream"
    await asyncio.to_thread(upload_to_r2, r2_key, content, content_type)

    version = DocVersion(
        document_id=document_id,
        version_no=next_version_no,
        r2_key=r2_key,
        r2_url=r2_url,
        status="processing",
        changelog_md=cl,
        created_by=user.id,
    )
    session.add(version)
    await session.commit()
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

    prev = (
        UploadVersionPreviousVersion(id=latest.id, version_no=latest.version_no, status=str(latest.status).lower())
        if latest
        else UploadVersionPreviousVersion(id=version.id, version_no=1, status="processing")
    )

    return UploadVersionResponse202(
        document_id=document_id,
        version=UploadVersionBodyVersion(
            id=version.id,
            version_no=version.version_no,
            status=str(version.status).lower(),
            r2_key=version.r2_key,
            changelog_md=version.changelog_md,
            created_at=version.created_at,
        ),
        previous_version=prev,
        diff_job_id=None,
        embed_job_id=str(job.id),
        message=f"Version {next_version_no} đang được xử lý...",
    )


@router.get(
    "/{document_id}/versions/{version_id}/status",
    response_model=VersionStatusResponse,
)
async def get_version_status(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> VersionStatusResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:doc:verstat:{user.id}", 120)

    d = await _document_or_404(session, document_id)
    await require_project_access(session, user, d.project_id)

    v = await session.get(DocVersion, version_id)
    if v is None or v.document_id != document_id:
        raise ApiError(404, "NOT_FOUND", "Version không tồn tại")

    chunk_count = int(
        (await session.execute(select(func.count()).select_from(_chunks).where(_chunks.c.doc_version_id == version_id))).scalar_one()
    )

    st = str(v.status).lower()
    if st == "processing":
        total = chunk_count
        embedded = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(text("chunk_embeddings ce JOIN chunks c ON c.id = ce.chunk_id"))
                    .where(text("c.doc_version_id = :vid").bindparams(vid=version_id))
                )
            ).scalar_one()
        )
        percentage = int(round((embedded / total) * 100)) if total > 0 else 0
        embed_progress = {"total_chunks": total, "embedded_chunks": embedded, "percentage": percentage}
        return VersionStatusResponse(
            version_id=version_id,
            version_no=v.version_no,
            status=st,
            chunk_count=chunk_count,
            embed_progress=VersionEmbedProgress(
                total_chunks=total,
                embedded_chunks=embedded,
                percentage=percentage,
            ),
            diff_ready=False,
            diff_review_id=None,
            updated_at=v.updated_at,
        )

    return VersionStatusResponse(
        version_id=version_id,
        version_no=v.version_no,
        status=st,
        chunk_count=chunk_count,
        embed_progress=None,
        diff_ready=False,
        diff_review_id=None,
        updated_at=v.updated_at,
    )


@router.delete(
    "/{document_id}/versions/{version_id}",
    response_model=DeleteVersionResponse,
)
async def delete_document_version(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> DeleteVersionResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:doc:vdel:{user.id}", 10)

    d = await _document_or_404(session, document_id)
    await require_project_access(session, user, d.project_id)

    role = await project_member_role(session, user.id, d.project_id)
    if not (is_system_admin(user) or (role or "").lower() == "owner"):
        raise ApiError(403, "FORBIDDEN", "Không có quyền xoá version")

    v = await session.get(DocVersion, version_id)
    if v is None or v.document_id != document_id:
        raise ApiError(404, "NOT_FOUND", "Version không tồn tại")

    st = str(v.status).lower()
    if st not in {"draft", "rejected"}:
        raise ApiError(
            409,
            "INVALID_VERSION_DELETE",
            "Không thể xoá version ở trạng thái này. Chỉ xoá draft hoặc rejected.",
        )

    versions_count = int(
        (await session.execute(select(func.count()).select_from(DocVersion).where(DocVersion.document_id == document_id))).scalar_one()
    )
    if versions_count <= 1:
        raise ApiError(409, "VERSION_SINGLE", "Không thể xoá version duy nhất. Hãy xoá document thay vì xoá version.")

    # Count chunks for response
    deleted_chunks = int(
        (await session.execute(select(func.count()).select_from(_chunks).where(_chunks.c.doc_version_id == version_id))).scalar_one()
    )

    await session.delete(v)
    await session.commit()

    remaining_versions = versions_count - 1

    return DeleteVersionResponse(
        message=f"Đã xoá version {v.version_no}",
        version_id=version_id,
        deleted_chunks=deleted_chunks,
        document_id=document_id,
        remaining_versions=remaining_versions,
    )


@router.get("/{document_id}/versions/{version_id}/download", response_model=DownloadUrlResponse)
async def presign_version_download(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    document_id: uuid.UUID,
    version_id: uuid.UUID,
) -> DownloadUrlResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:doc:dl:{user.id}", 30)

    d = await _document_or_404(session, document_id)
    await require_project_access(session, user, d.project_id)

    v = await session.get(DocVersion, version_id)
    if v is None or v.document_id != document_id:
        raise ApiError(404, "NOT_FOUND", "Version không tồn tại")

    dt = d.doc_type if isinstance(d.doc_type, str) else str(d.doc_type)
    filename = _filename_from_key(v.r2_key, d.screen_name, dt, v.version_no)
    ctype, _ = mimetypes.guess_type(filename)
    content_type = ctype or "application/octet-stream"

    expires_in = 900
    signed = try_presign_download(v.r2_key, expires_seconds=expires_in)
    if signed:
        url = signed
    else:
        pub = public_download_url(v.r2_key)
        url = pub if pub else v.r2_url

    return DownloadUrlResponse(download_url=url, filename=filename, content_type=content_type, expires_in=expires_in)


@router.patch("/{document_id}", response_model=DocumentPatchResponse)
async def patch_document(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    document_id: uuid.UUID,
    body: DocumentPatchBody,
) -> DocumentPatchResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:doc:patch:{user.id}", 20)

    d = await _document_or_404(session, document_id)
    await require_project_access(session, user, d.project_id)
    role = await project_member_role(session, user.id, d.project_id)
    if not can_patch_or_delete_document(user, role):
        raise ApiError(403, "FORBIDDEN", "Không có quyền")

    if body.screen_name is None and body.description is None:
        raise ApiError(400, "BAD_REQUEST", "Không có field nào để cập nhật")

    vals: dict = {}
    if body.screen_name is not None:
        vals["screen_name"] = body.screen_name.strip()
    if body.description is not None:
        vals["description"] = body.description.strip() or None

    if vals:
        vals["updated_at"] = func.now()
        try:
            await session.execute(update(Document).where(Document.id == document_id).values(**vals))
            await session.commit()
        except IntegrityError as e:
            await session.rollback()
            raise ApiError(
                409,
                "CONFLICT",
                "Tên màn hình đã tồn tại với loại tài liệu này",
                extra={"field": "screen_name"},
            ) from e

    d = await session.get(Document, document_id)
    if d is None:
        raise ApiError(404, "NOT_FOUND", "Document không tồn tại")
    dt = d.doc_type if isinstance(d.doc_type, str) else str(d.doc_type)
    return DocumentPatchResponse(
        id=d.id,
        screen_name=d.screen_name,
        doc_type=dt,
        description=d.description,
        updated_at=d.updated_at,
    )


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    document_id: uuid.UUID,
) -> DocumentDeleteResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:doc:del:{user.id}", 10)

    d = await _document_or_404(session, document_id)
    await require_project_access(session, user, d.project_id)
    role = await project_member_role(session, user.id, d.project_id)
    if not can_patch_or_delete_document(user, role):
        raise ApiError(403, "FORBIDDEN", "Không có quyền xoá tài liệu. Chỉ Owner và Admin mới có thể xoá.")

    ver_ids = (
        await session.execute(select(DocVersion.id).where(DocVersion.document_id == document_id))
    ).scalars().all()
    deleted_versions = len(ver_ids)

    deleted_chunks = 0
    unlinked_testcases = 0
    if ver_ids:
        chunks_t = table("chunks", column("id"), column("doc_version_id"))
        links_t = table("testcase_chunk_links", column("chunk_id"), column("testcase_id"))

        deleted_chunks = int(
            (await session.execute(select(func.count()).select_from(chunks_t).where(chunks_t.c.doc_version_id.in_(ver_ids)))).scalar_one()
        )
        chunk_ids_sub = select(chunks_t.c.id).where(chunks_t.c.doc_version_id.in_(ver_ids))
        unlinked_testcases = int(
            (
                await session.execute(
                    select(func.count(func.distinct(links_t.c.testcase_id))).where(links_t.c.chunk_id.in_(chunk_ids_sub))
                )
            ).scalar_one()
        )

    await session.delete(d)
    await session.commit()

    return DocumentDeleteResponse(
        message=f"Đã xoá tài liệu và {deleted_versions} version liên quan",
        document_id=document_id,
        deleted_versions=deleted_versions,
        deleted_chunks=deleted_chunks,
        unlinked_testcases=unlinked_testcases,
    )
