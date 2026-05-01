import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class UserBrief(BaseModel):
    id: UUID
    full_name: str

    model_config = {"from_attributes": True}


class ProjectStats(BaseModel):
    document_count: int
    testcase_count: int


class ProjectStatsWithMembers(ProjectStats):
    member_count: int


class ProjectListItem(BaseModel):
    id: UUID
    name: str
    slug: str
    description: str | None
    status: str
    stats: ProjectStats
    my_role: str
    created_at: datetime
    updated_at: datetime | None
    created_by: UserBrief | None


class PaginationMeta(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int


class ProjectListResponse(BaseModel):
    data: list[ProjectListItem]
    pagination: PaginationMeta


class ProjectCreateBody(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    slug: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("slug")
    @classmethod
    def slug_fmt(cls, v: str) -> str:
        s = v.strip().lower()
        if not SLUG_PATTERN.fullmatch(s):
            raise ValueError("Slug chỉ được chứa chữ thường, số và dấu gạch ngang")
        return s


class ProjectPatchBody(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class ProjectMemberOut(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    role: str
    avatar_url: str | None
    joined_at: datetime | None


class ProjectDetail(BaseModel):
    id: UUID
    name: str
    slug: str
    description: str | None
    status: str
    stats: ProjectStatsWithMembers
    my_role: str
    members: list[ProjectMemberOut]
    created_at: datetime
    updated_at: datetime | None
    created_by: UserBrief | None


class ArchiveBody(BaseModel):
    status: Literal["active", "archived"]


class ArchiveResponse(BaseModel):
    id: UUID
    status: str
    message: str
