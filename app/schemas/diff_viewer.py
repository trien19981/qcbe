from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UserBrief(BaseModel):
    id: UUID
    full_name: str | None = None


class VersionBrief(BaseModel):
    id: UUID
    version_no: int
    status: str
    created_at: datetime | None = None
    created_by_name: str | None = None
    changelog_md: str | None = None


class DiffReviewOut(BaseModel):
    id: UUID
    document_id: UUID | None = None
    old_version: VersionBrief | None = None
    new_version: VersionBrief | None = None
    status: str
    is_readonly: bool = False

    ai_summary: str | None = None
    total_changes: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    pending_count: int = 0

    reviewed_at: datetime | None = None
    reviewed_by: UserBrief | None = None
    created_at: datetime | None = None
    estimated_seconds: int | None = None


class DiffChunkOut(BaseModel):
    id: UUID
    chunk_index: int | None = None
    content_text: str
    section: str | None = None


class AffectedTestcaseOut(BaseModel):
    id: UUID
    title: str
    priority: str | None = None


class DiffChangeOut(BaseModel):
    id: UUID
    change_index: int | None = None
    change_type: str
    approval_status: str
    chunk_old: DiffChunkOut | None = None
    chunk_new: DiffChunkOut | None = None
    word_diff_old: str | None = None
    word_diff_new: str | None = None
    similarity_score: float | None = None
    affected_testcases: list[AffectedTestcaseOut] = Field(default_factory=list)
    approve_note: str | None = None


class GetDocumentDiffResponse(BaseModel):
    diff_review: DiffReviewOut
    changes: list[DiffChangeOut]
    message: str | None = None


class DiffReviewStatusProgress(BaseModel):
    total_chunks_old: int | None = None
    total_chunks_new: int | None = None
    processed_pairs: int | None = None
    percentage: int | None = None


class DiffReviewStatusResponse(BaseModel):
    diff_review_id: UUID
    status: str
    progress: DiffReviewStatusProgress | None = None
    total_changes: int = 0
    updated_at: datetime | None = None


class PatchDiffChangeBody(BaseModel):
    approval_status: str
    approve_note: str | None = None


class PatchDiffChangeResponse(BaseModel):
    id: UUID
    approval_status: str
    approved_by: UserBrief | None = None
    approved_at: datetime | None = None
    approve_note: str | None = None
    diff_review_summary: dict = Field(default_factory=dict)


class SubmitDiffReviewBody(BaseModel):
    review_note: str | None = None


class SubmitDiffReviewResponse(BaseModel):
    diff_review_id: UUID
    status: str
    summary: dict
    new_version_status: str | None = None
    reembed_job_id: str | None = None
    message: str | None = None


class DiffHistoryChangeItem(BaseModel):
    id: UUID
    change_index: int | None = None
    change_type: str
    section: str | None = None
    ai_change_summary: str | None = None
    chunk_old_id: UUID | None = None
    chunk_new_id: UUID | None = None


class DiffHistoryVersionItem(BaseModel):
    id: UUID
    version_no: int


class DiffHistoryReviewItem(BaseModel):
    diff_review_id: UUID
    from_version: DiffHistoryVersionItem
    to_version: DiffHistoryVersionItem
    approved_at: datetime | None = None
    approved_by: UserBrief | None = None
    review_note: str | None = None
    total_changes: int = 0
    changes: list[DiffHistoryChangeItem] = Field(default_factory=list)


class GetDiffHistoryResponse(BaseModel):
    document_id: UUID
    screen_name: str
    doc_type: str
    diff_history: list[DiffHistoryReviewItem]
    total_diff_reviews: int

