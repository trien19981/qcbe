from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, AsyncGenerator

logger = logging.getLogger(__name__)

# Matches *term* or **term** — user-marked emphasis for weighted retrieval
_EMPHASIS_RE = re.compile(r'\*{1,2}(.+?)\*{1,2}')


def _parse_emphasized(query: str) -> tuple[str, list[str]]:
    """Extract emphasized terms from *term* or **term** syntax.

    Returns (clean_query, emphasized_terms) where clean_query has the
    asterisks stripped and emphasized_terms is a list of the marked phrases.

    Example:
      "*Card trắng* có *kích thước* là bao nhiêu?"
      → ("Card trắng có kích thước là bao nhiêu?", ["Card trắng", "kích thước"])
    """
    emphasized = [m.group(1).strip() for m in _EMPHASIS_RE.finditer(query)]
    clean = _EMPHASIS_RE.sub(lambda m: m.group(1), query).strip()
    return clean, emphasized

import httpx
from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy import column, func, select, table, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.deps import get_current_user
from app.exceptions import ApiError
from app.models.user import User
from app.project_access import is_system_admin, project_member_role, require_project_access
from app.redis_client import get_redis
from app.services import ai_prompts as ai_prompt_svc
from app.schemas.chat import (
    ChatUserBrief,
    ConversationMessagesResponse,
    ConversationOut,
    ConversationsListResponse,
    ConversationScope,
    CreateConversationBody,
    CreateConversationResponse,
    DeleteConversationResponse,
    MessageOut,
    SendMessageBody,
    SendMessageResponse,
    SuggestedQuestionsResponse,
    CitationOut,
)
from app.schemas.project import PaginationMeta

router = APIRouter()

_convs = table(
    "chat_conversations",
    column("id"),
    column("project_id"),
    column("created_by"),
    column("title"),
    column("scope_type"),
    column("scope_config"),
    column("created_at"),
    column("updated_at"),
)
_msgs = table(
    "chat_messages",
    column("id"),
    column("conversation_id"),
    column("role"),
    column("content"),
    column("created_at"),
)
_cits = table(
    "chat_citations",
    column("id"),
    column("message_id"),
    column("chunk_id"),
    column("citation_index"),
    column("badge_text"),
    column("doc_type"),
    column("screen_name"),
    column("section_name"),
    column("preview_text"),
    column("similarity_score"),
)
_suggested = table(
    "chat_suggested_questions",
    column("id"),
    column("conversation_id"),
    column("question"),
    column("display_order"),
    column("created_at"),
)

_users = table("users", column("id"), column("full_name"))

_documents = table("documents", column("id"), column("project_id"), column("screen_name"), column("doc_type"))
_doc_versions = table("doc_versions", column("id"), column("document_id"), column("status"), column("version_no"))
_chunks = table("chunks", column("id"), column("doc_version_id"), column("content_text"), column("metadata"))
_emb = table("chunk_embeddings", column("chunk_id"), column("embedding"), column("model_name"))


