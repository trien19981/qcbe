"""S3 document list — GET theo project (S3_DOCUMENT_LIST_DESIGN.md)."""

import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.deps import get_current_user
from app.exceptions import ApiError
from app.models.document import DocVersion, Document
from app.models.user import User
from app.project_access import require_project_access
from app.redis_client import get_redis
from app.schemas.documents import (
    DocumentListItem,
    DocumentListResponse,
    DocUserBrief,
    LatestVersionOut,
    ScreenCountItem,
    ScreensResponse,
)
from app.schemas.project import PaginationMeta

router = APIRouter()

DOC_TYPES = frozenset({"basic_design", "api_design", "detail_design", "testcase_manual", "figma"})
VERSION_STATUSES = frozenset(
    {"draft", "processing", "ready_for_review", "approved", "rejected"},
)


async def _rate_limit_minute(redis, key: str, limit: int) -> None:
    bucket = int(time.time() // 60)
    rkey = f"{key}:{bucket}"
    n = await redis.incr(rkey)
    if n == 1:
        await redis.expire(rkey, 120)
    if n > limit:
        raise ApiError(429, "TOO_MANY_REQUESTS", "Quá nhiều yêu cầu. Vui lòng thử lại sau.")


def _latest_version_id_sq():
    return (
        select(DocVersion.id)
        .where(DocVersion.document_id == Document.id)
        .order_by(DocVersion.version_no.desc())
        .limit(1)
        .correlate(Document)
        .scalar_subquery()
    )


async def _load_users(session: AsyncSession, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not user_ids:
        return {}
    res = await session.execute(select(User).where(User.id.in_(user_ids)))
    return {u.id: u for u in res.scalars().all()}


def _user_brief(u: User | None) -> DocUserBrief | None:
    if u is None:
        return None
    return DocUserBrief(id=u.id, full_name=u.full_name, avatar_url=u.avatar_url)


@router.get("/{project_id}/documents", response_model=DocumentListResponse)
async def list_project_documents(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
    doc_type: str | None = Query(None),
    screen: str | None = Query(None),
    search: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
) -> DocumentListResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:doc:list:{user.id}", 60)

    await require_project_access(session, user, project_id)

    if doc_type is not None and doc_type.strip() and doc_type.strip() not in DOC_TYPES:
        raise ApiError(422, "VALIDATION_ERROR", "Tham số doc_type không hợp lệ")
    if status is not None and status.strip() and status.strip() not in VERSION_STATUSES:
        raise ApiError(422, "VALIDATION_ERROR", "Tham số status không hợp lệ")

    lv_id = _latest_version_id_sq()
    base = (
        select(Document, DocVersion)
        .join(DocVersion, DocVersion.id == lv_id)
        .where(Document.project_id == project_id)
    )
    if doc_type and doc_type.strip():
        base = base.where(Document.doc_type == doc_type.strip())
    if screen and screen.strip():
        pat = f"%{screen.strip()}%"
        base = base.where(Document.screen_name.ilike(pat))
    if search and search.strip():
        pat = f"%{search.strip()}%"
        base = base.where(Document.screen_name.ilike(pat))
    if status and status.strip():
        base = base.where(DocVersion.status == status.strip())

    count_stmt = select(func.count()).select_from(base.subquery())
    total = int((await session.execute(count_stmt)).scalar_one())

    stmt = base.order_by(Document.updated_at.desc().nulls_last(), Document.created_at.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    rows = (await session.execute(stmt)).all()

    doc_ids = [d.id for d, _ in rows]
    vc_map: dict[uuid.UUID, int] = {}
    if doc_ids:
        vc_rows = (
            await session.execute(
                select(DocVersion.document_id, func.count())
                .where(DocVersion.document_id.in_(doc_ids))
                .group_by(DocVersion.document_id)
            )
        ).all()
        vc_map = {r[0]: int(r[1]) for r in vc_rows}

    uids: set[uuid.UUID] = set()
    for d, lv in rows:
        if d.created_by:
            uids.add(d.created_by)
        if lv.created_by:
            uids.add(lv.created_by)
    umap = await _load_users(session, uids)

    data: list[DocumentListItem] = []
    for d, lv in rows:
        vc = vc_map.get(d.id, 0)
        dt = d.doc_type if isinstance(d.doc_type, str) else str(d.doc_type)
        st = lv.status if isinstance(lv.status, str) else str(lv.status)
        creator_lv = umap.get(lv.created_by) if lv.created_by else None
        data.append(
            DocumentListItem(
                id=d.id,
                project_id=d.project_id,
                screen_name=d.screen_name,
                doc_type=dt,
                description=d.description,
                version_count=vc,
                latest_version=LatestVersionOut(
                    id=lv.id,
                    version_no=lv.version_no,
                    status=st,
                    changelog_md=lv.changelog_md,
                    created_at=lv.created_at,
                    created_by=_user_brief(creator_lv),
                    approved_at=lv.approved_at,
                ),
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
        )

    hp = (
        await session.execute(
            text(
                """
                SELECT EXISTS (
                  SELECT 1 FROM documents d
                  JOIN LATERAL (
                    SELECT status FROM doc_versions dv
                    WHERE dv.document_id = d.id
                    ORDER BY dv.version_no DESC LIMIT 1
                  ) lv ON true
                  WHERE d.project_id = CAST(:pid AS uuid) AND lv.status::text = 'processing'
                )
                """
            ),
            {"pid": str(project_id)},
        )
    ).scalar_one()
    has_processing = bool(hp)

    total_pages = (total + per_page - 1) // per_page if total else 0
    return DocumentListResponse(
        data=data,
        pagination=PaginationMeta(total=total, page=page, per_page=per_page, total_pages=total_pages),
        has_processing=has_processing,
    )


@router.get("/{project_id}/documents/screens", response_model=ScreensResponse)
async def list_project_document_screens(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
) -> ScreensResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:doc:screens:{user.id}", 60)

    await require_project_access(session, user, project_id)

    stmt = (
        select(Document.screen_name, func.count().label("doc_count"))
        .where(Document.project_id == project_id)
        .group_by(Document.screen_name)
        .order_by(Document.screen_name.asc())
    )
    rows = (await session.execute(stmt)).all()
    screens = [ScreenCountItem(screen_name=r[0], doc_count=int(r[1])) for r in rows]
    return ScreensResponse(screens=screens, total=len(screens))
