import asyncio
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.llm_chunker import SemanticChunk, llm_chunk_markdown, rule_chunk_markdown
from app.models.document import Chunk, DocVersion, Document
from app.r2_download import download_bytes_from_r2


def _file_ext_from_r2_key(r2_key: str) -> str:
    lower = (r2_key or "").lower()
    idx = lower.rfind(".")
    return lower[idx:] if idx >= 0 else ""


def _extract_text_from_bytes(ext: str, data: bytes) -> str:
    if (ext or "").lower() == ".md":
        return data.decode("utf-8", errors="replace")
    raise RuntimeError(f"Unsupported file type for text extraction: {ext or 'unknown'}")


# Delays (seconds) between consecutive embedding attempts: attempt 1→2, 2→3, 3→4.
_EMBED_RETRY_DELAYS: tuple[float, ...] = (3.0, 10.0, 30.0)
_EMBED_MAX_ATTEMPTS: int = len(_EMBED_RETRY_DELAYS) + 1  # 4 total

# Transient errors that are safe to retry.
_RETRYABLE_HTTPX = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)


async def _embed_batch(texts: list[str], *, model_name_or_path: str) -> tuple[list[list[float]], int]:
    if not settings.embedding_service_url:
        raise RuntimeError("Missing EMBEDDING_SERVICE_URL")

    url = settings.embedding_service_url.rstrip("/") + "/embed/chunks"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.embedding_service_internal_key:
        headers["X-Internal-Key"] = settings.embedding_service_internal_key

    payload = {
        "chunks": [{"text": t} for t in texts],
        "model_name_or_path": model_name_or_path,
        "normalize_embeddings": True,
        "use_fp16": True,
        "batch_size": 32,
    }

    timeout = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=5.0)
    last_exc: Exception | None = None

    for attempt in range(1, _EMBED_MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)

            # 4xx → client error, retrying won't help.
            if 400 <= resp.status_code < 500:
                raise RuntimeError(
                    f"Embedding service client error {resp.status_code}: {resp.text[:300]}"
                )

            # 5xx → server-side transient, retryable.
            if resp.status_code >= 500:
                last_exc = RuntimeError(
                    f"Embedding service server error {resp.status_code} "
                    f"(attempt {attempt}/{_EMBED_MAX_ATTEMPTS}): {resp.text[:300]}"
                )
            else:
                data = resp.json()
                vecs = [e["embedding"] for e in data["embeddings"]]
                elapsed_ms = int(data.get("elapsed_ms") or 0)
                return vecs, elapsed_ms

        except _RETRYABLE_HTTPX as exc:
            last_exc = RuntimeError(
                f"Embedding service unreachable (attempt {attempt}/{_EMBED_MAX_ATTEMPTS}): {exc}"
            )

        if attempt < _EMBED_MAX_ATTEMPTS:
            await asyncio.sleep(_EMBED_RETRY_DELAYS[attempt - 1])

    raise last_exc  # type: ignore[misc]


async def _delete_existing_chunks(session: AsyncSession, doc_version_id: uuid.UUID) -> None:
    chunk_ids = (await session.execute(select(Chunk.id).where(Chunk.doc_version_id == doc_version_id))).scalars().all()
    if chunk_ids:
        ids_literal = ",".join(f"'{cid}'::uuid" for cid in chunk_ids)
        await session.execute(text(f"DELETE FROM chunk_embeddings WHERE chunk_id IN ({ids_literal})"))
    await session.execute(delete(Chunk).where(Chunk.doc_version_id == doc_version_id))


async def process_version_async(version_id: str) -> None:
    """Extract → chunk → embed a document version.

    Sets DocVersion.status to 'ready_for_review' on success.
    Raises on error — caller (worker) is responsible for setting 'rejected'.
    Safe to call on retry: resets status to 'processing' at the start.
    """
    vid = uuid.UUID(version_id)
    async with AsyncSessionLocal() as session:
        v = await session.get(DocVersion, vid)
        if v is None:
            return

        # Reset status so retries restart cleanly from a known state.
        v.status = "processing"
        v.updated_at = datetime.now(UTC)
        await session.commit()

        doc = await session.get(Document, v.document_id)
        if doc is None:
            return

        ext = _file_ext_from_r2_key(v.r2_key)
        raw, _ctype = await asyncio.to_thread(download_bytes_from_r2, v.r2_key)
        full_text = await asyncio.to_thread(_extract_text_from_bytes, ext, raw)

        # ── Chunking: LLM primary, rule-based fallback ───────────────────────
        doc_type_str = str(doc.doc_type)
        try:
            semantic_chunks = await llm_chunk_markdown(full_text, doc_type=doc_type_str)
        except Exception:
            semantic_chunks = rule_chunk_markdown(full_text)

        await _delete_existing_chunks(session, v.id)

        model_name = "BAAI/bge-m3"
        if not semantic_chunks:
            v.status = "ready_for_review"
            v.updated_at = datetime.now(UTC)
            await session.commit()
            return

        base_meta = {
            "ext": ext,
            "document_id": str(doc.id),
            "version_no": v.version_no,
            "screen_name": doc.screen_name,
            "doc_type": doc_type_str,
        }

        chunk_rows: list[Chunk] = []
        for idx, sc in enumerate(semantic_chunks):
            chunk_rows.append(
                Chunk(
                    doc_version_id=v.id,
                    chunk_index=idx,
                    content_text=sc.content,
                    metadata_={
                        **base_meta,
                        "source": sc.chunker,
                        "section_path": sc.section_path,
                        "chunk_type": sc.chunk_type,
                        "summary": sc.summary,
                    },
                    token_count=None,
                )
            )
        session.add_all(chunk_rows)
        await session.flush()

        batch_size = 32
        for i in range(0, len(chunk_rows), batch_size):
            batch = chunk_rows[i : i + batch_size]
            texts = [c.content_text for c in batch]
            vectors, _ = await _embed_batch(texts, model_name_or_path=model_name)

            for c, vec in zip(batch, vectors, strict=False):
                emb_id = uuid.uuid4()
                vec_literal = "[" + ",".join(str(float(x)) for x in vec) + "]"
                await session.execute(
                    text(
                        """
                        INSERT INTO chunk_embeddings (id, chunk_id, embedding, model_name, created_at)
                        VALUES (:id, :chunk_id, CAST(:embedding AS vector), :model_name, NOW())
                        """
                    ),
                    {"id": str(emb_id), "chunk_id": str(c.id), "embedding": vec_literal, "model_name": model_name},
                )

        v.status = "ready_for_review"
        v.updated_at = datetime.now(UTC)
        await session.commit()
