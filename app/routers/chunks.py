from __future__ import annotations

import json
import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from redis.exceptions import RedisError
from sqlalchemy import column, func, select, table, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.database import get_session
from app.deps import get_current_user
from app.exceptions import ApiError
from app.models.user import User
from app.project_access import is_system_admin, project_member_role, require_project_access
from app.redis_client import get_redis
from app.schemas.viewer import (
    ChunkTestcaseItem,
    ChunkTestcasesResponse,
    CreateTestcaseLinkBody,
    DeleteTestcaseLinkResponse,
    TestcaseLinkResponse,
    ViewerUserBrief,
)

router = APIRouter()

_chunks = table(
    "chunks",
    column("id"),
    column("doc_version_id"),
    column("chunk_index"),
    column("content_text"),
    column("metadata"),
    column("created_at"),
)
_doc_versions = table("doc_versions", column("id"), column("document_id"))
_documents = table("documents", column("id"), column("project_id"))

_links = table(
    "testcase_chunk_links",
    column("id"),
    column("testcase_id"),
    column("chunk_id"),
    column("link_type"),
    column("relevance_score"),
    column("is_primary"),
    column("created_at"),
)
_testcases = table(
    "testcases",
    column("id"),
    column("project_id"),
    column("title"),
    column("tc_type"),
    column("steps"),
    column("priority"),
    column("status"),
    column("updated_at"),
    column("created_by"),
)
_users = table("users", column("id"), column("full_name"))


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


async def _chunk_project_id_or_404(session: AsyncSession, chunk_id: uuid.UUID) -> uuid.UUID:
    r = await session.execute(
        select(_documents.c.project_id)
        .select_from(
            _chunks.join(_doc_versions, _doc_versions.c.id == _chunks.c.doc_version_id).join(
                _documents, _documents.c.id == _doc_versions.c.document_id
            )
        )
        .where(_chunks.c.id == chunk_id)
    )
    pid = r.scalar_one_or_none()
    if pid is None:
        raise ApiError(404, "NOT_FOUND", "Chunk không tồn tại")
    return pid


def _can_link_unlink(user: User, role: str | None) -> bool:
    if is_system_admin(user):
        return True
    return (role or "").lower() in {"owner", "pm", "qc"}


@router.get("/chunks/{chunk_id}/testcases", response_model=ChunkTestcasesResponse)
async def get_chunk_testcases(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    chunk_id: Annotated[uuid.UUID, Path(...)],
) -> ChunkTestcasesResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:chunk:tcs:{user.id}", 120)

    project_id = await _chunk_project_id_or_404(session, chunk_id)
    await require_project_access(session, user, project_id)

    cache_key = f"chunk_tcs:{chunk_id}"
    try:
        cached = await redis.get(cache_key)
    except RedisError:
        cached = None

    if cached:
        try:
            payload = json.loads(cached)
            return ChunkTestcasesResponse.model_validate(payload)
        except Exception:
            # fall through to DB
            pass

    # chunk preview + section
    cr = await session.execute(
        select(_chunks.c.content_text, _chunks.c.metadata)
        .where(_chunks.c.id == chunk_id)
        .limit(1)
    )
    row = cr.first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Chunk không tồn tại")
    content_text: str = row[0] or ""
    meta = row[1] if isinstance(row[1], dict) else None
    section = (meta or {}).get("section")
    preview = " ".join(content_text.replace("\n", " ").split())[:80]

    qr = await session.execute(
        select(
            _testcases.c.id,
            _testcases.c.title,
            _testcases.c.tc_type,
            _testcases.c.priority,
            _testcases.c.status,
            func.coalesce(func.jsonb_array_length(_testcases.c.steps), 0).label("steps_count"),
            _links.c.link_type,
            _links.c.relevance_score,
            _links.c.is_primary,
            _users.c.full_name.label("created_by_name"),
            _testcases.c.updated_at,
        )
        .select_from(
            _links.join(_testcases, _testcases.c.id == _links.c.testcase_id).outerjoin(
                _users, _users.c.id == _testcases.c.created_by
            )
        )
        .where(_links.c.chunk_id == chunk_id)
        .order_by(_links.c.is_primary.desc(), _links.c.relevance_score.desc(), _testcases.c.updated_at.desc().nullslast())
    )
    items: list[ChunkTestcaseItem] = []
    for r in qr.all():
        items.append(
            ChunkTestcaseItem(
                id=r.id,
                title=r.title,
                tc_type=str(r.tc_type),
                priority=str(r.priority),
                status=str(r.status),
                steps_count=int(r.steps_count or 0),
                link_type=str(r.link_type),
                relevance_score=float(r.relevance_score or 0.0),
                is_primary_link=bool(r.is_primary),
                created_by=ViewerUserBrief(full_name=r.created_by_name) if r.created_by_name else None,
                updated_at=r.updated_at,
            )
        )

    out = ChunkTestcasesResponse(
        chunk_id=chunk_id,
        chunk_preview=preview,
        chunk_section=section,
        testcases=items,
        total=len(items),
    )

    try:
        await redis.set(cache_key, out.model_dump_json(), ex=60)
    except RedisError:
        pass

    return out


