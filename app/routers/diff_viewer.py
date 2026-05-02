"""Diff viewer APIs (S7_DIFF_VIEWER_DESIGN.md)."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy import column, func, select, table, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.deps import get_current_user
from app.exceptions import ApiError
from app.models.document import Chunk, DocVersion, Document
from app.models.user import User
from app.project_access import is_project_owner, is_system_admin, project_member_role, require_project_access
from app.worker import enqueue_diff_analysis
from app.redis_client import get_redis
from app.schemas.diff_viewer import (
    DiffChangeOut,
    DiffChunkOut,
    DiffHistoryChangeItem,
    DiffHistoryReviewItem,
    DiffHistoryVersionItem,
    DiffReviewOut,
    DiffReviewStatusProgress,
    DiffReviewStatusResponse,
    GetDiffHistoryResponse,
    GetDocumentDiffResponse,
    PatchDiffChangeBody,
    PatchDiffChangeResponse,
    SubmitDiffReviewBody,
    SubmitDiffReviewResponse,
    UserBrief,
    VersionBrief,
)

router = APIRouter()

_diff_reviews = table(
    "diff_reviews",
    column("id"),
    column("old_version_id"),
    column("new_version_id"),
    column("diff_summary"),
    column("total_changes"),
    column("approved_count"),
    column("rejected_count"),
    column("status"),
    column("ai_summary"),
    column("reviewed_at"),
    column("reviewed_by"),
    column("review_note"),
    column("created_at"),
)

_diff_changes = table(
    "diff_changes",
    column("id"),
    column("diff_review_id"),
    column("change_type"),
    column("approval_status"),
    column("approve_note"),
    column("approved_at"),
    column("approved_by"),
    column("chunk_old_id"),
    column("chunk_new_id"),
    column("content_before"),
    column("content_after"),
    column("similarity_score"),
    column("created_at"),
)

_doc_versions_for_join = table("doc_versions", column("id"), column("document_id"))


def _str_enum(v: object) -> str:
    return v if isinstance(v, str) else str(v)


async def _document_for_diff_review_row(session: AsyncSession, rev: Any) -> Document | None:
    """diff_reviews has no document_id — resolve via new_version (fallback old_version)."""
    doc_id: uuid.UUID | None = None
    if getattr(rev, "new_version_id", None):
        nv = await session.get(DocVersion, rev.new_version_id)
        if nv is not None:
            doc_id = nv.document_id
    if doc_id is None and getattr(rev, "old_version_id", None):
        ov = await session.get(DocVersion, rev.old_version_id)
        if ov is not None:
            doc_id = ov.document_id
    if doc_id is None:
        return None
    return await session.get(Document, doc_id)


def _status_for_api(review_row: Any, *, loaded_change_count: int | None = None) -> str:
    """Map DB diff_status (pending|approved|rejected) to S7 API (processing|ready|approved|rejected)."""
    st = _str_enum(review_row.status).lower()
    if st == "pending":
        n_db = int(review_row.total_changes or 0)
        n = loaded_change_count if loaded_change_count is not None else n_db
        if n == 0:
            return "processing"
        return "ready"
    return _str_enum(review_row.status)


def _status_for_polling_endpoint(review_row: Any, change_n_i: int) -> str:
    """Same mapping as `_status_for_api` but uses pre-counted rows for `/status` polling."""
    return _status_for_api(review_row, loaded_change_count=change_n_i)


def _can_review(project_role: str | None, user: User) -> bool:
    if is_system_admin(user):
        return True
    return (project_role or "").lower() in {"owner", "pm"}


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


def _diff_review_out(
    *,
    review_row: Any,
    old_ver: DocVersion | None,
    new_ver: DocVersion | None,
    doc: Document | None,
    reviewed_by: User | None,
    loaded_change_count: int | None = None,
) -> DiffReviewOut:
    raw_status = _str_enum(review_row.status).lower()
    display_status = _status_for_api(review_row, loaded_change_count=loaded_change_count)
    total_changes = int(review_row.total_changes or 0)
    approved_count = int(review_row.approved_count or 0)
    rejected_count = int(review_row.rejected_count or 0)
    pending_count = max(0, total_changes - approved_count - rejected_count)

    old_v = None
    if old_ver is not None:
        old_v = VersionBrief(
            id=old_ver.id,
            version_no=old_ver.version_no,
            status=(old_ver.status if isinstance(old_ver.status, str) else str(old_ver.status)),
            created_at=old_ver.created_at,
            changelog_md=old_ver.changelog_md,
        )

    new_v = None
    if new_ver is not None:
        new_v = VersionBrief(
            id=new_ver.id,
            version_no=new_ver.version_no,
            status=(new_ver.status if isinstance(new_ver.status, str) else str(new_ver.status)),
            created_at=new_ver.created_at,
            changelog_md=new_ver.changelog_md,
        )

    readonly = raw_status == "approved"
    if new_ver is not None:
        nv = (new_ver.status if isinstance(new_ver.status, str) else str(new_ver.status)).lower()
        if nv in {"approved", "rejected"}:
            readonly = True

    return DiffReviewOut(
        id=review_row.id,
        document_id=(doc.id if doc is not None else None),
        old_version=old_v,
        new_version=new_v,
        status=display_status,
        is_readonly=readonly,
        ai_summary=review_row.ai_summary,
        total_changes=total_changes,
        approved_count=approved_count,
        rejected_count=rejected_count,
        pending_count=pending_count,
        reviewed_at=review_row.reviewed_at,
        reviewed_by=(UserBrief(id=reviewed_by.id, full_name=reviewed_by.full_name) if reviewed_by else None),
        created_at=review_row.created_at,
        estimated_seconds=(20 if display_status == "processing" else None),
    )


async def _chunk_out(session: AsyncSession, chunk_id: uuid.UUID | None) -> DiffChunkOut | None:
    if chunk_id is None:
        return None
    c = await session.get(Chunk, chunk_id)
    if c is None:
        return None
    md = c.metadata_ or {}
    section = md.get("section") if isinstance(md, dict) else None
    return DiffChunkOut(id=c.id, chunk_index=c.chunk_index, content_text=c.content_text, section=section)


async def _generate_basic_diff_changes(
    session: AsyncSession,
    *,
    diff_review_id: uuid.UUID,
    old_version_id: uuid.UUID,
    new_version_id: uuid.UUID,
) -> int:
    """Generate minimal diff_changes from chunks by chunk_index.

    Fallback so FE can show changes without async AI worker.
    """
    old_rows = (
        await session.execute(
            select(Chunk.id, Chunk.chunk_index, Chunk.content_text).where(Chunk.doc_version_id == old_version_id)
        )
    ).all()
    new_rows = (
        await session.execute(
            select(Chunk.id, Chunk.chunk_index, Chunk.content_text).where(Chunk.doc_version_id == new_version_id)
        )
    ).all()

    old_by_idx = {int(r.chunk_index): (r.id, r.content_text) for r in old_rows}
    new_by_idx = {int(r.chunk_index): (r.id, r.content_text) for r in new_rows}
    all_idx = sorted(set(old_by_idx.keys()) | set(new_by_idx.keys()))

    inserted = 0
    for idx in all_idx:
        old = old_by_idx.get(idx)
        new = new_by_idx.get(idx)
        if old is None and new is None:
            continue

        if old is None:
            chg_type = "added"
            chunk_old_id = None
            chunk_new_id = new[0]
            before = None
            after = new[1]
        elif new is None:
            chg_type = "removed"
            chunk_old_id = old[0]
            chunk_new_id = None
            before = old[1]
            after = None
        else:
            if (old[1] or "").strip() == (new[1] or "").strip():
                continue
            chg_type = "modified"
            chunk_old_id = old[0]
            chunk_new_id = new[0]
            before = old[1]
            after = new[1]

        await session.execute(
            text(
                """
                INSERT INTO diff_changes
                  (id, diff_review_id, chunk_old_id, chunk_new_id, change_type,
                   content_before, content_after, approval_status, created_at)
                VALUES
                  (:id, :diff_review_id, :chunk_old_id, :chunk_new_id, :change_type,
                   :content_before, :content_after, 'pending'::diff_status, now())
                """
            ),
            {
                "id": uuid.uuid4(),
                "diff_review_id": diff_review_id,
                "chunk_old_id": chunk_old_id,
                "chunk_new_id": chunk_new_id,
                "change_type": chg_type,
                "content_before": before,
                "content_after": after,
            },
        )
        inserted += 1

    if inserted > 0:
        await session.execute(
            update(_diff_reviews)
            .where(_diff_reviews.c.id == diff_review_id)
            .values(
                total_changes=inserted,
                approved_count=0,
                rejected_count=0,
                ai_summary=f"Tìm thấy {inserted} thay đổi (basic diff).",
            )
        )
    return inserted


async def _load_diff_changes(session: AsyncSession, diff_review_id: uuid.UUID) -> list[DiffChangeOut]:
    rows = (
        await session.execute(
            select(_diff_changes)
            .where(_diff_changes.c.diff_review_id == diff_review_id)
            .order_by(_diff_changes.c.created_at.asc().nulls_first(), _diff_changes.c.id.asc())
        )
    ).all()
    out: list[DiffChangeOut] = []
    for idx, r in enumerate(rows, start=1):
        chunk_old = await _chunk_out(session, r.chunk_old_id)
        chunk_new = await _chunk_out(session, r.chunk_new_id)
        out.append(
            DiffChangeOut(
                id=r.id,
                change_index=idx,
                change_type=r.change_type,
                approval_status=r.approval_status,
                chunk_old=chunk_old,
                chunk_new=chunk_new,
                word_diff_old=r.content_before,
                word_diff_new=r.content_after,
                similarity_score=float(r.similarity_score) if r.similarity_score is not None else None,
                affected_testcases=[],
                approve_note=r.approve_note,
            )
        )
    return out


async def _recount_and_update_review_counters(session: AsyncSession, diff_review_id: uuid.UUID) -> dict[str, int]:
    approved = (
        await session.execute(
            select(func.count()).select_from(_diff_changes).where(
                (_diff_changes.c.diff_review_id == diff_review_id) & (_diff_changes.c.approval_status == "approved")
            )
        )
    ).scalar_one()
    rejected = (
        await session.execute(
            select(func.count()).select_from(_diff_changes).where(
                (_diff_changes.c.diff_review_id == diff_review_id) & (_diff_changes.c.approval_status == "rejected")
            )
        )
    ).scalar_one()
    total = (
        await session.execute(
            select(func.count()).select_from(_diff_changes).where(_diff_changes.c.diff_review_id == diff_review_id)
        )
    ).scalar_one()
    approved_i, rejected_i, total_i = int(approved or 0), int(rejected or 0), int(total or 0)
    pending_i = max(0, total_i - approved_i - rejected_i)

    await session.execute(
        update(_diff_reviews)
        .where(_diff_reviews.c.id == diff_review_id)
        .values(
            total_changes=total_i,
            approved_count=approved_i,
            rejected_count=rejected_i,
        )
    )
    return {
        "total_changes": total_i,
        "approved_count": approved_i,
        "rejected_count": rejected_i,
        "pending_count": pending_i,
    }


async def _default_versions(session: AsyncSession, document_id: uuid.UUID) -> tuple[DocVersion | None, DocVersion | None]:
    old_v = (
        await session.execute(
            select(DocVersion)
            .where((DocVersion.document_id == document_id) & (DocVersion.status == "approved"))
            .order_by(DocVersion.version_no.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    new_v = (
        await session.execute(
            select(DocVersion)
            .where((DocVersion.document_id == document_id) & (DocVersion.status == "ready_for_review"))
            .order_by(DocVersion.version_no.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return old_v, new_v


@router.get("/documents/{document_id}/diff", response_model=GetDocumentDiffResponse)
async def get_or_create_document_diff(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    document_id: uuid.UUID,
    old_version_id: uuid.UUID | None = Query(default=None),
    new_version_id: uuid.UUID | None = Query(default=None),
) -> JSONResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:diff:get:{user.id}", 30)

    doc = await session.get(Document, document_id)
    if doc is None:
        raise ApiError(404, "NOT_FOUND", "Document không tồn tại")
    await require_project_access(session, user, doc.project_id)
    role = await project_member_role(session, user.id, doc.project_id)
    if not _can_review(role, user):
        raise ApiError(403, "FORBIDDEN", "Không có quyền xem diff")

    if old_version_id is None or new_version_id is None:
        d_old, d_new = await _default_versions(session, document_id)
        if old_version_id is None and d_old is not None:
            old_version_id = d_old.id
        if new_version_id is None and d_new is not None:
            new_version_id = d_new.id

    if old_version_id is None or new_version_id is None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy version phù hợp để so sánh")
    if old_version_id == new_version_id:
        raise ApiError(400, "VALIDATION_ERROR", "old_version và new_version trùng nhau")

    old_v = await session.get(DocVersion, old_version_id)
    new_v = await session.get(DocVersion, new_version_id)
    if old_v is None or new_v is None:
        raise ApiError(404, "NOT_FOUND", "Version không tồn tại")
    if old_v.document_id != document_id or new_v.document_id != document_id:
        raise ApiError(422, "VALIDATION_ERROR", "Version không thuộc cùng document")
    if int(new_v.version_no) <= int(old_v.version_no):
        raise ApiError(422, "VALIDATION_ERROR", "Version mới phải có số lớn hơn version cũ")

    existing = (
        await session.execute(
            select(_diff_reviews)
            .where(
                (_diff_reviews.c.old_version_id == old_version_id)
                & (_diff_reviews.c.new_version_id == new_version_id)
            )
            .order_by(_diff_reviews.c.created_at.desc().nulls_last(), _diff_reviews.c.id.desc())
            .limit(1)
        )
    ).first()

    if existing is None:
        diff_review_id = uuid.uuid4()
        now = datetime.now(UTC)
        await session.execute(
            text(
                """
                INSERT INTO diff_reviews
                  (id, old_version_id, new_version_id, diff_summary, status, ai_summary,
                   total_changes, approved_count, rejected_count, created_at)
                VALUES
                  (:id, :old_version_id, :new_version_id, '{}'::jsonb, 'pending'::diff_status, NULL,
                   0, 0, 0, :created_at)
                """
            ),
            {
                "id": diff_review_id,
                "old_version_id": old_version_id,
                "new_version_id": new_version_id,
                "created_at": now,
            },
        )
        await session.commit()
        await asyncio.to_thread(enqueue_diff_analysis, str(diff_review_id))
        review_stub = type(
            "Row",
            (),
            {
                "id": diff_review_id,
                "status": "pending",
                "ai_summary": None,
                "total_changes": 0,
                "approved_count": 0,
                "rejected_count": 0,
                "reviewed_at": None,
                "reviewed_by": None,
                "created_at": now,
            },
        )()
        body = GetDocumentDiffResponse(
            diff_review=_diff_review_out(
                review_row=review_stub,
                old_ver=old_v,
                new_ver=new_v,
                doc=doc,
                reviewed_by=None,
                loaded_change_count=0,
            ),
            changes=[],
            message="Đang phân tích sự khác biệt giữa 2 version. Vui lòng chờ.",
        ).model_dump(mode="json")
        return JSONResponse(status_code=202, content=body)

    review_row = existing
    reviewed_by = await session.get(User, review_row.reviewed_by) if review_row.reviewed_by else None

    changes = await _load_diff_changes(session, review_row.id)
    if len(changes) == 0 and _str_enum(review_row.status).lower() == "pending":
        # Give the semantic diff RQ job 5 minutes to finish before falling back.
        created_at = review_row.created_at
        if created_at is not None and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        job_still_running = created_at is not None and (datetime.now(UTC) - created_at) < timedelta(minutes=5)
        if not job_still_running:
            inserted = await _generate_basic_diff_changes(
                session,
                diff_review_id=review_row.id,
                old_version_id=old_version_id,
                new_version_id=new_version_id,
            )
            await session.commit()
            if inserted > 0:
                changes = await _load_diff_changes(session, review_row.id)
    display_status = _status_for_api(review_row, loaded_change_count=len(changes))
    if display_status == "processing":
        body = GetDocumentDiffResponse(
            diff_review=_diff_review_out(
                review_row=review_row,
                old_ver=old_v,
                new_ver=new_v,
                doc=doc,
                reviewed_by=reviewed_by,
                loaded_change_count=len(changes),
            ),
            changes=[],
            message="AI đang phân tích sự khác biệt giữa 2 version. Vui lòng chờ.",
        ).model_dump(mode="json")
        return JSONResponse(status_code=202, content=body)

    body = GetDocumentDiffResponse(
        diff_review=_diff_review_out(
            review_row=review_row,
            old_ver=old_v,
            new_ver=new_v,
            doc=doc,
            reviewed_by=reviewed_by,
            loaded_change_count=len(changes),
        ),
        changes=changes,
    ).model_dump(mode="json")
    return JSONResponse(status_code=200, content=body)


@router.get("/diff-reviews/{diff_review_id}", response_model=GetDocumentDiffResponse)
async def get_diff_review_detail(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    diff_review_id: uuid.UUID,
) -> JSONResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:diff:review:get:{user.id}", 60)

    review_row = (await session.execute(select(_diff_reviews).where(_diff_reviews.c.id == diff_review_id))).first()
    if review_row is None:
        raise ApiError(404, "NOT_FOUND", "Diff review không tồn tại")

    doc = await _document_for_diff_review_row(session, review_row)
    if doc is None:
        raise ApiError(404, "NOT_FOUND", "Document không tồn tại")
    await require_project_access(session, user, doc.project_id)
    role = await project_member_role(session, user.id, doc.project_id)
    if not _can_review(role, user):
        raise ApiError(403, "FORBIDDEN", "Không có quyền xem diff")

    old_v = await session.get(DocVersion, review_row.old_version_id)
    new_v = await session.get(DocVersion, review_row.new_version_id)
    reviewed_by = await session.get(User, review_row.reviewed_by) if review_row.reviewed_by else None

    changes = await _load_diff_changes(session, diff_review_id)
    display_status = _status_for_api(review_row, loaded_change_count=len(changes))
    if display_status == "processing":
        body = GetDocumentDiffResponse(
            diff_review=_diff_review_out(
                review_row=review_row,
                old_ver=old_v,
                new_ver=new_v,
                doc=doc,
                reviewed_by=reviewed_by,
                loaded_change_count=len(changes),
            ),
            changes=[],
            message="AI đang phân tích sự khác biệt giữa 2 version. Vui lòng chờ.",
        ).model_dump(mode="json")
        return JSONResponse(status_code=202, content=body)

    body = GetDocumentDiffResponse(
        diff_review=_diff_review_out(
            review_row=review_row,
            old_ver=old_v,
            new_ver=new_v,
            doc=doc,
            reviewed_by=reviewed_by,
            loaded_change_count=len(changes),
        ),
        changes=changes,
    ).model_dump(mode="json")
    return JSONResponse(status_code=200, content=body)


@router.get("/diff-reviews/{diff_review_id}/status", response_model=DiffReviewStatusResponse)
async def get_diff_review_status(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    diff_review_id: uuid.UUID,
) -> DiffReviewStatusResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:diff:status:{user.id}", 60)

    review_row = (await session.execute(select(_diff_reviews).where(_diff_reviews.c.id == diff_review_id))).first()
    if review_row is None:
        raise ApiError(404, "NOT_FOUND", "Diff review không tồn tại")

    doc = await _document_for_diff_review_row(session, review_row)
    if doc is None:
        raise ApiError(404, "NOT_FOUND", "Document không tồn tại")
    await require_project_access(session, user, doc.project_id)
    role = await project_member_role(session, user.id, doc.project_id)
    if not _can_review(role, user):
        raise ApiError(403, "FORBIDDEN", "Không có quyền")

    change_n = (
        await session.execute(
            select(func.count()).select_from(_diff_changes).where(_diff_changes.c.diff_review_id == diff_review_id)
        )
    ).scalar_one()
    change_n_i = int(change_n or 0)
    status_val = _status_for_polling_endpoint(review_row, change_n_i)
    percentage = 0 if status_val == "processing" else 100
    prog = DiffReviewStatusProgress(percentage=percentage)
    return DiffReviewStatusResponse(
        diff_review_id=diff_review_id,
        status=status_val,
        progress=prog,
        total_changes=int(review_row.total_changes or 0),
        updated_at=review_row.reviewed_at or review_row.created_at,
    )


@router.patch("/diff-changes/{change_id}", response_model=PatchDiffChangeResponse)
async def patch_diff_change(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    change_id: uuid.UUID,
    body: PatchDiffChangeBody,
) -> PatchDiffChangeResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:diff:change:patch:{user.id}", 60)

    st = (body.approval_status or "").lower().strip()
    if st not in {"approved", "rejected", "pending"}:
        raise ApiError(400, "VALIDATION_ERROR", "approval_status không hợp lệ")

    chg = (await session.execute(select(_diff_changes).where(_diff_changes.c.id == change_id).limit(1))).first()
    if chg is None:
        raise ApiError(404, "NOT_FOUND", "Change không tồn tại")

    rev = (await session.execute(select(_diff_reviews).where(_diff_reviews.c.id == chg.diff_review_id).limit(1))).first()
    if rev is None:
        raise ApiError(404, "NOT_FOUND", "Diff review không tồn tại")
    if (rev.status if isinstance(rev.status, str) else str(rev.status)) == "approved":
        raise ApiError(409, "CONFLICT", "Diff đã được submit — không thể thay đổi")

    doc = await _document_for_diff_review_row(session, rev)
    if doc is None:
        raise ApiError(404, "NOT_FOUND", "Document không tồn tại")
    await require_project_access(session, user, doc.project_id)
    role = await project_member_role(session, user.id, doc.project_id)
    if not _can_review(role, user):
        raise ApiError(403, "FORBIDDEN", "Không có quyền")

    now = datetime.now(UTC)
    approved_by = user.id if st in {"approved", "rejected"} else None
    approved_at = now if st in {"approved", "rejected"} else None
    note = body.approve_note if st == "rejected" else None

    await session.execute(
        update(_diff_changes)
        .where(_diff_changes.c.id == change_id)
        .values(
            approval_status=st,
            approve_note=note,
            approved_by=approved_by,
            approved_at=approved_at,
        )
    )
    summary = await _recount_and_update_review_counters(session, chg.diff_review_id)
    await session.commit()

    return PatchDiffChangeResponse(
        id=change_id,
        approval_status=st,
        approved_by=(UserBrief(id=user.id, full_name=user.full_name) if approved_by else None),
        approved_at=approved_at,
        approve_note=note,
        diff_review_summary={
            "approved_count": summary["approved_count"],
            "rejected_count": summary["rejected_count"],
            "pending_count": summary["pending_count"],
        },
    )


async def _submit_review(
    *,
    session: AsyncSession,
    user: User,
    diff_review_id: uuid.UUID,
    review_note: str | None,
    allow_owner_only: bool = False,
) -> SubmitDiffReviewResponse:
    rev = (await session.execute(select(_diff_reviews).where(_diff_reviews.c.id == diff_review_id))).first()
    if rev is None:
        raise ApiError(404, "NOT_FOUND", "Diff review không tồn tại")
    if (rev.status if isinstance(rev.status, str) else str(rev.status)) == "approved":
        raise ApiError(409, "CONFLICT", "Diff đã được submit trước đó")

    doc = await _document_for_diff_review_row(session, rev)
    if doc is None:
        raise ApiError(404, "NOT_FOUND", "Document không tồn tại")
    await require_project_access(session, user, doc.project_id)
    role = await project_member_role(session, user.id, doc.project_id)

    if allow_owner_only:
        if not (is_system_admin(user) or is_project_owner(role)):
            raise ApiError(403, "FORBIDDEN", "Chỉ Owner/Admin mới dùng approve-all")
    else:
        if not _can_review(role, user):
            raise ApiError(403, "FORBIDDEN", "Không có quyền")

    pending = (
        await session.execute(
            select(func.count()).select_from(_diff_changes).where(
                (_diff_changes.c.diff_review_id == diff_review_id) & (_diff_changes.c.approval_status == "pending")
            )
        )
    ).scalar_one()
    pending_i = int(pending or 0)
    if pending_i > 0:
        raise ApiError(400, "VALIDATION_ERROR", f"Còn {pending_i} thay đổi chưa được review")

    approved = (
        await session.execute(
            select(func.count()).select_from(_diff_changes).where(
                (_diff_changes.c.diff_review_id == diff_review_id) & (_diff_changes.c.approval_status == "approved")
            )
        )
    ).scalar_one()
    rejected = (
        await session.execute(
            select(func.count()).select_from(_diff_changes).where(
                (_diff_changes.c.diff_review_id == diff_review_id) & (_diff_changes.c.approval_status == "rejected")
            )
        )
    ).scalar_one()
    approved_i = int(approved or 0)
    rejected_i = int(rejected or 0)

    new_version_status = "approved" if approved_i > 0 else "rejected"
    now = datetime.now(UTC)
    await session.execute(
        update(_diff_reviews)
        .where(_diff_reviews.c.id == diff_review_id)
        .values(
            status="approved",
            reviewed_by=user.id,
            reviewed_at=now,
            review_note=review_note,
        )
    )
    await session.execute(
        update(DocVersion)
        .where(DocVersion.id == rev.new_version_id)
        .values(status=new_version_status, updated_at=now)
    )
    await session.commit()

    return SubmitDiffReviewResponse(
        diff_review_id=diff_review_id,
        status="processing",
        summary={
            "approved_changes": approved_i,
            "rejected_changes": rejected_i,
            "chunks_to_reembed": approved_i,
            "testcases_flagged": 0,
        },
        new_version_status=new_version_status,
        reembed_job_id=None,
        message=f"Đã submit diff review. Đang re-embedding {approved_i} chunk đã approve.",
    )


@router.post("/diff-reviews/{diff_review_id}/submit", response_model=SubmitDiffReviewResponse)
async def submit_diff_review(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    diff_review_id: uuid.UUID,
    body: SubmitDiffReviewBody,
) -> SubmitDiffReviewResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:diff:submit:{user.id}", 5)
    return await _submit_review(session=session, user=user, diff_review_id=diff_review_id, review_note=body.review_note)


@router.post("/diff-reviews/{diff_review_id}/approve-all", response_model=SubmitDiffReviewResponse)
async def approve_all_and_submit(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    diff_review_id: uuid.UUID,
    body: SubmitDiffReviewBody,
) -> SubmitDiffReviewResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:diff:approve_all:{user.id}", 5)

    rev = (await session.execute(select(_diff_reviews).where(_diff_reviews.c.id == diff_review_id))).first()
    if rev is None:
        raise ApiError(404, "NOT_FOUND", "Diff review không tồn tại")
    if (rev.status if isinstance(rev.status, str) else str(rev.status)) == "approved":
        raise ApiError(409, "CONFLICT", "Diff đã được submit")

    doc = await _document_for_diff_review_row(session, rev)
    if doc is None:
        raise ApiError(404, "NOT_FOUND", "Document không tồn tại")
    await require_project_access(session, user, doc.project_id)
    role = await project_member_role(session, user.id, doc.project_id)
    if not (is_system_admin(user) or is_project_owner(role)):
        raise ApiError(403, "FORBIDDEN", "Chỉ Owner/Admin mới dùng approve-all")

    now = datetime.now(UTC)
    await session.execute(
        update(_diff_changes)
        .where(_diff_changes.c.diff_review_id == diff_review_id)
        .values(approval_status="approved", approved_by=user.id, approved_at=now, approve_note=None)
    )
    await _recount_and_update_review_counters(session, diff_review_id)
    await session.commit()

    return await _submit_review(
        session=session,
        user=user,
        diff_review_id=diff_review_id,
        review_note=body.review_note,
        allow_owner_only=True,
    )


@router.get("/documents/{document_id}/diff-history", response_model=GetDiffHistoryResponse)
async def get_document_diff_history(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    document_id: uuid.UUID,
) -> GetDiffHistoryResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:diff:history:{user.id}", 60)

    doc = await session.get(Document, document_id)
    if doc is None:
        raise ApiError(404, "NOT_FOUND", "Document không tồn tại")
    await require_project_access(session, user, doc.project_id)

    rows = (
        await session.execute(
            select(_diff_reviews)
            .select_from(
                _diff_reviews.join(_doc_versions_for_join, _doc_versions_for_join.c.id == _diff_reviews.c.new_version_id)
            )
            .where((_doc_versions_for_join.c.document_id == document_id) & (_diff_reviews.c.status == "approved"))
            .order_by(_diff_reviews.c.reviewed_at.desc().nulls_last(), _diff_reviews.c.id.desc())
        )
    ).all()

    items: list[DiffHistoryReviewItem] = []
    for rev in rows:
        old_v = await session.get(DocVersion, rev.old_version_id)
        new_v = await session.get(DocVersion, rev.new_version_id)
        approved_by = await session.get(User, rev.reviewed_by) if rev.reviewed_by else None

        change_rows = (
            await session.execute(
                select(_diff_changes)
                .where(_diff_changes.c.diff_review_id == rev.id)
                .order_by(_diff_changes.c.created_at.asc().nulls_first(), _diff_changes.c.id.asc())
            )
        ).all()
        changes: list[DiffHistoryChangeItem] = []
        for idx, c in enumerate(change_rows, start=1):
            section = None
            if c.chunk_new_id:
                ch = await session.get(Chunk, c.chunk_new_id)
                if ch and isinstance(ch.metadata_, dict):
                    section = ch.metadata_.get("section")
            if section is None and c.chunk_old_id:
                ch = await session.get(Chunk, c.chunk_old_id)
                if ch and isinstance(ch.metadata_, dict):
                    section = ch.metadata_.get("section")
            changes.append(
                DiffHistoryChangeItem(
                    id=c.id,
                    change_index=idx,
                    change_type=c.change_type,
                    section=section,
                    ai_change_summary=None,
                    chunk_old_id=c.chunk_old_id,
                    chunk_new_id=c.chunk_new_id,
                )
            )

        if old_v is None or new_v is None:
            continue
        items.append(
            DiffHistoryReviewItem(
                diff_review_id=rev.id,
                from_version=DiffHistoryVersionItem(id=old_v.id, version_no=old_v.version_no),
                to_version=DiffHistoryVersionItem(id=new_v.id, version_no=new_v.version_no),
                approved_at=rev.reviewed_at,
                approved_by=(UserBrief(id=approved_by.id, full_name=approved_by.full_name) if approved_by else None),
                review_note=rev.review_note,
                total_changes=int(rev.total_changes or len(changes)),
                changes=changes,
            )
        )

    dt = doc.doc_type if isinstance(doc.doc_type, str) else str(doc.doc_type)
    return GetDiffHistoryResponse(
        document_id=doc.id,
        screen_name=doc.screen_name,
        doc_type=dt,
        diff_history=items,
        total_diff_reviews=len(items),
    )

