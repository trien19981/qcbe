"""Background execution for POST /projects/{id}/tvp/generate.

Step 2 in Q&A → TVP → TC pipeline. Builds context from approved spec chunks +
answered Q&A items, calls Claude, stores TVP markdown + checklist 18 mục.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.schemas.test_viewpoints import CHECKLIST_18_KEYS
from app.services import ai_prompts as ai_prompt_svc
from app.services.anthropic_stream_final import (
    build_anthropic_client,
    loads_llm_json_object,
    stream_user_message_text,
)

logger = logging.getLogger(__name__)


_DEFAULT_LABELS: dict[str, str] = {
    "FUNCTIONAL_HAPPY_PATH": "FUNCTIONAL (Happy Path)",
    "INPUT_VALIDATION": "INPUT VALIDATION (Field Level)",
    "BOUNDARY_VALUE": "BOUNDARY VALUE (BVA)",
    "NEGATIVE_CASE": "NEGATIVE CASE",
    "USER_BEHAVIOR": "USER BEHAVIOR (Real-world)",
    "SYSTEM_BEHAVIOR": "SYSTEM BEHAVIOR",
    "DATA_INTEGRITY": "DATA INTEGRITY",
    "DB_UI_DATA_MAPPING": "DB ↔ UI DATA MAPPING",
    "INTEGRATION_API": "INTEGRATION (API)",
    "SECURITY_BASIC": "SECURITY (Basic)",
    "UX_UI": "UX/UI",
    "STATE_FLOW": "STATE & FLOW",
    "CONCURRENCY": "CONCURRENCY (Advanced)",
    "DATA_LIFECYCLE": "DATA LIFECYCLE",
    "SEARCH_FILTER_SORT": "SEARCH / FILTER / SORT",
    "PAGINATION_LARGE_DATA": "PAGINATION / LARGE DATA",
    "CROSS_FIELD_VALIDATION": "CROSS-FIELD VALIDATION",
    "IMPORT_EXPORT": "IMPORT / EXPORT",
}

_ALLOWED_STATUSES = {"covered", "not_covered", "n_a"}


async def _exec_job_update(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    status: str | None = None,
    progress: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
    tvp_id: uuid.UUID | None = None,
) -> None:
    parts: list[str] = ["updated_at = NOW()"]
    params: dict[str, Any] = {"jid": str(job_id)}
    if status is not None:
        parts.append("status = :status")
        params["status"] = status
    if progress is not None:
        parts.append("progress = CAST(:progress AS jsonb)")
        params["progress"] = json.dumps(progress)
    if result is not None:
        parts.append("result = CAST(:result AS jsonb)")
        params["result"] = json.dumps(result)
    if error_message is not None:
        parts.append("error_message = :err")
        params["err"] = error_message[:2000]
    if tvp_id is not None:
        parts.append("tvp_id = CAST(:tid AS uuid)")
        params["tid"] = str(tvp_id)
    await session.execute(text(f"UPDATE tvp_jobs SET {', '.join(parts)} WHERE id = :jid"), params)


async def _fetch_approved_chunks(
    session: AsyncSession,
    project_id: uuid.UUID,
    screen_name: str,
    doc_types: list[str],
) -> list[dict[str, Any]]:
    if not doc_types:
        doc_types = ["basic_design", "api_design", "detail_design", "testcase_manual"]
    q = text(
        """
        SELECT c.id, c.chunk_index, c.content_text, c.metadata, d.doc_type::text AS doc_type
        FROM chunks c
        INNER JOIN doc_versions dv ON dv.id = c.doc_version_id AND dv.status = 'approved'
        INNER JOIN documents d ON d.id = dv.document_id
        WHERE d.project_id = CAST(:pid AS uuid)
          AND d.screen_name = :screen
          AND d.doc_type::text = ANY(:doc_types)
        ORDER BY d.doc_type::text, c.chunk_index
        """
    )
    r = await session.execute(
        q,
        {"pid": str(project_id), "screen": screen_name, "doc_types": doc_types},
    )
    return [dict(x) for x in r.mappings().all()]


async def _fetch_answered_qa_items(
    session: AsyncSession, qa_analysis_id: uuid.UUID
) -> list[dict[str, Any]]:
    q = text(
        """
        SELECT gap_id, category, gap_description, risk, question, answer, answer_status
        FROM qa_gap_items
        WHERE qa_analysis_id = CAST(:aid AS uuid)
        ORDER BY display_order ASC, gap_id ASC
        """
    )
    r = await session.execute(q, {"aid": str(qa_analysis_id)})
    return [dict(x) for x in r.mappings().all()]


def _build_context(chunks: list[dict[str, Any]], qa_items: list[dict[str, Any]] | None) -> str:
    parts: list[str] = []

    if qa_items:
        parts.append("=== Q&A ĐÃ ĐƯỢC TRẢ LỜI (input từ bước 1) ===\n")
        for it in qa_items:
            ans = (it.get("answer") or "").strip()
            st = str(it.get("answer_status") or "open")
            ans_block = ans if ans else f"(không có câu trả lời, status={st})"
            parts.append(
                f"- [{it.get('gap_id')}] [{it.get('category')}] (Risk: {it.get('risk')})\n"
                f"  Gap: {it.get('gap_description')}\n"
                f"  Q: {it.get('question')}\n"
                f"  A: {ans_block}"
            )
        parts.append("")

    parts.append("=== TÀI LIỆU SPEC/DESIGN (chunks đã approved) ===\n")
    for i, ch in enumerate(chunks):
        meta = ch.get("metadata") or {}
        section = meta.get("section") if isinstance(meta, dict) else None
        head = f"--- Chunk {i} --- (doc_type={ch.get('doc_type')}, section={section!r})\n"
        body = (ch.get("content_text") or "")[:8000]
        parts.append(head + body)

    return "\n\n".join(parts)


def _normalize_checklist(raw: Any) -> list[dict[str, Any]]:
    """Ensure 18 items in correct order, fill defaults for any missing."""
    by_key: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        for x in raw:
            if not isinstance(x, dict):
                continue
            key = str(x.get("key") or "").strip()
            if key in _DEFAULT_LABELS:
                status = str(x.get("status") or "not_covered").strip()
                if status not in _ALLOWED_STATUSES:
                    status = "not_covered"
                by_key[key] = {
                    "key": key,
                    "label": str(x.get("label") or _DEFAULT_LABELS[key]),
                    "status": status,
                    "note": str(x.get("note") or ""),
                }
    out: list[dict[str, Any]] = []
    for key in CHECKLIST_18_KEYS:
        item = by_key.get(key) or {
            "key": key,
            "label": _DEFAULT_LABELS[key],
            "status": "not_covered",
            "note": "(LLM không trả về mục này)",
        }
        out.append(item)
    return out


async def run_tvp_generate_job(job_id: str) -> None:
    """RQ worker entry: load job, generate TVP markdown + checklist, update job row."""
    from app.database import AsyncSessionLocal, engine

    jid = uuid.UUID(job_id)

    async def _run() -> None:
        async with AsyncSessionLocal() as session:
            jr = await session.execute(
                text(
                    """
                    SELECT id, project_id, screen_name, qa_analysis_id, doc_types,
                           status, created_by
                    FROM tvp_jobs WHERE id = :jid
                    """
                ),
                {"jid": str(jid)},
            )
            job = jr.mappings().first()
            if job is None:
                return
            job = dict(job)
            if str(job.get("status") or "") != "queued":
                return

            await _exec_job_update(
                session,
                jid,
                status="processing",
                progress={"total_chunks": 0, "processed_chunks": 0, "percentage": 0},
            )
            await session.commit()

            project_id = uuid.UUID(str(job["project_id"]))
            screen_name = str(job["screen_name"])
            doc_types = list(job["doc_types"] or [])
            qa_analysis_id_raw = job.get("qa_analysis_id")
            qa_analysis_id = uuid.UUID(str(qa_analysis_id_raw)) if qa_analysis_id_raw else None
            created_by = job.get("created_by")

            try:
                chunks = await _fetch_approved_chunks(session, project_id, screen_name, doc_types)
                qa_items: list[dict[str, Any]] | None = None
                if qa_analysis_id:
                    qa_items = await _fetch_answered_qa_items(session, qa_analysis_id)

                if not chunks and not qa_items:
                    await _exec_job_update(
                        session,
                        jid,
                        status="failed",
                        progress={"total_chunks": 0, "processed_chunks": 0, "percentage": 0},
                        error_message="Không có chunk approved hoặc Q&A để build context",
                    )
                    await session.commit()
                    return

                total = len(chunks)
                await _exec_job_update(
                    session,
                    jid,
                    progress={"total_chunks": total, "processed_chunks": 0, "percentage": 0},
                )
                await session.commit()

                if not settings.anthropic_api_key:
                    await _exec_job_update(
                        session,
                        jid,
                        status="failed",
                        progress={"total_chunks": total, "processed_chunks": 0, "percentage": 0},
                        error_message="Thiếu ANTHROPIC_API_KEY",
                    )
                    await session.commit()
                    return

                client = build_anthropic_client(
                    api_key=settings.anthropic_api_key,
                    base_url=settings.anthropic_base_url,
                )

                context = _build_context(chunks, qa_items)
                tmpl = await ai_prompt_svc.get_ai_prompt(
                    session,
                    project_id,
                    ai_prompt_svc.TVP_GENERATE_PROMPT,
                    ai_prompt_svc.DEFAULT_TVP_GENERATE_PROMPT,
                )
                tmpl = ai_prompt_svc.inject_references(tmpl, ai_prompt_svc.TVP_GENERATE_PROMPT)
                if "{context}" in tmpl:
                    prompt = ai_prompt_svc.inject_context(tmpl, context)
                else:
                    prompt = tmpl.rstrip() + "\n\n[TÀI LIỆU]\n" + context

                raw = await stream_user_message_text(
                    client,
                    model=settings.anthropic_model,
                    max_tokens=60000,
                    user_text=prompt,
                    thinking={"type": "disabled"},
                )

                payload = loads_llm_json_object(raw)

                content_md = str(payload.get("content_md") or "").strip()
                if not content_md:
                    raise ValueError("LLM output thiếu content_md")
                checklist = _normalize_checklist(payload.get("checklist_18"))

                tvp_id = uuid.uuid4()
                await session.execute(
                    text(
                        """
                        INSERT INTO test_viewpoints (
                          id, project_id, screen_name, qa_analysis_id, status,
                          content_md, checklist_18,
                          generated_by, created_at, updated_at
                        ) VALUES (
                          CAST(:id AS uuid), CAST(:pid AS uuid), :sn,
                          CAST(:aid AS uuid), 'draft',
                          :md, CAST(:cl AS jsonb),
                          CAST(:uid AS uuid), NOW(), NOW()
                        )
                        """
                    ),
                    {
                        "id": str(tvp_id),
                        "pid": str(project_id),
                        "sn": screen_name,
                        "aid": str(qa_analysis_id) if qa_analysis_id else None,
                        "md": content_md,
                        "cl": json.dumps(checklist),
                        "uid": str(created_by) if created_by else None,
                    },
                )
                await session.commit()

                await _exec_job_update(
                    session,
                    jid,
                    status="done",
                    progress={
                        "total_chunks": total,
                        "processed_chunks": total,
                        "percentage": 100,
                    },
                    result={"tvp_id": str(tvp_id)},
                    tvp_id=tvp_id,
                )
                await session.commit()

            except Exception as exc:
                logger.exception("tvp_generate job failed")
                await session.rollback()
                try:
                    await _exec_job_update(
                        session,
                        jid,
                        status="failed",
                        error_message=str(exc)[:2000],
                    )
                    await session.commit()
                except Exception:
                    logger.exception("failed to persist tvp job failure state")

    try:
        await _run()
    finally:
        await engine.dispose()


def run_tvp_generate_job_sync(job_id: str) -> None:
    """Sync wrapper for RQ."""
    import asyncio

    asyncio.run(run_tvp_generate_job(job_id))