async def _rate_limit_minute(redis, key: str, limit: int) -> None:
    bucket = int(time.time() // 60)
    rkey = f"{key}:{bucket}"
    try:
        n = await redis.incr(rkey)
        if n == 1:
            await redis.expire(rkey, 120)
    except RedisError as exc:
        raise ApiError(503, "REDIS_UNAVAILABLE", "Không kết nối được Redis.") from exc
    if n > limit:
        raise ApiError(429, "TOO_MANY_REQUESTS", "Quá nhiều yêu cầu. Vui lòng thử lại sau.")


def _scope_from_row(scope_type: str, scope_config: dict | None) -> ConversationScope:
    cfg = scope_config if isinstance(scope_config, dict) else {}
    return ConversationScope(
        type=scope_type,
        screen_name=cfg.get("screen_name"),
        doc_types=cfg.get("doc_types"),
    )


async def _load_user_brief(session: AsyncSession, user_id: uuid.UUID) -> ChatUserBrief:
    r = await session.execute(select(_users.c.full_name).where(_users.c.id == user_id))
    name = r.scalar_one_or_none() or ""
    return ChatUserBrief(id=user_id, full_name=name)


async def _conv_or_404(session: AsyncSession, conv_id: uuid.UUID) -> dict:
    r = await session.execute(select(_convs).where(_convs.c.id == conv_id))
    row = r.mappings().first()
    if not row:
        raise ApiError(404, "NOT_FOUND", "Conversation không tồn tại")
    return dict(row)


async def _require_conv_access(session: AsyncSession, user: User, conv: dict) -> None:
    project_id = uuid.UUID(str(conv["project_id"]))
    await require_project_access(session, user, project_id)
    if is_system_admin(user):
        return
    owner_id = uuid.UUID(str(conv["created_by"]))
    if owner_id != user.id:
        raise ApiError(403, "FORBIDDEN", "Không có quyền")


async def _embed_query(text_q: str) -> list[float]:
    if not settings.embedding_service_url:
        raise ApiError(503, "EMBEDDING_NOT_CONFIGURED", "Chưa cấu hình EMBEDDING_SERVICE_URL.")
    url = settings.embedding_service_url.rstrip("/") + "/embed/chunks"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.embedding_service_internal_key:
        headers["X-Internal-Key"] = settings.embedding_service_internal_key
    payload = {
        "chunks": [{"text": text_q}],
        "model_name_or_path": "BAAI/bge-m3",
        "normalize_embeddings": True,
        "use_fp16": True,
        "batch_size": 1,
    }
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
    if resp.status_code >= 400:
        raise ApiError(502, "EMBEDDING_FAILED", f"Embedding service error {resp.status_code}")
    data = resp.json()
    return data["embeddings"][0]["embedding"]


# L2 distance threshold for normalized BAAI/bge-m3 embeddings.
# L2=0.85 ↔ cosine≈0.64 — requires meaningful semantic similarity.
# Was 1.0 (cosine≈0.5, borderline); tightened to reduce vector arm noise.
_DIST_THRESHOLD: float = 0.85
# Minimum ts_rank_cd for the FTS arm — filters keyword-only noise where the
# query terms appear only once or tangentially in a long document.
_MIN_FTS_RANK_SCORE: float = 0.01
# Absolute post-fusion RRF score floor applied in Python after retrieval.
# Score 0.015 ≈ "ranked in top-6 of at least one arm" (1/(60+6)=0.0152).
# Chunks scoring below this are dropped before being sent to Claude.
_MIN_RRF_SCORE: float = 0.015
# Candidate pool size per search arm fed into RRF fusion.
_CANDIDATE_K: int = 20
# RRF constant — controls how steeply rank penalises lower positions.
_RRF_K: int = 60


async def _retrieve_chunks(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    scope_type: str,
    scope_config: dict,
    query_vec: list[float],
    query_text: str = "",
    fts_text: str = "",
    top_k: int = 8,
    dist_threshold: float = _DIST_THRESHOLD,
    min_fts_rank_score: float = _MIN_FTS_RANK_SCORE,
    min_rrf_score: float = _MIN_RRF_SCORE,
) -> list[dict]:
    """Hybrid retrieval: pgvector L2 + PostgreSQL full-text search fused with RRF.

    Three-layer relevance filtering:
      1. Vector arm: dist_threshold (L2 < 0.85 → cosine > 0.64)
      2. FTS arm: min_fts_rank_score (ts_rank_cd floor to filter keyword noise)
      3. Python post-filter: min_rrf_score drops low-relevance chunks after fusion

    fts_text: when provided (e.g. user-emphasized terms), the FTS arm uses it
    instead of query_text so keyword matching focuses on the important terms.
    """
    allowed_version_status = ("approved", "ready_for_review")
    doc_types = scope_config.get("doc_types") if isinstance(scope_config.get("doc_types"), list) else None
    screen_name = scope_config.get("screen_name") if isinstance(scope_config.get("screen_name"), str) else None

    vec_literal = "[" + ",".join(str(float(x)) for x in query_vec) + "]"

    # Scope predicates shared across both arms (minus model_name / embedding columns).
    scope_extra_vec: list[str] = []
    scope_extra_fts: list[str] = []
    params: dict = {
        "pid": str(project_id),
        "vstatuses": list(allowed_version_status),
        "model_name": "BAAI/bge-m3",
        "qvec": vec_literal,
        "k": int(top_k),
        "ck": _CANDIDATE_K,
        "dist_threshold": float(dist_threshold),
        "min_fts_rank_score": float(min_fts_rank_score),
    }
    if scope_type == "screen" and screen_name:
        scope_extra_vec.append("d.screen_name = :screen_name")
        scope_extra_fts.append("d.screen_name = :screen_name")
        params["screen_name"] = screen_name
    if scope_type == "doc_type" and doc_types:
        scope_extra_vec.append("d.doc_type = ANY(:doc_types)")
        scope_extra_fts.append("d.doc_type = ANY(:doc_types)")
        params["doc_types"] = doc_types

    vec_where = " AND ".join([
        "d.project_id = :pid",
        "dv.status = ANY(:vstatuses)",
        "ce.model_name = :model_name",
        "(ce.embedding <-> CAST(:qvec AS vector)) < :dist_threshold",
        *scope_extra_vec,
    ])
    fts_where = " AND ".join([
        "d.project_id = :pid",
        "dv.status = ANY(:vstatuses)",
        *scope_extra_fts,
    ])

    clean_query = (query_text or "").strip()
    # Use explicit fts_text (emphasized terms) when provided, else fall back to full query.
    clean_fts = (fts_text or "").strip() or clean_query
    use_fts = bool(clean_fts)

    if use_fts:
        params["query_text"] = clean_fts
        sql = f"""
          WITH
          vr AS (
            SELECT
              c.id                                              AS chunk_id,
              ROW_NUMBER() OVER (
                ORDER BY ce.embedding <-> CAST(:qvec AS vector)
              )                                                AS rank_v,
              (ce.embedding <-> CAST(:qvec AS vector))         AS distance
            FROM chunk_embeddings ce
            JOIN chunks      c  ON c.id  = ce.chunk_id
            JOIN doc_versions dv ON dv.id = c.doc_version_id
            JOIN documents    d  ON d.id  = dv.document_id
            WHERE {vec_where}
            ORDER BY ce.embedding <-> CAST(:qvec AS vector)
            LIMIT :ck
          ),
          fr AS (
            SELECT
              c.id  AS chunk_id,
              ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(
                  to_tsvector('simple', c.content_text),
                  websearch_to_tsquery('simple', :query_text)
                ) DESC
              ) AS rank_f
            FROM chunks      c
            JOIN doc_versions dv ON dv.id = c.doc_version_id
            JOIN documents    d  ON d.id  = dv.document_id
            WHERE {fts_where}
              AND to_tsvector('simple', c.content_text)
                  @@ websearch_to_tsquery('simple', :query_text)
              AND ts_rank_cd(
                    to_tsvector('simple', c.content_text),
                    websearch_to_tsquery('simple', :query_text)
                  ) >= :min_fts_rank_score
            LIMIT :ck
          ),
          merged AS (
            SELECT
              COALESCE(vr.chunk_id, fr.chunk_id)                          AS chunk_id,
              COALESCE(1.0 / ({_RRF_K}.0 + vr.rank_v::float), 0.0)
              + COALESCE(1.0 / ({_RRF_K}.0 + fr.rank_f::float), 0.0)     AS rrf_score,
              COALESCE(vr.distance, 1.5)                                   AS distance
            FROM vr
            FULL OUTER JOIN fr ON vr.chunk_id = fr.chunk_id
          )
          SELECT
            m.chunk_id,
            m.rrf_score  AS score,
            m.distance,
            c.content_text,
            c.metadata,
            d.id          AS document_id,
            dv.id         AS version_id
          FROM merged m
          JOIN chunks      c  ON c.id  = m.chunk_id
          JOIN doc_versions dv ON dv.id = c.doc_version_id
          JOIN documents    d  ON d.id  = dv.document_id
          ORDER BY m.rrf_score DESC
          LIMIT :k
        """
    else:
        # Pure vector search with distance threshold.
        sql = f"""
          SELECT
            c.id                                              AS chunk_id,
            1.0 / ({_RRF_K}.0 + ROW_NUMBER() OVER (
              ORDER BY ce.embedding <-> CAST(:qvec AS vector)
            )::float)                                        AS score,
            (ce.embedding <-> CAST(:qvec AS vector))         AS distance,
            c.content_text,
            c.metadata,
            d.id  AS document_id,
            dv.id AS version_id
          FROM chunk_embeddings ce
          JOIN chunks      c  ON c.id  = ce.chunk_id
          JOIN doc_versions dv ON dv.id = c.doc_version_id
          JOIN documents    d  ON d.id  = dv.document_id
          WHERE {vec_where}
          ORDER BY ce.embedding <-> CAST(:qvec AS vector)
          LIMIT :k
        """

    r = await session.execute(text(sql), params)
    out = []
    for row in r.mappings().all():
        meta = row["metadata"] if isinstance(row["metadata"], dict) else {}
        out.append({
            "chunk_id":    uuid.UUID(str(row["chunk_id"])) if row["chunk_id"] else None,
            "content_text": row["content_text"] or "",
            "metadata":    meta,
            "document_id": uuid.UUID(str(row["document_id"])) if row["document_id"] else None,
            "version_id":  uuid.UUID(str(row["version_id"])) if row["version_id"] else None,
            "score":       float(row["score"] or 0.0),
        })

    # Post-fusion relevance filter: drop chunks whose absolute RRF score is below
    # the floor. Chunks are already sorted DESC by score from SQL, so the first
    # item that drops below the floor means all subsequent ones do too.
    before = len(out)
    out = [c for c in out if c["score"] >= min_rrf_score]
    after = len(out)
    if before != after:
        logger.debug(
            "[RETRIEVAL] post-filter dropped %d/%d low-score chunks "
            "(min_rrf_score=%.4f, kept=%d)",
            before - after, before, min_rrf_score, after,
        )
    else:
        logger.debug(
            "[RETRIEVAL] %d chunks passed all filters (min_rrf_score=%.4f)",
            after, min_rrf_score,
        )
    return out


def _make_badge(doc_type: str | None, screen: str | None, section: str | None) -> str:
    dt = doc_type or "doc"
    sc = screen or "—"
    sec = section or "—"
    return f"[{dt} · {sc} · §{sec}]"


async def _claude_answer(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    question: str,
    context_chunks: list[dict],
    history: list[dict] | None = None,
) -> tuple[str, list[CitationOut]]:
    if not settings.anthropic_api_key:
        raise ApiError(503, "CLAUDE_UNAVAILABLE", "Claude API không khả dụng (thiếu ANTHROPIC_API_KEY).")
    try:
        from anthropic import AsyncAnthropic  # type: ignore[import-untyped]
    except Exception as exc:
        raise ApiError(503, "CLAUDE_UNAVAILABLE", "Claude SDK (anthropic) chưa được cài trong môi trường API.") from exc

    # Build context with inline citation anchors CITATION_i.
    ctx_lines: list[str] = []
    citations: list[CitationOut] = []
    for i, c in enumerate(context_chunks):
        meta = c.get("metadata") or {}
        doc_type = str(meta.get("doc_type") or meta.get("docType") or "")
        screen = str(meta.get("screen_name") or meta.get("screen") or "")
        section = None
        if isinstance(meta.get("section_path"), list) and meta.get("section_path"):
            section = str(meta["section_path"][-1])
        section = section or str(meta.get("section") or "")
        ver_no = c.get("version_no")
        ver_st = c.get("version_status", "")
        if ver_no is not None:
            if ver_st == "approved":
                version_suffix = f" · v{ver_no} approved"
                version_label = f" [v{ver_no} · approved ✓]"
            elif ver_st == "ready_for_review":
                version_suffix = f" · v{ver_no} review"
                version_label = f" [v{ver_no} · đang review]"
            else:
                version_suffix = f" · v{ver_no}"
                version_label = f" [v{ver_no}]"
        else:
            version_suffix = ""
            version_label = ""

        badge = _make_badge(doc_type or None, screen or None, section or None)
        badge_with_version = badge.rstrip("]") + version_suffix + "]" if version_suffix else badge
        preview = " ".join(str(c.get("content_text") or "").replace("\n", " ").split())[:80]
        citations.append(
            CitationOut(
                index=i,
                chunk_id=c.get("chunk_id"),
                badge_text=badge_with_version,
                doc_type=doc_type or None,
                screen=screen or None,
                section=section or None,
                document_id=c.get("document_id"),
                version_id=c.get("version_id"),
                version_no=ver_no,
                version_status=ver_st or None,
                preview=preview,
                similarity_score=float(c.get("score") or 0.0),
            )
        )
        ctx_lines.append(f"[CITATION_{i}] {badge}{version_label}\n{c.get('content_text')}\n")

    system = await ai_prompt_svc.get_ai_prompt(
        session,
        project_id,
        ai_prompt_svc.QA_ANSWER_SYSTEM,
        ai_prompt_svc.DEFAULT_QA_ANSWER_SYSTEM,
    )

    # Current turn: CONTEXT + câu hỏi mới.
    current_prompt = (
        "CONTEXT:\n"
        + "\n".join(ctx_lines)
        + "\nQUESTION:\n"
        + question
        + "\n\nYêu cầu: trả lời ngắn gọn, có trích dẫn CITATION_i ở câu liên quan."
    )

    # Build messages: lịch sử hội thoại (raw) + current turn (có context).
    # Lịch sử không chứa CONTEXT — chỉ câu hỏi và câu trả lời gốc.
    messages_payload: list[dict] = []
    for m in (history or []):
        role = m.get("role", "")
        content = m.get("content", "")
        if role in ("user", "assistant") and content:
            messages_payload.append({"role": role, "content": content})
    messages_payload.append({"role": "user", "content": current_prompt})

    history_count = len(messages_payload) - 1  # không kể current turn
    logger.debug(
        "\n"
        "╔══════════════════════════════════════════════════════╗\n"
        "║  [CLAUDE PROMPT]  STEP 2 — Q&A ANSWER               ║\n"
        "╚══════════════════════════════════════════════════════╝\n"
        "  model          : claude-sonnet-4-20250514\n"
        "  max_tokens     : 1000\n"
        "  context_chunks : %d\n"
        "  history_turns  : %d messages trước\n"
        "\n── SYSTEM ──────────────────────────────────────────────\n"
        "%s\n"
        "\n── HISTORY (%d messages) ────────────────────────────────\n"
        "%s\n"
        "\n── CURRENT USER TURN ───────────────────────────────────\n"
        "%s\n"
        "════════════════════════════════════════════════════════",
        len(context_chunks),
        history_count,
        system,
        history_count,
        json.dumps(messages_payload[:-1], ensure_ascii=False, indent=2) if history_count else "(no history)",
        current_prompt,
    )

    client_kwargs: dict = {"api_key": settings.anthropic_api_key}
    if settings.anthropic_base_url:
        client_kwargs["base_url"] = settings.anthropic_base_url
    client = AsyncAnthropic(**client_kwargs)
    resp = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=system,
        messages=messages_payload,
    )
    text_out = ""
    for b in resp.content:
        if getattr(b, "type", None) == "text":
            text_out += b.text
    logger.debug(
        "[CLAUDE RESPONSE] STEP 2 — Q&A ANSWER: %d chars "
        "(input_tokens=%s, output_tokens=%s)",
        len(text_out),
        getattr(resp.usage, "input_tokens", "?"),
        getattr(resp.usage, "output_tokens", "?"),
    )
    return text_out.strip(), citations


