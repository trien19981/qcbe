from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.project import PaginationMeta


class DocUserBrief(BaseModel):
    id: UUID
    full_name: str
    avatar_url: str | None = None


class LatestVersionOut(BaseModel):
    id: UUID
    version_no: int
    status: str
    changelog_md: str | None
    created_at: datetime | None
    created_by: DocUserBrief | None
    approved_at: datetime | None


class DocumentListItem(BaseModel):
    id: UUID
    project_id: UUID
    screen_name: str
    doc_type: str
    description: str | None
    version_count: int
    latest_version: LatestVersionOut
    created_at: datetime | None
    updated_at: datetime | None


class DocumentListResponse(BaseModel):
    data: list[DocumentListItem]
    pagination: PaginationMeta
    has_processing: bool


class ScreenCountItem(BaseModel):
    screen_name: str
    doc_count: int


class ScreensResponse(BaseModel):
    screens: list[ScreenCountItem]
    total: int


class ApproverBrief(BaseModel):
    id: UUID
    full_name: str


class VersionDetailOut(BaseModel):
    id: UUID
    version_no: int
    status: str
    r2_url: str
    changelog_md: str | None
    created_at: datetime | None
    created_by: DocUserBrief | None
    approved_by: ApproverBrief | None
    approved_at: datetime | None
    chunk_count: int
    is_latest: bool


class VersionsListResponse(BaseModel):
    document_id: UUID
    screen_name: str
    doc_type: str
    versions: list[VersionDetailOut]
    total_versions: int


class DownloadUrlResponse(BaseModel):
    download_url: str
    filename: str
    content_type: str
    expires_in: int


class DocumentPatchBody(BaseModel):
    screen_name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class DocumentPatchResponse(BaseModel):
    id: UUID
    screen_name: str
    doc_type: str
    description: str | None
    updated_at: datetime | None


class DocumentDeleteResponse(BaseModel):
    message: str
    document_id: UUID
    deleted_versions: int
    deleted_chunks: int
    unlinked_testcases: int


class ExistingDocumentSummary(BaseModel):
    id: UUID
    screen_name: str
    doc_type: str
    version_count: int
    latest_version_no: int
    latest_status: str


class UploadDocumentBodyDocument(BaseModel):
    id: UUID
    project_id: UUID
    screen_name: str
    doc_type: str
    description: str | None


class UploadDocumentBodyVersion(BaseModel):
    id: UUID
    version_no: int
    status: str
    r2_key: str
    created_at: datetime | None


class UploadNewDocumentResponse202(BaseModel):
    document: UploadDocumentBodyDocument
    version: UploadDocumentBodyVersion
    job_id: str | None
    message: str


class UploadVersionPreviousVersion(BaseModel):
    id: UUID
    version_no: int
    status: str


class UploadVersionBodyVersion(BaseModel):
    id: UUID
    version_no: int
    status: str
    r2_key: str
    changelog_md: str | None
    created_at: datetime | None


class UploadVersionResponse202(BaseModel):
    document_id: UUID
    version: UploadVersionBodyVersion
    previous_version: UploadVersionPreviousVersion
    diff_job_id: str | None
    embed_job_id: str | None
    message: str


class VersionEmbedProgress(BaseModel):
    total_chunks: int
    embedded_chunks: int
    percentage: int


class VersionStatusResponse(BaseModel):
    version_id: UUID
    version_no: int
    status: str
    chunk_count: int
    embed_progress: VersionEmbedProgress | None = None
    diff_ready: bool | None = None
    diff_review_id: str | None = None
    updated_at: datetime | None


class DeleteVersionResponse(BaseModel):
    message: str
    version_id: UUID
    deleted_chunks: int
    document_id: UUID
    remaining_versions: int
