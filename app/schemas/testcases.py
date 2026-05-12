"""Pydantic schemas for S12 testcase list API (S12_TC_LIST_DESIGN.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

TcType = Literal["manual", "api", "e2e"]
Priority = Literal["critical", "high", "medium", "low"]
TcStatus = Literal["active", "draft", "archived"]
SortBy = Literal["created_at", "updated_at", "priority"]
SortDir = Literal["asc", "desc"]
BulkAction = Literal["archive", "delete", "set_priority", "mark_reviewed"]


class TestcaseUserBrief(BaseModel):
    id: UUID
    full_name: str


class LinkedChunkOut(BaseModel):
    chunk_id: UUID
    document_id: UUID | None = None
    doc_type: str
    section: str | None = None
    is_primary: bool


class TestcaseListItem(BaseModel):
    id: UUID
    tc_id: str
    project_id: UUID
    screen_name: str
    title: str
    tc_type: str
    priority: str
    status: str
    needs_review: bool
    steps_count: int
    steps_preview: list[str]
    expected_result: str | None
    technique: str | None = None
    source_tvp_id: UUID | None = None
    source_tvp_section: str | None = None
    linked_chunks: list[LinkedChunkOut]
    linked_chunks_count: int
    created_at: datetime | None
    updated_at: datetime | None
    created_by: TestcaseUserBrief | None


class PaginationOut(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int


class TestcaseSummaryCounts(BaseModel):
    total: int
    needs_review_count: int
    by_status: dict[str, int]
    by_priority: dict[str, int]


class TestcaseListResponse(BaseModel):
    data: list[TestcaseListItem]
    pagination: PaginationOut
    summary: TestcaseSummaryCounts


class ScreenAggItem(BaseModel):
    screen_name: str
    tc_count: int
    needs_review_count: int


class TestcaseScreensResponse(BaseModel):
    screens: list[ScreenAggItem]
    total: int


class TestcaseStatsResponse(BaseModel):
    project_id: UUID
    total_testcases: int
    needs_review: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    by_tc_type: dict[str, int]
    by_screen: list[dict[str, int | str]]
    coverage: dict[str, int | float]


class TestcaseGenerateBody(BaseModel):
    screen_name: str = Field(..., min_length=1, max_length=200)
    doc_types: list[str] = Field(default_factory=list)
    tc_type: TcType
    overwrite_existing: bool = False
    tvp_id: UUID | None = None

    @field_validator("doc_types")
    @classmethod
    def doc_types_allowed(cls, v: list[str]) -> list[str]:
        allowed = {"basic_design", "api_design", "detail_design", "testcase_manual"}
        for d in v:
            if d not in allowed:
                raise ValueError(f"doc_type không hợp lệ: {d}")
        return v


class TestcaseGenerateAccepted(BaseModel):
    job_id: UUID
    screen_name: str
    doc_types: list[str]
    tvp_id: UUID | None = None
    estimated_tc_count: int
    estimated_seconds: int
    message: str


class GenerateProgressOut(BaseModel):
    total_chunks: int
    processed_chunks: int
    percentage: int


class GenerateResultOut(BaseModel):
    created_count: int
    testcase_ids: list[UUID]


class TestcaseGenerateJobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    progress: GenerateProgressOut
    result: GenerateResultOut | None = None
    error_message: str | None = None
    updated_at: datetime | None


class TestcaseBulkBody(BaseModel):
    action: BulkAction
    testcase_ids: list[UUID] = Field(..., min_length=1, max_length=100)
    priority: Priority | None = None

    @field_validator("testcase_ids")
    @classmethod
    def max_ids(cls, v: list[UUID]) -> list[UUID]:
        if len(v) > 100:
            raise ValueError("Tối đa 100 testcase_ids")
        return v


class TestcaseBulkResponse(BaseModel):
    action: str
    affected_count: int
    testcase_ids: list[UUID]
    skipped_ids: list[UUID]
    message: str


class TestcaseDeleteResponse(BaseModel):
    message: str
    testcase_id: UUID
    unlinked_chunks: int