@router.get("/projects/{project_id}/chat/conversations", response_model=ConversationsListResponse)
async def list_conversations(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=50)] = 20,
    user_id: Annotated[uuid.UUID | None, Query()] = None,
) -> ConversationsListResponse:
    try:
        redis = get_redis()
    except Exception as exc:
        raise ApiError(503, "REDIS_NOT_CONFIGURED", "Chưa cấu hình REDIS_URL hợp lệ.") from exc
    await _rate_limit_minute(redis, f"rl:chat:convs:{user.id}", 60)

    await require_project_access(session, user, project_id)
    if user_id is not None and not is_system_admin(user):
        raise ApiError(403, "FORBIDDEN", "Chỉ admin được filter user_id")
    target_user_id = user_id if user_id is not None else user.id

    total = int(
        (
            await session.execute(
                select(func.count()).select_from(_convs).where(_convs.c.project_id == project_id, _convs.c.created_by == target_user_id)
            )
        ).scalar_one()
    )
    offset = (page - 1) * per_page

    # list conversations + counts
    r = await session.execute(
        select(
            _convs.c.id,
            _convs.c.title,
            _convs.c.scope_type,
            _convs.c.scope_config,
            _convs.c.created_at,
            _convs.c.created_by,
            func.count(_msgs.c.id).label("message_count"),
            func.max(_msgs.c.created_at).label("last_message_at"),
        )
        .select_from(_convs.outerjoin(_msgs, _msgs.c.conversation_id == _convs.c.id))
        .where(_convs.c.project_id == project_id, _convs.c.created_by == target_user_id)
        .group_by(_convs.c.id)
        .order_by(func.max(_msgs.c.created_at).desc().nullslast(), _convs.c.created_at.desc().nullslast())
        .limit(per_page)
        .offset(offset)
    )
    items = []
    for row in r.all():
        created_by_brief = await _load_user_brief(session, uuid.UUID(str(row.created_by)))
        items.append(
            {
                "id": row.id,
                "title": row.title,
                "scope": _scope_from_row(str(row.scope_type), row.scope_config),
                "message_count": int(row.message_count or 0),
                "last_message_at": row.last_message_at,
                "created_at": row.created_at,
                "created_by": created_by_brief,
            }
        )
    return ConversationsListResponse(
        conversations=items,
        pagination=PaginationMeta(
            total=total,
            page=page,
            per_page=per_page,
            total_pages=int((total + per_page - 1) / per_page) if per_page else 1,
        ),
    )


