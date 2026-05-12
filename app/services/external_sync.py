"""Sync a ScreenExternalLink:
- figma_frame  → FigmaArtifact (tách hoàn toàn khỏi document pipeline)
- backlog_issue → DocVersion (giữ nguyên flow cũ)
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text

from app.config import settings
from app.services.anthropic_stream_final import stream_user_message_text
from app.database import AsyncSessionLocal
from app.document_processing import _delete_existing_chunks, _embed_batch
from app.llm_chunker import llm_chunk_markdown, rule_chunk_markdown
from app.models.document import Chunk, DocVersion, Document
from app.models.external import ExternalIntegration, FigmaArtifact, ScreenExternalLink


_MODEL_NAME = "BAAI/bge-m3"


# ---------------------------------------------------------------------------
# Figma path — Phase 1 (ingest) ghi vào figma_artifacts; Phase 2 (embed) chunk+embed
# ---------------------------------------------------------------------------

async def _llm_refine_figma_markdown(
    raw_markdown: str,
    *,
    screen_name: str,
    node_name: str | None,
    node_id: str,
    figma_url: str | None,
    screenshot_url: str | None,
    model: str,
) -> str:
    """Rewrite/normalize markdown for better downstream chunking & retrieval.

    - Opt-in only (caller decides).
    - Must be robust: any failure should fall back to raw_markdown.
    """
    if not settings.anthropic_api_key:
        return raw_markdown
    try:
        from anthropic import AsyncAnthropic  # type: ignore[import-untyped]
    except Exception:
        return raw_markdown

    client_kwargs: dict = {"api_key": settings.anthropic_api_key}
    if settings.anthropic_base_url:
        client_kwargs["base_url"] = settings.anthropic_base_url
    client = AsyncAnthropic(**client_kwargs)

    # Keep the prompt simple: we only want better structure, not invented content.
    ctx_lines = [
        f"screen_name: {screen_name}",
        f"node_name: {node_name or ''}",
        f"node_id: {node_id}",
        f"figma_url: {figma_url or ''}",
        f"screenshot_url: {screenshot_url or ''}",
    ]
    user_prompt = (
        "Bạn sẽ nhận 1 bản Markdown được tạo tự động từ Figma frame.\n"
        "Hãy *chỉ* chỉnh sửa để Markdown dễ đọc, nhất quán, tối ưu cho RAG.\n"
        "\n"
        "RÀNG BUỘC:\n"
        "- KHÔNG bịa thêm thông tin không có trong input.\n"
        "- Giữ nguyên số liệu/label/điều kiện/logic nếu có.\n"
        "- Chuẩn hoá heading: bắt đầu bằng H1 là tên màn hình/frame, dùng H2/H3 cho sections.\n"
        "- Gom các bullet rời rạc thành nhóm hợp lý; loại bỏ trùng lặp hiển nhiên.\n"
        "- Nếu có phần 'Screenshot' hoặc link ảnh, giữ lại một dòng tham chiếu.\n"
        "- Output trả về CHỈ markdown, không thêm giải thích, không bọc ```.\n"
        "\n"
        f"[META]\n{chr(10).join(ctx_lines)}\n\n"
        f"[INPUT MARKDOWN]\n{raw_markdown}"
    )

    out = (
        await stream_user_message_text(
            client,
            model=model,
            max_tokens=2500,
            user_text=user_prompt,
        )
    ).strip()
    return out or raw_markdown


async def ingest_figma_artifact_async(session, link: ScreenExternalLink, config: dict) -> FigmaArtifact:
    from app.clients.figma import export_node_images, fetch_node, list_file_components
    from app.clients.figma_parser import figma_node_to_markdown

    file_key = config["file_key"]
    token = config["personal_access_token"]
    node_id = link.external_id

    node = await fetch_node(file_key=file_key, node_id=node_id, token=token)
    await asyncio.sleep(1)
    file_components = await list_file_components(file_key=file_key, token=token)
    await asyncio.sleep(1)
    images = await export_node_images(
        file_key=file_key, node_ids=[node_id], token=token, format="png", scale=1
    )
    screenshot_url = images.get(node_id)
    markdown = figma_node_to_markdown(node, file_components=file_components, screenshot_url=screenshot_url)

    # Optional: refine markdown with LLM for better structure/retrieval.
    # Default ON when ANTHROPIC_API_KEY is configured; explicit opt-out via llm_markdown=false.
    llm_flag = config.get("llm_markdown")
    llm_enabled = (settings.anthropic_api_key is not None) and (llm_flag is not False)
    if llm_enabled:
        llm_model = str(config.get("llm_markdown_model") or settings.anthropic_model)
        try:
            markdown = await _llm_refine_figma_markdown(
                markdown,
                screen_name=link.screen_name,
                node_name=str(node.get("name") or "").strip() or None,
                node_id=node_id,
                figma_url=link.external_url,
                screenshot_url=screenshot_url,
                model=llm_model,
            )
        except Exception:
            # Keep ingest resilient; any LLM failure falls back to parser markdown.
            pass

    # Upsert FigmaArtifact
    artifact = (
        await session.execute(
            select(FigmaArtifact).where(
                FigmaArtifact.project_id == link.project_id,
                FigmaArtifact.screen_name == link.screen_name,
                FigmaArtifact.node_id == node_id,
            )
        )
    ).scalar_one_or_none()

    if artifact is None:
        artifact = FigmaArtifact(
            project_id=link.project_id,
            screen_name=link.screen_name,
            file_key=file_key,
            node_id=node_id,
            node_url=link.external_url,
            created_by=link.created_by,
        )
        session.add(artifact)

    artifact.markdown = markdown
    artifact.screenshot_url = screenshot_url
    artifact.sync_status = "synced"
    artifact.updated_at = datetime.now(UTC)
    artifact.last_synced_at = datetime.now(UTC)
    artifact.error_message = None
    # New ingest always schedules embed as the next step
    artifact.embed_status = "pending"
    artifact.embed_error_message = None
    artifact.embedded_at = None
    await session.flush()

    return artifact


async def embed_figma_artifact_async(figma_artifact_id: str) -> None:
    """Phase 2: chunk + embed an existing FigmaArtifact (runs in worker)."""
    if not settings.figma_embedding_enabled:
        # Hard guard: do not perform any embedding writes when disabled.
        return

    artifact_uuid = uuid.UUID(figma_artifact_id)

    async with AsyncSessionLocal() as session:
        artifact = await session.get(FigmaArtifact, artifact_uuid)
        if artifact is None:
            return

        # Mark embedding
        artifact.embed_status = "embedding"
        artifact.embed_error_message = None
        artifact.updated_at = datetime.now(UTC)
        await session.commit()

    try:
        async with AsyncSessionLocal() as session:
            artifact = await session.get(FigmaArtifact, artifact_uuid)
            if artifact is None:
                return

            # We need link fields for metadata; derive a best-effort base meta directly from artifact.
            node_id = artifact.node_id
            node_url = artifact.node_url or ""
            markdown = artifact.markdown or ""

            # Delete old chunks for this artifact
            old_chunks = (
                await session.execute(select(Chunk).where(Chunk.figma_artifact_id == artifact.id))
            ).scalars().all()
            for c in old_chunks:
                await session.delete(c)
            await session.flush()

            if not markdown.strip():
                artifact.embed_status = "failed"
                artifact.embed_error_message = "Missing markdown — ingest must run before embedding."
                artifact.updated_at = datetime.now(UTC)
                await session.commit()
                return

            # Chunk
            try:
                semantic_chunks = await llm_chunk_markdown(markdown, doc_type="detail_design")
            except Exception:
                semantic_chunks = rule_chunk_markdown(markdown)

            if semantic_chunks:
                base_meta = {
                    "project_id": str(artifact.project_id),
                    "screen_name": artifact.screen_name,
                    "figma_artifact_id": str(artifact.id),
                    "node_id": node_id,
                    "node_url": node_url,
                    "source": "figma",
                }
                chunk_rows: list[Chunk] = []
                for idx, sc in enumerate(semantic_chunks):
                    chunk_rows.append(
                        Chunk(
                            figma_artifact_id=artifact.id,
                            doc_version_id=None,
                            chunk_index=idx,
                            content_text=sc.content,
                            metadata_={
                                **base_meta,
                                "chunker": sc.chunker,
                                "section_path": sc.section_path,
                                "chunk_type": sc.chunk_type,
                                "summary": sc.summary,
                            },
                        )
                    )
                session.add_all(chunk_rows)
                await session.flush()

                # Embed
                for i in range(0, len(chunk_rows), 32):
                    batch = chunk_rows[i : i + 32]
                    vectors, _ = await _embed_batch(
                        [c.content_text for c in batch], model_name_or_path=_MODEL_NAME
                    )
                    for c, vec in zip(batch, vectors, strict=False):
                        vec_literal = "[" + ",".join(str(float(x)) for x in vec) + "]"
                        await session.execute(
                            text(
                                "INSERT INTO chunk_embeddings (id, chunk_id, embedding, model_name, created_at) "
                                "VALUES (:id, :chunk_id, CAST(:embedding AS vector), :model_name, NOW())"
                            ),
                            {
                                "id": str(uuid.uuid4()),
                                "chunk_id": str(c.id),
                                "embedding": vec_literal,
                                "model_name": _MODEL_NAME,
                            },
                        )

            artifact.embed_status = "embedded"
            artifact.embedded_at = datetime.now(UTC)
            artifact.embed_error_message = None
            artifact.updated_at = datetime.now(UTC)
            await session.commit()

    except Exception as exc:
        async with AsyncSessionLocal() as session:
            artifact = await session.get(FigmaArtifact, artifact_uuid)
            if artifact:
                artifact.embed_status = "failed"
                artifact.embed_error_message = str(exc)[:1000]
                artifact.updated_at = datetime.now(UTC)
                await session.commit()
        raise


# ---------------------------------------------------------------------------
# Backlog path — giữ nguyên flow cũ dùng doc_versions
# ---------------------------------------------------------------------------

def _pick_target_doc_type(link_type: str) -> str:
    return "testcase_manual"


async def _resolve_target_document(session, link: ScreenExternalLink) -> Document:
    if link.document_id is not None:
        doc = await session.get(Document, link.document_id)
        if doc is not None:
            return doc

    preferred_type = _pick_target_doc_type(link.type)
    rows = (
        await session.execute(
            select(Document)
            .where(
                Document.project_id == link.project_id,
                Document.screen_name == link.screen_name,
            )
            .order_by(Document.created_at.asc())
        )
    ).scalars().all()

    if not rows:
        raise RuntimeError(
            f"No document found for project={link.project_id} screen={link.screen_name}"
        )

    preferred = next((d for d in rows if str(d.doc_type) == preferred_type), None)
    return preferred or rows[0]


async def _ingest_markdown(
    session,
    *,
    document: Document,
    source: str,
    markdown: str,
    link: ScreenExternalLink,
) -> DocVersion:
    existing_nos = (
        await session.execute(
            select(DocVersion.version_no).where(DocVersion.document_id == document.id)
        )
    ).scalars().all()
    next_no = (max(existing_nos) + 1) if existing_nos else 1

    version = DocVersion(
        document_id=document.id,
        version_no=next_no,
        source=source,
        r2_key=None,
        r2_url=None,
        status="ready_for_review",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(version)
    await session.flush()

    doc_type_str = str(document.doc_type)
    try:
        semantic_chunks = await llm_chunk_markdown(markdown, doc_type=doc_type_str)
    except Exception:
        semantic_chunks = rule_chunk_markdown(markdown)

    if not semantic_chunks:
        return version

    base_meta = {
        "project_id": str(link.project_id),
        "screen_name": link.screen_name,
        "document_id": str(document.id),
        "version_no": next_no,
        "doc_type": doc_type_str,
        "source": source,
        "external_id": link.external_id,
        "external_url": link.external_url or "",
    }

    chunk_rows: list[Chunk] = []
    for idx, sc in enumerate(semantic_chunks):
        chunk_rows.append(
            Chunk(
                doc_version_id=version.id,
                chunk_index=idx,
                content_text=sc.content,
                metadata_={
                    **base_meta,
                    "chunker": sc.chunker,
                    "section_path": sc.section_path,
                    "chunk_type": sc.chunk_type,
                    "summary": sc.summary,
                },
                token_count=None,
            )
        )
    session.add_all(chunk_rows)
    await session.flush()

    for i in range(0, len(chunk_rows), 32):
        batch = chunk_rows[i : i + 32]
        vectors, _ = await _embed_batch(
            [c.content_text for c in batch], model_name_or_path=_MODEL_NAME
        )
        for c, vec in zip(batch, vectors, strict=False):
            vec_literal = "[" + ",".join(str(float(x)) for x in vec) + "]"
            await session.execute(
                text(
                    "INSERT INTO chunk_embeddings (id, chunk_id, embedding, model_name, created_at) "
                    "VALUES (:id, :chunk_id, CAST(:embedding AS vector), :model_name, NOW())"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "chunk_id": str(c.id),
                    "embedding": vec_literal,
                    "model_name": _MODEL_NAME,
                },
            )

    return version


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def sync_external_link_async(link_id: str) -> None:
    """Main sync entry point called by the RQ worker."""
    link_uuid = uuid.UUID(link_id)

    async with AsyncSessionLocal() as session:
        link = await session.get(ScreenExternalLink, link_uuid)
        if link is None:
            return
        link.sync_status = "syncing"
        link.updated_at = datetime.now(UTC)
        await session.commit()

    try:
        async with AsyncSessionLocal() as session:
            link = await session.get(ScreenExternalLink, link_uuid)
            if link is None:
                return

            integration_type = "figma" if link.type == "figma_frame" else "backlog"
            integration = (
                await session.execute(
                    select(ExternalIntegration).where(
                        ExternalIntegration.project_id == link.project_id,
                        ExternalIntegration.type == integration_type,
                    )
                )
            ).scalar_one_or_none()

            if integration is None:
                raise RuntimeError(
                    f"No {integration_type} integration configured for project {link.project_id}"
                )

            if link.type == "figma_frame":
                artifact = await ingest_figma_artifact_async(session, link, integration.config)
                link.figma_artifact_id = artifact.id
                # Xoá tham chiếu cũ sang document pipeline nếu có
                link.document_id = None
                link.doc_version_id = None

            else:
                from app.clients.backlog import fetch_issue, fetch_issue_comments
                from app.clients.backlog_parser import backlog_issue_to_markdown

                issue = await fetch_issue(
                    integration.config["space_url"], integration.config["api_key"], link.external_id
                )
                comments = await fetch_issue_comments(
                    integration.config["space_url"], integration.config["api_key"], link.external_id
                )
                markdown = backlog_issue_to_markdown(issue, comments)

                document = await _resolve_target_document(session, link)
                link.document_id = document.id

                if link.doc_version_id:
                    old_v = await session.get(DocVersion, link.doc_version_id)
                    if old_v:
                        await _delete_existing_chunks(session, old_v.id)
                        await session.delete(old_v)
                        await session.flush()

                version = await _ingest_markdown(
                    session, document=document, source="backlog", markdown=markdown, link=link
                )
                link.doc_version_id = version.id

            link.sync_status = "synced"
            link.last_synced_at = datetime.now(UTC)
            link.error_message = None
            link.updated_at = datetime.now(UTC)
            await session.commit()

    except Exception as exc:
        async with AsyncSessionLocal() as session:
            link = await session.get(ScreenExternalLink, link_uuid)
            if link:
                link.sync_status = "failed"
                link.error_message = str(exc)[:1000]
                link.updated_at = datetime.now(UTC)
                await session.commit()
        raise
