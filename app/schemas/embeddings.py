from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field


class ChunkForEmbedding(BaseModel):
    # Có thể null nếu client không có sẵn id.
    id: UUID | None = None
    text: Annotated[str, Field(min_length=1, max_length=20000)]


class EmbedChunksRequest(BaseModel):
    chunks: list[ChunkForEmbedding] = Field(min_length=1, max_length=200)

    # Model name/path trên HF hoặc đường dẫn local đã tải sẵn.
    model_name_or_path: str = Field(default="BAAI/bge-m3", min_length=1, max_length=500)

    normalize_embeddings: bool = True
    use_fp16: bool = True
    batch_size: int = Field(default=32, ge=1, le=512)


class EmbeddedChunk(BaseModel):
    id: UUID | None = None
    embedding: list[float]


class EmbedChunksResponse(BaseModel):
    model_name_or_path: str
    dimension: int
    embeddings: list[EmbeddedChunk]
    # Thời gian để xử lý request (ms) - hữu ích cho debug.
    elapsed_ms: int

