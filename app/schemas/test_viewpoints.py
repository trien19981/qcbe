"""Pydantic schemas for Test Viewpoints API (step 2 in Q&A → TVP → TC pipeline)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

TVPStatus = Literal["draft", "approved", "archived"]
ChecklistStatus = Literal["covered", "not_covered", "n_a"]

ALLOWED_DOC_TYPES = {"basic_design", "api_design", "detail_design", "testcase_manual"}

CHECKLIST_18_KEYS: list[str] = [
    "FUNCTIONAL_HAPPY_PATH",
    "INPUT_VALIDATION",
    "BOUNDARY_VALUE",
    "NEGATIVE_CASE",
    "USER_BEHAVIOR",
    "SYSTEM_BEHAVIOR",
    "DATA_INTEGRITY",
    "DB_UI_DATA_MAPPING",
    "INTEGRATION_API",
    "SECURITY_BASIC",
    "UX_UI",
    "STATE_FLOW",
    "CONCURRENCY",
    "DATA_LIFECYCLE",
    "SEARCH_FILTER_SORT",
    "PAGINATION_LARGE_DATA",
    "CROSS_FIELD_VALIDATION",
    "IMPORT_EXPORT",
]


class TVPUserBrief(BaseModel):
    id: UUID
    full_name: str


class TVPChecklistItem(BaseModel):
    key: str
    label: str | None = None
    status: ChecklistStatus = "not_covered"
    note: str | None = None


class TVPGenerateBody(BaseModel):
    screen_name: str = Field(..., min_length=1, max_length=200)
    doc_types: list[str] = Field(default_factory=list)
    qa_analysis_id: UUID | None = None
    overwrite_existing: bool = False

    @field_validator("doc_types")
    @classmethod
    def doc_types_allowed(cls, v: list[str]) -> list[str]:
        for d in v:
            if d not in ALLOWED_DOC_TYPES:
                raise ValueError(f"doc_type không hợp lệ: {d}")
        return v


class TVPGenerateAccepted(BaseModel):
    job_id: UUID
    screen_name: str
    qa_analysis_id: UUID | None
    estimated_seconds: int
    message: str


class TVPJobProgressOut(BaseModel):
    total_chunks: int
    processed_chunks: int
    percentage: int


class TVPJobResultOut(BaseModel):
    tvp_id: UUID


class TVPJobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    progress: TVPJobProgressOut
    result: TVPJobResultOut | None = None
    error_message: str | None = None
    updated_at: datetime | None


class TVPListItem(BaseModel):
    id: UUID
    project_id: UUID
    screen_name: str
    status: str
    qa_analysis_id: UUID | None
    coverage_total: int
    coverage_covered: int
    coverage_percent: int
    generated_by: TVPUserBrief | None
    approved_by: TVPUserBrief | None
    approved_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class TVPListResponse(BaseModel):
    data: list[TVPListItem]
    total: int


class TVPDetailResponse(BaseModel):
    id: UUID
    project_id: UUID
    screen_name: str
    qa_analysis_id: UUID | None
    status: str
    content_md: str
    checklist_18: list[TVPChecklistItem]
    coverage_total: int
    coverage_covered: int
    coverage_percent: int
    generated_by: TVPUserBrief | None
    approved_by: TVPUserBrief | None
    approved_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class TVPPatchBody(BaseModel):
    content_md: str | None = None
    checklist_18: list[TVPChecklistItem] | None = None


class TVPApproveResponse(BaseModel):
    id: UUID
    status: str
    approved_at: datetime | None
    message: str