@router.post(
    "/projects/{project_id}/chat/conversations",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateConversationResponse,
)
async def create_conversation(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
    body: CreateConversationBody,
) -> CreateConversationResponse:
    try:
        redis = get_redis()
    except Exception as exc:
        raise ApiError(503, "REDIS_NOT_CONFIGURED", "Chưa cấu hình REDIS_URL hợp lệ.") from exc
    await _rate_limit_minute(redis, f"rl:chat:convcreate:{user.id}", 20)

    await require_project_access(session, user, project_id)

    scope_type = (body.scope_type or "").strip()
    if scope_type not in {"project", "screen", "doc_type"}:
        raise ApiError(422, "VALIDATION_ERROR", "scope_type không hợp lệ")
    scope_config: dict = {}
    if scope_type == "screen":
        if not body.screen_name:
            raise ApiError(400, "BAD_REQUEST", "Thiếu screen_name")
        scope_config["screen_name"] = body.screen_name
    if scope_type == "doc_type":
        scope_config["doc_types"] = body.doc_types or []

    conv_id = uuid.uuid4()
    try:
        await session.execute(
            text(
                """
                INSERT INTO chat_conversations (id, project_id, created_by, title, scope_type, scope_config, created_at, updated_at)
                VALUES (:id, :pid, :uid, NULL, :scope_type, CAST(:scope_config AS jsonb), NOW(), NOW())
                """
            ),
            {
                "id": str(conv_id),
                "pid": str(project_id),
                "uid": str(user.id),
                "scope_type": scope_type,
                "scope_config": json.dumps(scope_config),
            },
        )
        await session.commit()
    except SQLAlchemyError as exc:
        await session.rollback()
        detail = str(getattr(exc, "orig", exc))
        # Keep it short-ish for API responses.
        if len(detail) > 280:
            detail = detail[:280] + "…"
        raise ApiError(
            500,
            "CHAT_SCHEMA_ERROR",
            "Không tạo được conversation. "
            "Kiểm tra DB đã chạy migration `document/sql/005_chat_qa.sql` và kết nối database. "
            f"Detail: {exc.__class__.__name__}: {detail}",
        ) from exc

    # has_approved_documents: COUNT(*) — avoids zero-vector distance math issue.
    has_chunks = False
    try:
        count_where = " AND ".join([
            "d.project_id = :pid",
            "dv.status = ANY(:vstatuses)",
            "ce.model_name = :model_name",
        ])
        count_params: dict = {
            "pid": str(project_id),
            "vstatuses": ["approved", "ready_for_review"],
            "model_name": "BAAI/bge-m3",
        }
        if scope_type == "screen" and isinstance(scope_config.get("screen_name"), str):
            count_where += " AND d.screen_name = :screen_name"
            count_params["screen_name"] = scope_config["screen_name"]
        elif scope_type == "doc_type" and isinstance(scope_config.get("doc_types"), list):
            count_where += " AND d.doc_type = ANY(:doc_types)"
            count_params["doc_types"] = scope_config["doc_types"]
        count_sql = f"""
            SELECT COUNT(*) FROM chunk_embeddings ce
            JOIN chunks      c  ON c.id  = ce.chunk_id
            JOIN doc_versions dv ON dv.id = c.doc_version_id
            JOIN documents    d  ON d.id  = dv.document_id
            WHERE {count_where}
        """
        n = (await session.execute(text(count_sql), count_params)).scalar_one()
        has_chunks = int(n) > 0
    except Exception:
        has_chunks = False

    # Suggested questions: generate async using a fresh DB session to avoid
    # using the request-scoped session after it has been closed.
    questions: list[str] = []
    if settings.anthropic_api_key and has_chunks:
        from app.database import AsyncSessionLocal  # local import to avoid circular

        _snap_project_id = project_id
        _snap_scope_type = scope_type
        _snap_scope_config = dict(scope_config)
        _snap_conv_id = conv_id

        async def _gen() -> None:
            try:
                from anthropic import AsyncAnthropic  # type: ignore[import-untyped]
            except Exception:
                return
            try:
                async with AsyncSessionLocal() as bg_session:
                    # Random sample chunks as seed context — ORDER BY RANDOM() LIMIT 3
                    seed_where = " AND ".join([
                        "d.project_id = :pid",
                        "dv.status = ANY(:vstatuses)",
                    ])
                    seed_params: dict = {
                        "pid": str(_snap_project_id),
                        "vstatuses": ["approved", "ready_for_review"],
                    }
                    if _snap_scope_type == "screen" and isinstance(_snap_scope_config.get("screen_name"), str):
                        seed_where += " AND d.screen_name = :screen_name"
                        seed_params["screen_name"] = _snap_scope_config["screen_name"]
                    elif _snap_scope_type == "doc_type" and isinstance(_snap_scope_config.get("doc_types"), list):
                        seed_where += " AND d.doc_type = ANY(:doc_types)"
                        seed_params["doc_types"] = _snap_scope_config["doc_types"]
                    seed_sql = f"""
                        SELECT c.content_text FROM chunks c
                        JOIN doc_versions dv ON dv.id = c.doc_version_id
                        JOIN documents    d  ON d.id  = dv.document_id
                        WHERE {seed_where}
                        ORDER BY RANDOM() LIMIT 3
                    """
                    seed_rows = (await bg_session.execute(text(seed_sql), seed_params)).all()
                    if not seed_rows:
                        return
                    ctx = "\n\n".join((r[0] or "")[:800] for r in seed_rows)
                    client_kwargs: dict = {"api_key": settings.anthropic_api_key}
                    if settings.anthropic_base_url:
                        client_kwargs["base_url"] = settings.anthropic_base_url
                    tmpl = await ai_prompt_svc.get_ai_prompt(
                        bg_session,
                        uuid.UUID(str(_snap_project_id)),
                        ai_prompt_svc.QA_SUGGESTED_QUESTIONS_USER,
                        ai_prompt_svc.DEFAULT_QA_SUGGESTED_QUESTIONS_USER,
                    )
                    if "{context}" in tmpl:
                        gen_user_content = ai_prompt_svc.inject_context(tmpl, ctx)
                    else:
                        gen_user_content = tmpl.rstrip() + "\n\n---\n" + ctx + "\n---"
                    logger.debug(
                        "\n"
                        "╔══════════════════════════════════════════════════════╗\n"
                        "║  [CLAUDE PROMPT]  STEP 3 — SUGGESTED QUESTIONS      ║\n"
                        "╚══════════════════════════════════════════════════════╝\n"
                        "  model      : claude-sonnet-4-20250514\n"
                        "  max_tokens : 300\n"
                        "  scope_type : %s  scope_config : %s\n"
                        "  seed_chunks: %d đoạn\n"
                        "\n── USER PROMPT ─────────────────────────────────────────\n"
                        "%s\n"
                        "════════════════════════════════════════════════════════",
                        _snap_scope_type,
                        json.dumps(_snap_scope_config, ensure_ascii=False),
                        len(seed_rows),
                        gen_user_content,
                    )
                    client = AsyncAnthropic(**client_kwargs)
                    resp = await client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=300,
                        messages=[{"role": "user", "content": gen_user_content}],
                    )
                    txt = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
                    qs = [q.strip("-• \t0123456789.") for q in txt.splitlines() if q.strip()]
                    qs = [q for q in qs if q][:4]
                    logger.debug(
                        "[CLAUDE RESPONSE] STEP 3 — SUGGESTED QUESTIONS: %s "
                        "(input_tokens=%s, output_tokens=%s)",
                        qs,
                        getattr(resp.usage, "input_tokens", "?"),
                        getattr(resp.usage, "output_tokens", "?"),
                    )
                    if qs:
                        await bg_session.execute(
                            text("DELETE FROM chat_suggested_questions WHERE conversation_id = :cid"),
                            {"cid": str(_snap_conv_id)},
                        )
                        for i, q in enumerate(qs):
                            await bg_session.execute(
                                text(
                                    """
                                    INSERT INTO chat_suggested_questions (id, conversation_id, question, display_order, created_at)
                                    VALUES (:id, :cid, :q, :ord, NOW())
                                    """
                                ),
                                {"id": str(uuid.uuid4()), "cid": str(_snap_conv_id), "q": q, "ord": i},
                            )
                        await bg_session.commit()
            except Exception:
                return

        asyncio.create_task(_gen())

    return CreateConversationResponse(
        id=conv_id,
        title=None,
        scope=_scope_from_row(scope_type, scope_config),
        suggested_questions=questions,
        has_approved_documents=has_chunks,
        message_count=0,
        created_at=datetime.now(UTC),
    )


