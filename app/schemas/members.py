from datetime import datetime
from typing import Literal, Union
from uuid import UUID

from pydantic import BaseModel, EmailStr


class MemberListItem(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    avatar_url: str | None
    role: str
    joined_at: datetime | None
    is_current_user: bool


class PendingInvitationOut(BaseModel):
    id: UUID
    email: str
    role: str
    invited_by_name: str | None
    expires_at: datetime
    created_at: datetime | None


class MembersListResponse(BaseModel):
    members: list[MemberListItem]
    pending_invitations: list[PendingInvitationOut]
    total_members: int
    total_pending: int


class InviteMemberBody(BaseModel):
    email: EmailStr
    role: Literal["pm", "qc", "dev"]


class MemberAddedOut(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    avatar_url: str | None
    role: str
    joined_at: datetime | None


class InvitationCreatedOut(BaseModel):
    id: UUID
    email: str
    role: str
    expires_at: datetime


class InviteAddedResponse(BaseModel):
    type: Literal["added"] = "added"
    message: str
    member: MemberAddedOut


class InviteInvitedResponse(BaseModel):
    type: Literal["invited"] = "invited"
    message: str
    invitation: InvitationCreatedOut


InviteMemberResponse = Union[InviteAddedResponse, InviteInvitedResponse]


class PatchMemberBody(BaseModel):
    role: Literal["pm", "qc", "dev"]


class PatchMemberResponse(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    role: str
    updated_at: datetime


class DeleteMemberResponse(BaseModel):
    message: str
    user_id: UUID


class TransferOwnerBody(BaseModel):
    new_owner_id: UUID


class TransferOwnerParty(BaseModel):
    user_id: UUID
    full_name: str
    role: str


class TransferOwnerResponse(BaseModel):
    message: str
    new_owner: TransferOwnerParty
    previous_owner: TransferOwnerParty


class CancelInvitationResponse(BaseModel):
    message: str
    invitation_id: UUID


class AcceptInvitationBody(BaseModel):
    user_id: UUID


class AcceptInvitationProject(BaseModel):
    id: UUID
    name: str
    slug: str


class AcceptInvitationResponse(BaseModel):
    message: str
    project: AcceptInvitationProject
    role: str
