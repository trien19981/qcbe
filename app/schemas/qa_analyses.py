"""Pydantic schemas for Q&A Gap Analysis API (step 1 in Q&A → TVP → TC pipeline)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

QACategory = Literal[
    "Functional",
    "Business Logic",
    "Data",
    "Validation",
    "Integration",
    "Edge Case",
    "UI/UX",
    "Non-functional",
]
QARisk = Literal["High", "Medium", "Low"]
QAStatus = Literal["draft", "in_review", "completed"]
QAItemStatus = Literal["open", "answered", "wont_fix", "deferred"]

ALLOWED_DOC_TYPES = {"basic_design", "api_design", "detail_design", "testcase_manual"}


class QAUserBrief(BaseModel):
    id: UUID
    full_name: str


class QAGenerateBody(BaseModel):
    screen_name: str = Field(..., min_length=1, max_length=200)
    doc_types: list[str] = Field(..., min_length=1)
    overwrite_existing: bool = False

    @field_validator("doc_types")
    @classmethod
    def doc_types_allowed(cls, v: list[str]) -> list[str]:
        for d in v:
            if d not in ALLOWED_DOC_TYPES:
                raise ValueError(f"doc_type không hợp lệ: {d}")
        return v


class QAGenerateAccepted(BaseModel):
    job_id: UUID
    screen_name: str
    doc_types: list[str]
    estimated_seconds: int
    message: str


class QAJobProgressOut(BaseModel):
    total_chunks: int
    processed_chunks: int
    percentage: int


class QAJobResultOut(BaseModel):
    qa_analysis_id: UUID
    total_items: int


class QAJobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    progress: QAJobProgressOut
    result: QAJobResultOut | None = None
    error_message: str | None = None
    updated_at: datetime | None


class QAGapItemOut(BaseModel):
    id: UUID
    qa_analysis_id: UUID
    gap_id: str
    category: str
    gap_description: str
    risk: str
    question: str
    answer: str | None
    answer_status: str
    answered_by: QAUserBrief | None
    answered_at: datetime | None
    source_chunk_id: UUID | None
    display_order: int
    created_at: datetime | None
    updated_at: datetime | None


class QAItemPatchBody(BaseModel):
    answer: str | None = None
    answer_status: QAItemStatus | None = None


class QAItemCreateBody(BaseModel):
    category: QACategory
    gap_description: str = Field(..., min_length=1, max_length=4000)
    risk: QARisk
    question: str = Field(..., min_length=1, max_length=4000)
    answer: str | None = None


class QAItemDeleteResponse(BaseModel):
    message: str
    item_id: UUID


class QAGapAnalysisSummary(BaseModel):
    total_items: int
    answered_items: int
    progress_percent: int
    by_category: dict[str, int]
    by_risk: dict[str, int]
    by_status: dict[str, int]


class QAGapAnalysisListItem(BaseModel):
    id: UUID
    project_id: UUID
    screen_name: str
    doc_types: list[str]
    status: str
    total_items: int
    answered_items: int
    progress_percent: int
    generated_by: QAUserBrief | None
    generated_at: datetime | None
    completed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class QAGapAnalysisListResponse(BaseModel):
    data: list[QAGapAnalysisListItem]
    total: int


class QAGapAnalysisDetailResponse(BaseModel):
    id: UUID
    project_id: UUID
    screen_name: str
    doc_types: list[str]
    status: str
    items: list[QAGapItemOut]
    summary: QAGapAnalysisSummary
    generated_by: QAUserBrief | None
    generated_at: datetime | None
    completed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
