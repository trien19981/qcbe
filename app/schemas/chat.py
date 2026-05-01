from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.project import PaginationMeta


class ChatUserBrief(BaseModel):
    id: UUID
    full_name: str


class ConversationScope(BaseModel):
    type: str  # project | screen | doc_type
    screen_name: str | None = None
    doc_types: list[str] | None = None


class ConversationListItem(BaseModel):
    id: UUID
    title: str | None
    scope: ConversationScope
    message_count: int
    last_message_at: datetime | None
    created_at: datetime | None
    created_by: ChatUserBrief


class ConversationsListResponse(BaseModel):
    conversations: list[ConversationListItem]
    pagination: PaginationMeta


class CreateConversationBody(BaseModel):
    scope_type: str = Field(..., description="project|screen|doc_type")
    screen_name: str | None = None
    doc_types: list[str] | None = None


class CreateConversationResponse(BaseModel):
    id: UUID
    title: str | None
    scope: ConversationScope
    suggested_questions: list[str]
    has_approved_documents: bool
    message_count: int
    created_at: datetime | None


class CitationOut(BaseModel):
    index: int
    chunk_id: UUID | None
    badge_text: str
    doc_type: str | None = None
    screen: str | None = None
    section: str | None = None
    document_id: UUID | None = None
    version_id: UUID | None = None
    preview: str | None = None
    similarity_score: float | None = None


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    citations: list[CitationOut] = []
    created_at: datetime | None = None


class SendMessageBody(BaseModel):
    content: str = Field(..., min_length=3, max_length=2000)
    stream: bool = False


class SendMessageResponse(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    conversation_title: str | None = None


class ConversationOut(BaseModel):
    id: UUID
    title: str | None
    scope: ConversationScope
    created_at: datetime | None


class ConversationMessagesResponse(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]
    pagination: PaginationMeta


class DeleteConversationResponse(BaseModel):
    message: str
    conversation_id: UUID
    deleted_messages: int


class SuggestedQuestionsResponse(BaseModel):
    conversation_id: UUID
    scope_label: str
    questions: list[str]
    generated_at: datetime | None = None

