"""Project members & invitations (MEMBER_MANAGEMENT_DESIGN.md)."""

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Union

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.deps import get_current_user
from app.exceptions import ApiError
from app.models.pending_invitation import PendingInvitation
from app.models.project import ProjectMember
from app.models.user import User
from app.project_access import (
    can_manage_project_members,
    can_see_pending_invitations,
    is_project_owner,
    is_system_admin,
    project_member_role,
    require_project_access,
)
from app.redis_client import get_redis
from app.schemas.members import (
    CancelInvitationResponse,
    DeleteMemberResponse,
    InviteAddedResponse,
    InviteInvitedResponse,
    InviteMemberBody,
    InvitationCreatedOut,
    MemberAddedOut,
    MemberListItem,
    MembersListResponse,
    PatchMemberBody,
    PatchMemberResponse,
    PendingInvitationOut,
    TransferOwnerBody,
    TransferOwnerParty,
    TransferOwnerResponse,
)

router = APIRouter()


async def _rate_limit_minute(redis, key: str, limit: int) -> None:
    bucket = int(time.time() // 60)
    rkey = f"{key}:{bucket}"
    n = await redis.incr(rkey)
    if n == 1:
        await redis.expire(rkey, 120)
    if n > limit:
        raise ApiError(429, "TOO_MANY_REQUESTS", "Quá nhiều yêu cầu. Vui lòng thử lại sau.")


async def _rate_limit_hour(redis, key: str, limit: int) -> None:
    bucket = int(time.time() // 3600)
    rkey = f"{key}:{bucket}"
    n = await redis.incr(rkey)
    if n == 1:
        await redis.expire(rkey, 7200)
    if n > limit:
        raise ApiError(429, "TOO_MANY_REQUESTS", "Quá nhiều yêu cầu. Vui lòng thử lại sau.")


def _norm_email(s: str) -> str:
    return s.strip().lower()


@router.get("/{project_id}/members", response_model=MembersListResponse)
async def list_members(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
) -> MembersListResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:mem:list:{user.id}", 60)

    await require_project_access(session, user, project_id)
    my_role = await project_member_role(session, user.id, project_id)
    show_pending = can_see_pending_invitations(user, my_role)

    mem_rows = await session.execute(
        select(ProjectMember, User)
        .select_from(ProjectMember)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.joined_at.asc())
    )
    members: list[MemberListItem] = []
    for pm, u in mem_rows.all():
        r = pm.role if isinstance(pm.role, str) else str(pm.role)
        members.append(
            MemberListItem(
                user_id=u.id,
                email=u.email,
                full_name=u.full_name,
                avatar_url=u.avatar_url,
                role=r,
                joined_at=pm.joined_at,
                is_current_user=u.id == user.id,
            )
        )

    pending_out: list[PendingInvitationOut] = []
    if show_pending:
        inv_rows = await session.execute(
            select(PendingInvitation).where(PendingInvitation.project_id == project_id)
        )
        invs = inv_rows.scalars().all()
        inviter_ids = {i.invited_by for i in invs if i.invited_by}
        inviter_map: dict[uuid.UUID, User] = {}
        if inviter_ids:
            ur = await session.execute(select(User).where(User.id.in_(inviter_ids)))
            for u in ur.scalars().all():
                inviter_map[u.id] = u
        for inv in invs:
            inv_u = inviter_map.get(inv.invited_by) if inv.invited_by else None
            pending_out.append(
                PendingInvitationOut(
                    id=inv.id,
                    email=inv.email,
                    role=inv.role,
                    invited_by_name=inv_u.full_name if inv_u else None,
                    expires_at=inv.expires_at,
                    created_at=inv.created_at,
                )
            )

    return MembersListResponse(
        members=members,
        pending_invitations=pending_out if show_pending else [],
        total_members=len(members),
        total_pending=len(pending_out) if show_pending else 0,
    )


@router.post(
    "/{project_id}/members",
    status_code=status.HTTP_201_CREATED,
    response_model=Union[InviteAddedResponse, InviteInvitedResponse],
)
async def invite_member(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
    body: InviteMemberBody,
) -> InviteAddedResponse | InviteInvitedResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:mem:invite:{user.id}", 20)

    await require_project_access(session, user, project_id)
    my_role = await project_member_role(session, user.id, project_id)
    if not can_manage_project_members(user, my_role):
        raise ApiError(403, "FORBIDDEN", "Không có quyền mời thành viên")

    email = _norm_email(str(body.email))
    if user.email.strip().lower() == email:
        raise ApiError(422, "VALIDATION_ERROR", "Bạn không thể mời chính mình")

    target = (
        await session.execute(select(User).where(func.lower(User.email) == email))
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    pend = await session.execute(
        select(PendingInvitation).where(
            PendingInvitation.project_id == project_id,
            func.lower(PendingInvitation.email) == email,
        )
    )
    existing_p = pend.scalar_one_or_none()

    if target:
        ex = await session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == target.id,
            )
        )
        if ex.scalar_one_or_none() is not None:
            raise ApiError(
                409,
                "CONFLICT",
                "Thành viên này đã có trong project",
                extra={"field": "email"},
            )
        if existing_p:
            await session.delete(existing_p)
            await session.flush()
    else:
        if existing_p and existing_p.expires_at > now:
            raise ApiError(409, "CONFLICT", "Thành viên này đã có trong project", extra={"field": "email"})
        if existing_p:
            await session.delete(existing_p)
            await session.flush()

    if target:
        pm = ProjectMember(project_id=project_id, user_id=target.id, role=body.role)
        session.add(pm)
        try:
            await session.commit()
        except IntegrityError as e:
            await session.rollback()
            raise ApiError(409, "CONFLICT", "Thành viên này đã có trong project", extra={"field": "email"}) from e
        await session.refresh(pm)
        return InviteAddedResponse(
            message="Đã thêm thành viên vào project thành công",
            member=MemberAddedOut(
                user_id=target.id,
                email=target.email,
                full_name=target.full_name,
                avatar_url=target.avatar_url,
                role=body.role,
                joined_at=pm.joined_at,
            ),
        )

    exp = now + timedelta(days=7)
    inv = PendingInvitation(
        project_id=project_id,
        email=email,
        role=body.role,
        invited_by=user.id,
        expires_at=exp,
    )
    session.add(inv)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ApiError(409, "CONFLICT", "Thành viên này đã có trong project", extra={"field": "email"}) from e
    await session.refresh(inv)

    return InviteInvitedResponse(
        message=f"Đã gửi lời mời đến {email}",
        invitation=InvitationCreatedOut(
            id=inv.id,
            email=inv.email,
            role=inv.role,
            expires_at=inv.expires_at,
        ),
    )