@router.post(
    "/chunks/{chunk_id}/testcase-links",
    status_code=status.HTTP_201_CREATED,
    response_model=TestcaseLinkResponse,
)
async def create_chunk_testcase_link(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    chunk_id: Annotated[uuid.UUID, Path(...)],
    body: CreateTestcaseLinkBody,
) -> TestcaseLinkResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:chunk:link:{user.id}", 60)

    project_id = await _chunk_project_id_or_404(session, chunk_id)
    await require_project_access(session, user, project_id)
    role = await project_member_role(session, user.id, project_id)
    if not _can_link_unlink(user, role):
        raise ApiError(403, "FORBIDDEN", "Không có quyền")

    # Check testcase exists and belongs to same project
    tr = await session.execute(
        select(_testcases.c.project_id).where(_testcases.c.id == body.testcase_id).limit(1)
    )
    tc_project_id = tr.scalar_one_or_none()
    if tc_project_id is None:
        raise ApiError(404, "NOT_FOUND", "Testcase không tồn tại")
    if uuid.UUID(str(tc_project_id)) != uuid.UUID(str(project_id)):
        raise ApiError(422, "CROSS_PROJECT_LINK", "TC và chunk thuộc project khác nhau")

    link_id = uuid.uuid4()
    try:
        await session.execute(
            text(
                """
                INSERT INTO testcase_chunk_links (id, testcase_id, chunk_id, link_type, relevance_score, is_primary, created_at)
                VALUES (:id, :tc_id, :chunk_id, :link_type::doc_type_enum, :score, :is_primary, NOW())
                """
            ),
            {
                "id": str(link_id),
                "tc_id": str(body.testcase_id),
                "chunk_id": str(chunk_id),
                "link_type": body.link_type,
                "score": float(body.relevance_score),
                "is_primary": bool(body.is_primary),
            },
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(409, "LINK_EXISTS", "Link đã tồn tại") from exc

    # bust cache
    try:
        await redis.delete(f"chunk_tcs:{chunk_id}")
    except RedisError:
        pass

    return TestcaseLinkResponse(
        id=link_id,
        chunk_id=chunk_id,
        testcase_id=body.testcase_id,
        link_type=body.link_type,
        is_primary=bool(body.is_primary),
        relevance_score=float(body.relevance_score),
        created_at=None,
    )


@router.delete("/chunks/{chunk_id}/testcase-links/{testcase_id}", response_model=DeleteTestcaseLinkResponse)
async def delete_chunk_testcase_link(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    chunk_id: Annotated[uuid.UUID, Path(...)],
    testcase_id: Annotated[uuid.UUID, Path(...)],
) -> DeleteTestcaseLinkResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:chunk:unlink:{user.id}", 60)

    project_id = await _chunk_project_id_or_404(session, chunk_id)
    await require_project_access(session, user, project_id)
    role = await project_member_role(session, user.id, project_id)
    if not _can_link_unlink(user, role):
        raise ApiError(403, "FORBIDDEN", "Không có quyền")

    res = await session.execute(
        text("DELETE FROM testcase_chunk_links WHERE chunk_id = :chunk_id AND testcase_id = :tc_id"),
        {"chunk_id": str(chunk_id), "tc_id": str(testcase_id)},
    )
    await session.commit()
    if res.rowcount == 0:
        raise ApiError(404, "NOT_FOUND", "Link không tồn tại")

    try:
        await redis.delete(f"chunk_tcs:{chunk_id}")
    except RedisError:
        pass

    return DeleteTestcaseLinkResponse(
        message="Đã xoá liên kết giữa testcase và đoạn nội dung",
        chunk_id=chunk_id,
        testcase_id=testcase_id,
    )

