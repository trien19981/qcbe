from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ViewerUserBrief(BaseModel):
    id: UUID | None = None
    full_name: str | None = None


class ViewerDocumentOut(BaseModel):
    id: UUID
    screen_name: str
    doc_type: str
    project_id: UUID


class ViewerVersionOut(BaseModel):
    id: UUID
    version_no: int
    status: str
    changelog_md: str | None = None
    created_at: datetime | None = None
    created_by: ViewerUserBrief | None = None
    approved_at: datetime | None = None


class ViewerVersionItem(BaseModel):
    id: UUID
    version_no: int
    status: str
    is_current: bool


class ViewerChunkOut(BaseModel):
    id: UUID
    chunk_index: int
    content_text: str
    metadata: dict | None = Field(default=None, alias="metadata")
    token_count: int | None = None
    tc_count: int | None = None


class ViewerFigmaFrameOut(BaseModel):
    frame_id: str
    frame_name: str | None = None
    figma_url: str | None = None
    snapshot_url: str | None = None
    synced_at: datetime | None = None


class DocumentViewerResponse(BaseModel):
    document: ViewerDocumentOut
    version: ViewerVersionOut
    all_versions: list[ViewerVersionItem]
    chunks: list[ViewerChunkOut]
    total_chunks: int
    figma_frames: list[ViewerFigmaFrameOut] | None = None


class ChunkOutlineItem(BaseModel):
    id: UUID
    chunk_index: int
    section: str | None = None
    token_count: int | None = None
    tc_count: int | None = None


class DocumentChunksOutlineResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    chunks: list[ChunkOutlineItem]
    total: int


class ChunkTestcaseItem(BaseModel):
    id: UUID
    title: str
    tc_type: str
    priority: str
    status: str
    steps_count: int
    link_type: str
    relevance_score: float
    is_primary_link: bool
    created_by: ViewerUserBrief | None = None
    updated_at: datetime | None = None


class ChunkTestcasesResponse(BaseModel):
    chunk_id: UUID
    chunk_preview: str
    chunk_section: str | None = None
    testcases: list[ChunkTestcaseItem]
    total: int


class CreateTestcaseLinkBody(BaseModel):
    testcase_id: UUID
    link_type: str
    is_primary: bool = False
    relevance_score: float = 1.0


class TestcaseLinkResponse(BaseModel):
    id: UUID
    chunk_id: UUID
    testcase_id: UUID
    link_type: str
    is_primary: bool
    relevance_score: float
    created_at: datetime | None = None


class DeleteTestcaseLinkResponse(BaseModel):
    message: str
    chunk_id: UUID
    testcase_id: UUID