@router.get("/chat/conversations/{conversation_id}/messages", response_model=ConversationMessagesResponse)
async def get_conversation_messages(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    conversation_id: uuid.UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ConversationMessagesResponse:
    try:
        redis = get_redis()
    except Exception as exc:
        raise ApiError(503, "REDIS_NOT_CONFIGURED", "Chưa cấu hình REDIS_URL hợp lệ.") from exc
    await _rate_limit_minute(redis, f"rl:chat:msgs:{user.id}", 60)

    conv = await _conv_or_404(session, conversation_id)
    await _require_conv_access(session, user, conv)

    total = int(
        (
            await session.execute(
                select(func.count()).select_from(_msgs).where(_msgs.c.conversation_id == conversation_id)
            )
        ).scalar_one()
    )
    offset = (page - 1) * per_page
    r = await session.execute(
        select(_msgs.c.id, _msgs.c.role, _msgs.c.content, _msgs.c.created_at)
        .where(_msgs.c.conversation_id == conversation_id)
        .order_by(_msgs.c.created_at.asc())
        .limit(per_page)
        .offset(offset)
    )
    msg_rows = r.all()
    msg_ids = [m.id for m in msg_rows]
    cits_map: dict[uuid.UUID, list[CitationOut]] = {uuid.UUID(str(mid)): [] for mid in msg_ids}
    if msg_ids:
        cr = await session.execute(
            select(
                _cits.c.message_id,
                _cits.c.citation_index,
                _cits.c.chunk_id,
                _cits.c.badge_text,
                _cits.c.doc_type,
                _cits.c.screen_name,
                _cits.c.section_name,
                _cits.c.preview_text,
                _cits.c.similarity_score,
                _doc_versions.c.id.label("cited_version_id"),
                _doc_versions.c.document_id.label("cited_document_id"),
            )
            .select_from(
                _cits.outerjoin(_chunks, _cits.c.chunk_id == _chunks.c.id).outerjoin(
                    _doc_versions, _chunks.c.doc_version_id == _doc_versions.c.id
                )
            )
            .where(_cits.c.message_id.in_(msg_ids))
            .order_by(_cits.c.message_id, _cits.c.citation_index.asc())
        )
        for c in cr.all():
            cited_doc = c.cited_document_id
            cited_ver = c.cited_version_id
            cits_map[uuid.UUID(str(c.message_id))].append(
                CitationOut(
                    index=int(c.citation_index),
                    chunk_id=c.chunk_id,
                    badge_text=c.badge_text,
                    doc_type=c.doc_type,
                    screen=c.screen_name,
                    section=c.section_name,
                    preview=c.preview_text,
                    similarity_score=float(c.similarity_score) if c.similarity_score is not None else None,
                    document_id=uuid.UUID(str(cited_doc)) if cited_doc is not None else None,
                    version_id=uuid.UUID(str(cited_ver)) if cited_ver is not None else None,
                )
            )
    messages = [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            citations=cits_map.get(uuid.UUID(str(m.id)), []),
            created_at=m.created_at,
        )
        for m in msg_rows
    ]

    scope = _scope_from_row(str(conv["scope_type"]), conv.get("scope_config"))
    return ConversationMessagesResponse(
        conversation=ConversationOut(
            id=uuid.UUID(str(conv["id"])),
            title=conv.get("title"),
            scope=scope,
            created_at=conv.get("created_at"),
        ),
        messages=messages,
        pagination=PaginationMeta(
            total=total,
            page=page,
            per_page=per_page,
            total_pages=int((total + per_page - 1) / per_page) if per_page else 1,
        ),
    )


