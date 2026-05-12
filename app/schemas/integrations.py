from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

IntegrationType = Literal["figma", "backlog"]
LinkType = Literal["figma_frame", "backlog_issue"]
SyncStatus = Literal["pending", "syncing", "synced", "failed"]
EmbedStatus = Literal["pending", "embedding", "embedded", "failed"]


class IntegrationConfigUpsertBody(BaseModel):
    config: dict = Field(default_factory=dict)


class IntegrationConfigOut(BaseModel):
    id: UUID
    project_id: UUID
    type: IntegrationType
    config: dict
    created_by: UUID | None
    created_at: datetime | None
    updated_at: datetime | None


class IntegrationLinkUpsertBody(BaseModel):
    project_id: UUID
    screen_name: str = Field(min_length=1, max_length=255)
    type: LinkType
    external_id: str = Field(min_length=1, max_length=255)
    external_url: str | None = Field(default=None, max_length=2000)


class IntegrationLinkOut(BaseModel):
    id: UUID
    project_id: UUID
    screen_name: str
    document_id: UUID | None
    type: LinkType
    external_id: str
    external_url: str | None
    doc_version_id: UUID | None
    sync_status: SyncStatus
    # Only for figma_frame links (when figma_artifact_id is present)
    embed_status: EmbedStatus | None = None
    error_message: str | None
    last_synced_at: datetime | None
    created_by: UUID | None
    created_at: datetime | None
    updated_at: datetime | None


class SyncLinkRequestBody(BaseModel):
    link_id: UUID


class SyncLinkResponse(BaseModel):
    link_id: UUID
    sync_status: SyncStatus
    rq_job_id: str
    message: str


class FigmaTestBody(BaseModel):
    personal_access_token: str = Field(min_length=1)
    file_key: str = Field(min_length=1)


class FigmaTestResponse(BaseModel):
    ok: bool
    file_name: str | None = None
    error: str | None = None


class FigmaIngestBody(BaseModel):
    project_id: UUID
    screen_name: str = Field(min_length=1, max_length=255)
    figma_url: str = Field(min_length=1, max_length=2000)
    # Optional override; if omitted, uses stored ExternalIntegration(config) for the project.
    personal_access_token: str | None = Field(default=None, min_length=1)


class FigmaIngestResponse(BaseModel):
    link_id: UUID
    figma_artifact_id: UUID
    sync_status: SyncStatus
    embed_status: EmbedStatus
    rq_job_id: str
    screenshot_url: str | None = None
    markdown: str | None = None
