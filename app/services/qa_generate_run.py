"""Background execution for POST /projects/{id}/qa-analyses/generate.

Step 1 in Q&A → TVP → TC pipeline. Generates a Gap Analysis from approved spec
chunks using the Claude API and stores items as editable rows.
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
from app.services import ai_prompts as ai_prompt_svc
from app.services.anthropic_stream_final import (
    build_anthropic_client,
    loads_llm_json_array,
    stream_user_message_text,
)

logger = logging.getLogger(__name__)


_ALLOWED_CATEGORIES = {
    "Functional",
    "Business Logic",
    "Data",
    "Validation",
    "Integration",
    "Edge Case",
    "UI/UX",
    "Non-functional",
}
_ALLOWED_RISKS = {"High", "Medium", "Low"}


async def _exec_job_update(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    status: str | None = None,
    progress: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
    qa_analysis_id: uuid.UUID | None = None,
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
    if qa_analysis_id is not None:
        parts.append("qa_analysis_id = CAST(:aid AS uuid)")
        params["aid"] = str(qa_analysis_id)
    await session.execute(text(f"UPDATE qa_jobs SET {', '.join(parts)} WHERE id = :jid"), params)


async def _fetch_approved_chunks(
    session: AsyncSession,
    project_id: uuid.UUID,
    screen_name: str,
    doc_types: list[str],
) -> list[dict[str, Any]]:
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


def _build_context(chunks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for i, ch in enumerate(chunks):
        meta = ch.get("metadata") or {}
        section = meta.get("section") if isinstance(meta, dict) else None
        head = f"--- Chunk {i} --- (doc_type={ch.get('doc_type')}, section={section!r})\n"
        body = (ch.get("content_text") or "")[:8000]
        parts.append(head + body)
    return "\n\n".join(parts)


def _normalize_gap_id(raw: Any, idx: int) -> str:
    s = str(raw or "").strip()
    if re.match(r"^G-\d{3,}$", s):
        return s
    return f"G-{idx + 1:03d}"


def _normalize_category(raw: Any) -> str:
    s = str(raw or "").strip()
    if s in _ALLOWED_CATEGORIES:
        return s
    low = s.lower()
    for cat in _ALLOWED_CATEGORIES:
        if cat.lower() == low:
            return cat
    return "Functional"


def _normalize_risk(raw: Any) -> str:
    s = str(raw or "").strip().capitalize()
    if s in _ALLOWED_RISKS:
        return s
    low = s.lower()
    if low.startswith("h"):
        return "High"
    if low.startswith("l"):
        return "Low"
    return "Medium"


async def _delete_draft_for_screen(
    session: AsyncSession, project_id: uuid.UUID, screen_name: str
) -> None:
    """Remove any draft Q&A analyses for the same screen so overwrite_existing works."""
    await session.execute(
        text(
            """
            DELETE FROM qa_gap_analyses
            WHERE project_id = CAST(:pid AS uuid)
              AND screen_name = :sn
              AND status = 'draft'
            """
        ),
        {"pid": str(project_id), "sn": screen_name},
    )


async def run_qa_generate_job(job_id: str) -> None:
    """RQ worker entry: load job, generate Q&A items, update job row."""
    from app.database import AsyncSessionLocal, engine

    jid = uuid.UUID(job_id)

    async def _run() -> None:
        async with AsyncSessionLocal() as session:
            jr = await session.execute(
                text(
                    """
                    SELECT id, project_id, screen_name, doc_types, status, created_by
                    FROM qa_jobs WHERE id = :jid
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
            doc_types = list(job["doc_types"])
            created_by = job.get("created_by")

            try:
                chunks = await _fetch_approved_chunks(session, project_id, screen_name, doc_types)
                if not chunks:
                    await _exec_job_update(
                        session,
                        jid,
                        status="failed",
                        progress={"total_chunks": 0, "processed_chunks": 0, "percentage": 0},
                        error_message="Không có chunk tài liệu approved cho lựa chọn này",
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

                context = _build_context(chunks)
                tmpl = await ai_prompt_svc.get_ai_prompt(
                    session,
                    project_id,
                    ai_prompt_svc.QA_GAP_ANALYSIS_PROMPT,
                    ai_prompt_svc.DEFAULT_QA_GAP_ANALYSIS_PROMPT,
                )
                tmpl = ai_prompt_svc.inject_references(tmpl, ai_prompt_svc.QA_GAP_ANALYSIS_PROMPT)
                if "{context}" in tmpl:
                    prompt = ai_prompt_svc.inject_context(tmpl, context)
                else:
                    prompt = tmpl.rstrip() + "\n\n[TÀI LIỆU]\n" + context

                raw = await stream_user_message_text(
                    client,
                    model=settings.anthropic_model,
                    max_tokens=16000,
                    user_text=prompt,
                    thinking={"type": "disabled"},
                )

                gap_list = loads_llm_json_array(raw)

                analysis_id = uuid.uuid4()
                await session.execute(
                    text(
                        """
                        INSERT INTO qa_gap_analyses (
                          id, project_id, screen_name, doc_types, status,
                          total_items, answered_items, generated_by,
                          generated_at, created_at, updated_at
                        ) VALUES (
                          CAST(:id AS uuid), CAST(:pid AS uuid), :sn, CAST(:dts AS text[]), 'draft',
                          0, 0, CAST(:uid AS uuid),
                          NOW(), NOW(), NOW()
                        )
                        """
                    ),
                    {
                        "id": str(analysis_id),
                        "pid": str(project_id),
                        "sn": screen_name,
                        "dts": doc_types,
                        "uid": str(created_by) if created_by else None,
                    },
                )

                inserted = 0
                seen_gap_ids: set[str] = set()
                for idx, gap in enumerate(gap_list):
                    if not isinstance(gap, dict):
                        continue
                    gap_id_str = _normalize_gap_id(gap.get("gap_id"), idx)
                    while gap_id_str in seen_gap_ids:
                        idx += 1
                        gap_id_str = f"G-{idx + 1:03d}"
                    seen_gap_ids.add(gap_id_str)

                    category = _normalize_category(gap.get("category"))
                    risk = _normalize_risk(gap.get("risk"))
                    description = str(gap.get("gap_description") or "")[:4000].strip()
                    question = str(gap.get("question") or "")[:4000].strip()
                    if not description or not question:
                        continue

                    chunk_idx_raw = gap.get("source_chunk_index")
                    src_chunk_id: str | None = None
                    try:
                        ci = int(chunk_idx_raw) if chunk_idx_raw is not None else -1
                        if 0 <= ci < len(chunks):
                            src_chunk_id = str(chunks[ci]["id"])
                    except (TypeError, ValueError):
                        src_chunk_id = None

                    await session.execute(
                        text(
                            """
                            INSERT INTO qa_gap_items (
                              id, qa_analysis_id, gap_id, category, gap_description,
                              risk, question, answer, answer_status,
                              source_chunk_id, display_order,
                              created_at, updated_at
                            ) VALUES (
                              gen_random_uuid(), CAST(:aid AS uuid), :gid, :cat, :desc,
                              :risk, :q, NULL, 'open',
                              CAST(:scid AS uuid), :ord,
                              NOW(), NOW()
                            )
                            """
                        ),
                        {
                            "aid": str(analysis_id),
                            "gid": gap_id_str,
                            "cat": category,
                            "desc": description,
                            "risk": risk,
                            "q": question,
                            "scid": src_chunk_id,
                            "ord": inserted,
                        },
                    )
                    inserted += 1

                await session.execute(
                    text(
                        "UPDATE qa_gap_analyses SET total_items = :n, updated_at = NOW() "
                        "WHERE id = CAST(:aid AS uuid)"
                    ),
                    {"n": inserted, "aid": str(analysis_id)},
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
                    result={
                        "qa_analysis_id": str(analysis_id),
                        "total_items": inserted,
                    },
                    qa_analysis_id=analysis_id,
                )
                await session.commit()

            except Exception as exc:
                logger.exception("qa_generate job failed")
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
                    logger.exception("failed to persist qa job failure state")

    try:
        await _run()
    finally:
        await engine.dispose()


def run_qa_generate_job_sync(job_id: str) -> None:
    """Sync wrapper for RQ."""
    import asyncio

    asyncio.run(run_qa_generate_job(job_id))