@router.delete("/chat/conversations/{conversation_id}", response_model=DeleteConversationResponse)
async def delete_conversation(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    conversation_id: uuid.UUID,
) -> DeleteConversationResponse:
    try:
        redis = get_redis()
    except Exception as exc:
        raise ApiError(503, "REDIS_NOT_CONFIGURED", "Chưa cấu hình REDIS_URL hợp lệ.") from exc
    await _rate_limit_minute(redis, f"rl:chat:convdel:{user.id}", 20)

    conv = await _conv_or_404(session, conversation_id)
    project_id = uuid.UUID(str(conv["project_id"]))
    await require_project_access(session, user, project_id)
    owner_id = uuid.UUID(str(conv["created_by"]))
    if not (is_system_admin(user) or owner_id == user.id):
        raise ApiError(403, "FORBIDDEN", "Không có quyền")

    deleted = int(
        (
            await session.execute(select(func.count()).select_from(_msgs).where(_msgs.c.conversation_id == conversation_id))
        ).scalar_one()
    )
    await session.execute(text("DELETE FROM chat_conversations WHERE id = :cid"), {"cid": str(conversation_id)})
    await session.commit()
    return DeleteConversationResponse(
        message="Đã xoá conversation",
        conversation_id=conversation_id,
        deleted_messages=deleted,
    )


