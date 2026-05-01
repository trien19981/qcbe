"""Shared project access checks for routers."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ApiError
from app.models.project import Project, ProjectMember
from app.models.user import User


def user_role_str(user: User) -> str:
    r = user.role
    return r if isinstance(r, str) else str(r)


def is_system_admin(user: User) -> bool:
    return user_role_str(user).lower() == "admin"


async def require_project_access(session: AsyncSession, user: User, project_id: uuid.UUID) -> Project:
    p = await session.get(Project, project_id)
    if p is None:
        raise ApiError(404, "NOT_FOUND", "Project không tồn tại")
    if is_system_admin(user):
        return p
    r = await session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id,
        )
    )
    if r.scalar_one_or_none() is None:
        raise ApiError(403, "FORBIDDEN", "Không có quyền truy cập project")
    return p


async def project_member_role(session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID) -> str | None:
    r = await session.execute(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    row = r.one_or_none()
    if row is None:
        return None
    val = row[0]
    return val if isinstance(val, str) else str(val)


def can_manage_project_members(user: User, project_role: str | None) -> bool:
    """Owner của project hoặc system admin."""
    if is_system_admin(user):
        return True
    return (project_role or "").lower() == "owner"


def can_see_pending_invitations(user: User, project_role: str | None) -> bool:
    if is_system_admin(user):
        return True
    return (project_role or "").lower() == "owner"


def is_project_owner(project_role: str | None) -> bool:
    return (project_role or "").lower() == "owner"


def can_patch_or_delete_document(user: User, project_role: str | None) -> bool:
    """PATCH/DELETE document: system admin hoặc project owner (S3_DOCUMENT_LIST_DESIGN)."""
    if is_system_admin(user):
        return True
    return (project_role or "").lower() == "owner"