@router.patch("/{project_id}/members/{user_id}", response_model=PatchMemberResponse)
async def patch_member_role(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    body: PatchMemberBody,
) -> PatchMemberResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:mem:patch:{user.id}", 30)

    await require_project_access(session, user, project_id)
    my_role = await project_member_role(session, user.id, project_id)
    if not can_manage_project_members(user, my_role):
        raise ApiError(403, "FORBIDDEN", "Không có quyền")

    row = (
        await session.execute(
            select(ProjectMember, User)
            .select_from(ProjectMember)
            .join(User, User.id == ProjectMember.user_id)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Thành viên không tồn tại")
    pm, member_user = row[0], row[1]
    cur_role = pm.role if isinstance(pm.role, str) else str(pm.role)
    if cur_role.lower() == "owner":
        raise ApiError(403, "FORBIDDEN", "Không thể đổi role Owner")

    await session.execute(update(ProjectMember).where(ProjectMember.id == pm.id).values(role=body.role))
    await session.commit()

    return PatchMemberResponse(
        user_id=member_user.id,
        email=member_user.email,
        full_name=member_user.full_name,
        role=body.role,
        updated_at=datetime.now(UTC),
    )


@router.delete("/{project_id}/members/{user_id}", response_model=DeleteMemberResponse)
async def remove_member(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> DeleteMemberResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:mem:del:{user.id}", 20)

    await require_project_access(session, user, project_id)
    my_role = await project_member_role(session, user.id, project_id)
    if not can_manage_project_members(user, my_role):
        raise ApiError(403, "FORBIDDEN", "Không có quyền xoá")

    pm = (
        await session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if pm is None:
        raise ApiError(404, "NOT_FOUND", "Thành viên không tồn tại")
    cur_role = pm.role if isinstance(pm.role, str) else str(pm.role)
    if cur_role.lower() == "owner":
        raise ApiError(403, "FORBIDDEN", "Không thể xoá Owner. Hãy transfer ownership trước.")

    await session.delete(pm)
    await session.commit()
    return DeleteMemberResponse(message="Đã xoá thành viên khỏi project", user_id=user_id)


@router.post("/{project_id}/transfer-owner", response_model=TransferOwnerResponse)
async def transfer_project_owner(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
    body: TransferOwnerBody,
) -> TransferOwnerResponse:
    redis = get_redis()
    await _rate_limit_hour(redis, f"rl:mem:transfer:{user.id}", 5)

    await require_project_access(session, user, project_id)
    my_role = await project_member_role(session, user.id, project_id)
    if not is_project_owner(my_role):
        raise ApiError(403, "FORBIDDEN", "Chỉ Owner mới được chuyển quyền")
    if body.new_owner_id == user.id:
        raise ApiError(422, "VALIDATION_ERROR", "Không thể chuyển quyền cho chính mình")

    new_row = (
        await session.execute(
            select(ProjectMember, User)
            .select_from(ProjectMember)
            .join(User, User.id == ProjectMember.user_id)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == body.new_owner_id,
            )
        )
    ).one_or_none()
    if new_row is None:
        raise ApiError(404, "NOT_FOUND", "Người nhận không phải thành viên của project")
    new_pm, new_user = new_row[0], new_row[1]

    prev_pm = (
        await session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if prev_pm is None:
        raise ApiError(403, "FORBIDDEN", "Chỉ Owner mới được chuyển quyền")

    await session.execute(
        update(ProjectMember).where(ProjectMember.id == new_pm.id).values(role="owner")
    )
    await session.execute(
        update(ProjectMember).where(ProjectMember.id == prev_pm.id).values(role="pm")
    )
    await session.commit()

    return TransferOwnerResponse(
        message="Đã chuyển quyền sở hữu thành công",
        new_owner=TransferOwnerParty(user_id=new_user.id, full_name=new_user.full_name, role="owner"),
        previous_owner=TransferOwnerParty(user_id=user.id, full_name=user.full_name, role="pm"),
    )


@router.delete("/{project_id}/invitations/{invitation_id}", response_model=CancelInvitationResponse)
async def cancel_pending_invitation(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
    invitation_id: uuid.UUID,
) -> CancelInvitationResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:mem:invdel:{user.id}", 20)

    await require_project_access(session, user, project_id)
    my_role = await project_member_role(session, user.id, project_id)
    if not can_manage_project_members(user, my_role):
        raise ApiError(403, "FORBIDDEN", "Không có quyền huỷ lời mời")

    inv = await session.get(PendingInvitation, invitation_id)
    if inv is None or inv.project_id != project_id:
        raise ApiError(404, "NOT_FOUND", "Lời mời không tồn tại hoặc đã hết hạn")
    if inv.expires_at < datetime.now(UTC):
        raise ApiError(404, "NOT_FOUND", "Lời mời không tồn tại hoặc đã hết hạn")

    await session.delete(inv)
    await session.commit()
    return CancelInvitationResponse(message="Đã huỷ lời mời", invitation_id=invitation_id)