@router.get("/chat/conversations/{conversation_id}/suggested-questions", response_model=SuggestedQuestionsResponse)
async def get_suggested_questions(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    conversation_id: uuid.UUID,
) -> SuggestedQuestionsResponse:
    try:
        redis = get_redis()
    except Exception as exc:
        raise ApiError(503, "REDIS_NOT_CONFIGURED", "Chưa cấu hình REDIS_URL hợp lệ.") from exc
    await _rate_limit_minute(redis, f"rl:chat:suggest:{user.id}", 30)

    conv = await _conv_or_404(session, conversation_id)
    await _require_conv_access(session, user, conv)

    r = await session.execute(
        select(_suggested.c.question, _suggested.c.created_at)
        .where(_suggested.c.conversation_id == conversation_id)
        .order_by(_suggested.c.display_order.asc())
    )
    rows = r.all()
    qs = [row.question for row in rows]
    generated_at = rows[0][1] if rows else None
    scope = _scope_from_row(str(conv["scope_type"]), conv.get("scope_config"))
    label = "Toàn project" if scope.type == "project" else (f"Màn hình {scope.screen_name}" if scope.type == "screen" else "Loại tài liệu")
    return SuggestedQuestionsResponse(
        conversation_id=conversation_id,
        scope_label=label,
        questions=qs,
        generated_at=generated_at,
    )


