import time
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import and_, column, exists, false, func, or_, select, table, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.deps import get_current_user
from app.exceptions import ApiError
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.project_access import is_system_admin, require_project_access
from app.redis_client import get_redis
from app.schemas.project import (
    ArchiveBody,
    ArchiveResponse,
    ProjectCreateBody,
    ProjectDetail,
    ProjectListItem,
    ProjectListResponse,
    ProjectMemberOut,
    ProjectPatchBody,
    ProjectStats,
    ProjectStatsWithMembers,
    PaginationMeta,
    SLUG_PATTERN,
    UserBrief,
)

router = APIRouter()

_documents = table("documents", column("project_id"), column("id"))
_testcases = table("testcases", column("project_id"), column("id"))


async def _rate_limit(redis, key: str, limit: int) -> None:
    bucket = int(time.time() // 60)
    rkey = f"{key}:{bucket}"
    n = await redis.incr(rkey)
    if n == 1:
        await redis.expire(rkey, 120)
    if n > limit:
        raise ApiError(429, "TOO_MANY_REQUESTS", "Quá nhiều yêu cầu. Vui lòng thử lại sau.")


async def _counts_for_projects(
    session: AsyncSession,
    project_ids: list[uuid.UUID],
) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    if not project_ids:
        return {}, {}
    doc_stmt = (
        select(_documents.c.project_id, func.count(_documents.c.id))
        .where(_documents.c.project_id.in_(project_ids))
        .group_by(_documents.c.project_id)
    )
    tc_stmt = (
        select(_testcases.c.project_id, func.count(_testcases.c.id))
        .where(_testcases.c.project_id.in_(project_ids))
        .group_by(_testcases.c.project_id)
    )
    doc_rows = (await session.execute(doc_stmt)).all()
    tc_rows = (await session.execute(tc_stmt)).all()
    return {r[0]: int(r[1]) for r in doc_rows}, {r[0]: int(r[1]) for r in tc_rows}


async def _load_users(session: AsyncSession, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not user_ids:
        return {}
    res = await session.execute(select(User).where(User.id.in_(user_ids)))
    return {u.id: u for u in res.scalars().all()}


async def _my_roles(
    session: AsyncSession,
    project_ids: list[uuid.UUID],
    user_id: uuid.UUID,
) -> dict[uuid.UUID, str]:
    if not project_ids:
        return {}
    res = await session.execute(
        select(ProjectMember.project_id, ProjectMember.role).where(
            ProjectMember.project_id.in_(project_ids),
            ProjectMember.user_id == user_id,
        )
    )
    return {row[0]: (row[1] if isinstance(row[1], str) else str(row[1])) for row in res.all()}


def _list_conds(user: User, status: str, search: str | None) -> list:
    conds: list = []
    admin = is_system_admin(user)
    if not admin:
        conds.append(
            exists().where(
                ProjectMember.project_id == Project.id,
                ProjectMember.user_id == user.id,
            )
        )

    st = status.lower().strip()
    if st == "active":
        conds.append(Project.status == "active")
    elif st == "archived":
        if not admin:
            conds.append(false())
        else:
            conds.append(Project.status == "archived")
    elif st == "all":
        if not admin:
            conds.append(Project.status == "active")
    else:
        raise ApiError(422, "VALIDATION_ERROR", "Tham số status phải là active, archived hoặc all")

    if search and search.strip():
        kw = f"%{search.strip()}%"
        conds.append(or_(Project.name.ilike(kw), Project.description.ilike(kw)))
    return conds


def _brief(u: User | None) -> UserBrief | None:
    if u is None:
        return None
    return UserBrief(id=u.id, full_name=u.full_name)


def _dt(dt: datetime | None) -> datetime:
    return dt if dt is not None else datetime.now(UTC)


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    status: str = Query("active"),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
) -> ProjectListResponse:
    redis = get_redis()
    await _rate_limit(redis, f"rl:proj:list:{user.id}", 60)

    conds = _list_conds(user, status, search)
    if conds:
        base = select(Project).where(and_(*conds))
        count_stmt = select(func.count()).select_from(Project).where(and_(*conds))
    else:
        base = select(Project)
        count_stmt = select(func.count()).select_from(Project)

    total = int((await session.execute(count_stmt)).scalar_one())

    stmt = base.order_by(Project.updated_at.desc().nulls_last(), Project.created_at.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    rows = (await session.execute(stmt)).scalars().all()

    ids = [p.id for p in rows]
    doc_map, tc_map = await _counts_for_projects(session, ids)
    roles_map = await _my_roles(session, ids, user.id)
    creators = {p.created_by for p in rows if p.created_by}
    user_map = await _load_users(session, creators)

    admin = is_system_admin(user)
    data: list[ProjectListItem] = []
    for p in rows:
        mr = roles_map.get(p.id)
        if mr is None and admin:
            mr = "admin"
        elif mr is None:
            mr = "viewer"
        creator = user_map.get(p.created_by) if p.created_by else None
        data.append(
            ProjectListItem(
                id=p.id,
                name=p.name,
                slug=p.slug,
                description=p.description,
                status=p.status or "active",
                stats=ProjectStats(
                    document_count=doc_map.get(p.id, 0),
                    testcase_count=tc_map.get(p.id, 0),
                ),
                my_role=mr,
                created_at=_dt(p.created_at),
                updated_at=p.updated_at,
                created_by=_brief(creator),
            )
        )

    total_pages = (total + per_page - 1) // per_page if total else 0
    return ProjectListResponse(
        data=data,
        pagination=PaginationMeta(total=total, page=page, per_page=per_page, total_pages=total_pages),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    body: ProjectCreateBody,
) -> ProjectDetail:
    if not is_system_admin(user):
        raise ApiError(403, "FORBIDDEN", "Không có quyền tạo project")

    redis = get_redis()
    await _rate_limit(redis, f"rl:proj:create:{user.id}", 10)

    name = body.name.strip()
    if len(name) < 3 or len(name) > 100:
        raise ApiError(422, "VALIDATION_ERROR", "Tên project phải từ 3 đến 100 ký tự")

    slug = body.slug.strip().lower()
    if not SLUG_PATTERN.fullmatch(slug):
        raise ApiError(422, "VALIDATION_ERROR", "Slug chỉ được chứa chữ thường, số và dấu gạch ngang")

    project = Project(
        name=name,
        slug=slug,
        description=body.description.strip() if body.description else None,
        status="active",
        created_by=user.id,
    )
    session.add(project)
    await session.flush()
    member = ProjectMember(project_id=project.id, user_id=user.id, role="owner")
    session.add(member)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        err = str(e.orig).lower() if getattr(e, "orig", None) else str(e).lower()
        if "slug" in err or "unique" in err:
            raise ApiError(
                409,
                "CONFLICT",
                f"Slug '{slug}' đã được sử dụng. Vui lòng chọn slug khác.",
                extra={"field": "slug"},
            ) from e
        raise
    await session.refresh(project)

    return await _build_project_detail(session, user, project.id)


async def _build_project_detail(
    session: AsyncSession,
    user: User,
    project_id: uuid.UUID,
) -> ProjectDetail:
    """Chi tiết project (members + stats)."""
    p = await require_project_access(session, user, project_id)

    doc_map, tc_map = await _counts_for_projects(session, [p.id])
    roles_map = await _my_roles(session, [p.id], user.id)
    mr = roles_map.get(p.id)
    if mr is None and is_system_admin(user):
        mr = "admin"
    elif mr is None:
        mr = "viewer"

    mem_rows = await session.execute(
        select(ProjectMember, User)
        .select_from(ProjectMember)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == p.id)
        .order_by(ProjectMember.joined_at.asc())
    )
    members: list[ProjectMemberOut] = []
    for pm, u in mem_rows.all():
        r = pm.role
        members.append(
            ProjectMemberOut(
                user_id=u.id,
                full_name=u.full_name,
                email=u.email,
                role=r if isinstance(r, str) else str(r),
                avatar_url=u.avatar_url,
                joined_at=pm.joined_at,
            )
        )

    creator = await session.get(User, p.created_by) if p.created_by else None
    return ProjectDetail(
        id=p.id,
        name=p.name,
        slug=p.slug,
        description=p.description,
        status=p.status or "active",
        stats=ProjectStatsWithMembers(
            document_count=doc_map.get(p.id, 0),
            testcase_count=tc_map.get(p.id, 0),
            member_count=len(members),
        ),
        my_role=mr,
        members=members,
        created_at=_dt(p.created_at),
        updated_at=p.updated_at,
        created_by=_brief(creator),
    )


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
) -> ProjectDetail:
    redis = get_redis()
    await _rate_limit(redis, f"rl:proj:get:{user.id}", 120)
    return await _build_project_detail(session, user, project_id)


