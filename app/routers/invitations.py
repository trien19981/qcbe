"""Public invitation accept (MEMBER_MANAGEMENT_DESIGN.md)."""

import time
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.deps import get_client_ip
from app.exceptions import ApiError
from app.models.pending_invitation import PendingInvitation
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.members import AcceptInvitationBody, AcceptInvitationProject, AcceptInvitationResponse

router = APIRouter()


async def _rate_limit_minute(redis, key: str, limit: int) -> None:
    bucket = int(time.time() // 60)
    rkey = f"{key}:{bucket}"
    n = await redis.incr(rkey)
    if n == 1:
        await redis.expire(rkey, 120)
    if n > limit:
        raise ApiError(429, "TOO_MANY_REQUESTS", "Quá nhiều yêu cầu. Vui lòng thử lại sau.")


def _norm_email(s: str) -> str:
    return s.strip().lower()


@router.post("/invitations/{token}/accept", response_model=AcceptInvitationResponse)
async def accept_invitation(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    token: uuid.UUID,
    body: AcceptInvitationBody,
) -> AcceptInvitationResponse:
    redis = get_redis()
    ip = get_client_ip(request)
    await _rate_limit_minute(redis, f"rl:invacc:{ip}", 10)

    inv = (
        await session.execute(select(PendingInvitation).where(PendingInvitation.token == token))
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if inv is None or inv.expires_at < now:
        raise ApiError(400, "BAD_REQUEST", "Token không hợp lệ hoặc đã hết hạn")

    usr = await session.get(User, body.user_id)
    if usr is None:
        raise ApiError(422, "VALIDATION_ERROR", "user_id không hợp lệ")
    if _norm_email(usr.email) != _norm_email(inv.email):
        raise ApiError(422, "VALIDATION_ERROR", "Tài khoản không khớp với lời mời")

    ex = await session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == inv.project_id,
            ProjectMember.user_id == usr.id,
        )
    )
    if ex.scalar_one_or_none() is not None:
        raise ApiError(409, "CONFLICT", "Bạn đã là thành viên của project này")

    project = await session.get(Project, inv.project_id)
    if project is None:
        raise ApiError(400, "BAD_REQUEST", "Token không hợp lệ hoặc đã hết hạn")

    session.add(ProjectMember(project_id=inv.project_id, user_id=usr.id, role=inv.role))
    await session.delete(inv)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ApiError(409, "CONFLICT", "Bạn đã là thành viên của project này") from e

    return AcceptInvitationResponse(
        message="Đã tham gia project thành công",
        project=AcceptInvitationProject(id=project.id, name=project.name, slug=project.slug),
        role=inv.role,
    )