@router.post("/chat/conversations/{conversation_id}/messages", response_model=SendMessageResponse)
async def send_message(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    conversation_id: Annotated[uuid.UUID, Path(...)],
    body: SendMessageBody,
) -> SendMessageResponse | StreamingResponse:
    try:
        redis = get_redis()
    except Exception as exc:
        raise ApiError(503, "REDIS_NOT_CONFIGURED", "Chưa cấu hình REDIS_URL hợp lệ.") from exc
    await _rate_limit_minute(redis, f"rl:chat:send:{user.id}", 30)

    conv = await _conv_or_404(session, conversation_id)
    await _require_conv_access(session, user, conv)

    scope_type = str(conv["scope_type"])
    scope_config = conv.get("scope_config") if isinstance(conv.get("scope_config"), dict) else {}
    project_id = uuid.UUID(str(conv["project_id"]))

    # Load history BEFORE saving the user message so the current question is
    # not included — prevents sending the same question twice to Claude.
    history_rows = await session.execute(
        select(_msgs.c.role, _msgs.c.content)
        .where(_msgs.c.conversation_id == conversation_id)
        .order_by(_msgs.c.created_at.desc())
        .limit(6)
    )
    recent_history = list(reversed([
        {"role": str(r.role), "content": str(r.content)}
        for r in history_rows.all()
    ]))

    # Save user message
    user_msg_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO chat_messages (id, conversation_id, role, content, created_at)
            VALUES (:id, :cid, 'user', :content, NOW())
            """
        ),
        {"id": str(user_msg_id), "cid": str(conversation_id), "content": body.content},
    )
    await session.commit()

    # Parse emphasis markers (*term* / **term**) from the user's message.
    # clean_content has asterisks stripped; emphasized contains the marked phrases.
    clean_content, emphasized = _parse_emphasized(body.content)

    # Build contextual retrieval query: current question + last 2 user turns for
    # follow-up awareness (e.g. "cái đó là gì?" → "cái đó" refers to prior context).
    prior_user_ctx = " ".join(
        m["content"] for m in recent_history[-4:] if m["role"] == "user"
    )

    # Vector embedding: use clean content as-is — bge-m3 is a contextual model,
    # repetition distorts rather than boosts the embedding vector.
    retrieval_query = (clean_content + " " + prior_user_ctx).strip()[:600]

    # FTS query: emphasized terms joined with OR so the FTS arm boosts chunks that
    # contain ANY emphasized term (not ALL — AND would exclude chunks that use
    # English notation like "440px" instead of Vietnamese "kích thước").
    # No prior_user_ctx here — keeping FTS focused prevents false AND matches.
    if emphasized:
        fts_text = " OR ".join(f'"{t}"' if " " in t else t for t in emphasized)
    else:
        fts_text = ""

    # Retrieval: hybrid vector + FTS with RRF fusion.
    qvec = await _embed_query(retrieval_query)
    chunks = await _retrieve_chunks(
        session,
        project_id=project_id,
        scope_type=scope_type,
        scope_config=scope_config,
        query_vec=qvec,
        query_text=retrieval_query,
        fts_text=fts_text,
        top_k=8,
    )

    # Enrich each chunk with version_no and version_status so Claude can distinguish
    # approved vs. pending-review sources when formatting multi-version answers.
    if chunks:
        _ver_ids = list({str(c["version_id"]) for c in chunks if c.get("version_id")})
        if _ver_ids:
            _placeholders = ", ".join(f":_vid_{i}" for i in range(len(_ver_ids)))
            _ver_rows = (
                await session.execute(
                    text(f"SELECT id, version_no, status FROM doc_versions WHERE id::text IN ({_placeholders})"),
                    {f"_vid_{i}": v for i, v in enumerate(_ver_ids)},
                )
            ).all()
            _ver_map = {str(r.id): (int(r.version_no), str(r.status)) for r in _ver_rows}
            for c in chunks:
                _vid = str(c["version_id"]) if c.get("version_id") else None
                if _vid and _vid in _ver_map:
                    c["version_no"], c["version_status"] = _ver_map[_vid]

    async def _save_assistant(full_text: str, citations: list[CitationOut]) -> MessageOut:
        assistant_id = uuid.uuid4()
        await session.execute(
            text(
                """
                INSERT INTO chat_messages (id, conversation_id, role, content, created_at)
                VALUES (:id, :cid, 'assistant', :content, NOW())
                """
            ),
            {"id": str(assistant_id), "cid": str(conversation_id), "content": full_text},
        )
        # citations
        for c in citations:
            await session.execute(
                text(
                    """
                    INSERT INTO chat_citations
                      (id, message_id, chunk_id, citation_index, badge_text, doc_type, screen_name, section_name, preview_text, similarity_score)
                    VALUES
                      (:id, :mid, :chunk_id, :idx, :badge, :doc_type, :screen, :section, :preview, :score)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "mid": str(assistant_id),
                    "chunk_id": str(c.chunk_id) if c.chunk_id else None,
                    "idx": int(c.index),
                    "badge": c.badge_text,
                    "doc_type": c.doc_type,
                    "screen": c.screen,
                    "section": c.section,
                    "preview": c.preview,
                    "score": float(c.similarity_score) if c.similarity_score is not None else None,
                },
            )

        # set conversation title if null
        conv_title = conv.get("title")
        new_title = None
        if not conv_title:
            new_title = (body.content or "").strip()[:50]
            await session.execute(
                text("UPDATE chat_conversations SET title = :t, updated_at = NOW() WHERE id = :cid"),
                {"t": new_title, "cid": str(conversation_id)},
            )
        await session.commit()
        return MessageOut(
            id=assistant_id,
            role="assistant",
            content=full_text,
            citations=citations,
            created_at=datetime.now(UTC),
        )

    if not body.stream:
        answer, citations = await _claude_answer(
            session,
            project_id,
            question=clean_content,
            context_chunks=chunks,
            history=recent_history,
        )
        assistant = await _save_assistant(answer, citations)
        user_out = MessageOut(id=user_msg_id, role="user", content=body.content, citations=[], created_at=datetime.now(UTC))
        return SendMessageResponse(user_message=user_out, assistant_message=assistant, conversation_title=conv.get("title") or body.content[:50])

    async def event_gen() -> AsyncGenerator[str, None]:
        # First event: user message ack
        yield f"data: {json.dumps({'type': 'user_message', 'id': str(user_msg_id), 'created_at': datetime.now(UTC).isoformat()})}\n\n"
        # Stream answer from Claude (fallback to non-streaming if stream API not configured)
        full = ""
        citations: list[CitationOut] = []
        try:
            answer, citations = await _claude_answer(
                session,
                project_id,
                question=clean_content,
                context_chunks=chunks,
                history=recent_history,
            )
            # naive delta streaming: split by words (since we used create, not stream API)
            for w in answer.split(" "):
                full += ("" if not full else " ") + w
                yield f"data: {json.dumps({'type': 'delta', 'text': w + ' '})}\n\n"
                await asyncio.sleep(0)
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)[:200]})}\n\n"
            return

        assistant = await _save_assistant(full.strip(), citations)
        yield f"data: {json.dumps({'type': 'done', 'message_id': str(assistant.id), 'citations': [c.model_dump() for c in citations], 'conversation_title': conv.get('title') or body.content[:50]})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")