@router.patch("/{project_id}", response_model=ProjectDetail)
async def patch_project(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
    body: ProjectPatchBody,
) -> ProjectDetail:
    if not is_system_admin(user):
        raise ApiError(403, "FORBIDDEN", "Không có quyền cập nhật project")

    redis = get_redis()
    await _rate_limit(redis, f"rl:proj:patch:{user.id}", 30)

    p = await session.get(Project, project_id)
    if p is None:
        raise ApiError(404, "NOT_FOUND", "Project không tồn tại")

    if body.name is None and body.description is None:
        raise ApiError(400, "BAD_REQUEST", "Không có field nào để cập nhật")

    vals: dict = {}
    if body.name is not None:
        name = body.name.strip()
        if len(name) < 3 or len(name) > 100:
            raise ApiError(422, "VALIDATION_ERROR", "Tên project phải từ 3 đến 100 ký tự")
        vals["name"] = name
    if body.description is not None:
        vals["description"] = body.description

    if vals:
        vals["updated_at"] = func.now()
        await session.execute(update(Project).where(Project.id == project_id).values(**vals))
        await session.commit()

    return await _build_project_detail(session, user, project_id)


@router.patch("/{project_id}/archive", response_model=ArchiveResponse)
async def archive_project(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
    body: ArchiveBody,
) -> ArchiveResponse:
    if not is_system_admin(user):
        raise ApiError(403, "FORBIDDEN", "Không có quyền archive project")

    redis = get_redis()
    await _rate_limit(redis, f"rl:proj:arch:{user.id}", 10)

    p = await session.get(Project, project_id)
    if p is None:
        raise ApiError(404, "NOT_FOUND", "Project không tồn tại")

    new_st = body.status
    cur = (p.status or "active").lower()
    if cur == new_st:
        raise ApiError(409, "CONFLICT", "Project đã ở trạng thái này")

    await session.execute(
        update(Project).where(Project.id == project_id).values(status=new_st, updated_at=func.now())
    )
    await session.commit()

    msg = "Project đã được archive thành công" if new_st == "archived" else "Project đã được kích hoạt lại"
    return ArchiveResponse(id=project_id, status=new_st, message=msg)
