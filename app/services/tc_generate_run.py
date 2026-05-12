"""Background execution for POST /projects/{id}/testcases/generate (S12)."""

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


def _slug_prefix(slug: str) -> str:
    s = (slug or "prj").strip().upper().replace("-", "")[:8]
    if len(s) < 3:
        s = (s + "XXX")[:3]
    return s[:3]


async def _exec_job_update(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    status: str | None = None,
    progress: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
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
    await session.execute(text(f"UPDATE tc_generate_jobs SET {', '.join(parts)} WHERE id = :jid"), params)


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


async def _fetch_tvp_for_tc(
    session: AsyncSession, tvp_id: uuid.UUID
) -> dict[str, Any] | None:
    r = await session.execute(
        text(
            """
            SELECT id, project_id, screen_name, status, content_md
            FROM test_viewpoints WHERE id = CAST(:tid AS uuid)
            """
        ),
        {"tid": str(tvp_id)},
    )
    row = r.mappings().first()
    return dict(row) if row else None


_ALLOWED_TECHNIQUES = {"BVA", "EP", "DT", "ST", "Negative", "UC", "EG"}


def _normalize_technique(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if s in _ALLOWED_TECHNIQUES:
        return s
    upper = s.upper()
    aliases = {
        "BOUNDARY": "BVA",
        "BOUNDARY VALUE": "BVA",
        "EQUIVALENCE": "EP",
        "EQUIVALENCE PARTITIONING": "EP",
        "DECISION": "DT",
        "DECISION TABLE": "DT",
        "STATE": "ST",
        "STATE TRANSITION": "ST",
        "USE CASE": "UC",
        "USECASE": "UC",
        "ERROR GUESSING": "EG",
        "ERROR-GUESSING": "EG",
        "NEGATIVE": "Negative",
    }
    return aliases.get(upper)


async def _next_tc_sequential(session: AsyncSession, project_id: uuid.UUID) -> int:
    r = await session.execute(
        text(
            "SELECT COALESCE(MAX(tc_sequential), 0) + 1 AS n FROM testcases WHERE project_id = CAST(:pid AS uuid)"
        ),
        {"pid": str(project_id)},
    )
    return int(r.scalar_one())


async def _delete_draft_for_screen(
    session: AsyncSession, project_id: uuid.UUID, screen_name: str
) -> None:
    await session.execute(
        text(
            """
            DELETE FROM testcase_chunk_links tcl
            USING testcases t
            WHERE tcl.testcase_id = t.id
              AND t.project_id = CAST(:pid AS uuid)
              AND t.screen_name = :sn
              AND t.status = 'draft'
            """
        ),
        {"pid": str(project_id), "sn": screen_name},
    )
    await session.execute(
        text(
            """
            DELETE FROM testcases
            WHERE project_id = CAST(:pid AS uuid) AND screen_name = :sn AND status = 'draft'
            """
        ),
        {"pid": str(project_id), "sn": screen_name},
    )


async def run_tc_generate_job(job_id: str) -> None:
    """RQ worker entry: load job, generate TCs, update job row."""
    from app.database import AsyncSessionLocal, engine
    from app.models.project import Project

    jid = uuid.UUID(job_id)

    async def _run() -> None:
        async with AsyncSessionLocal() as session:
            jr = await session.execute(
                text(
                    """
                    SELECT id, project_id, screen_name, doc_types, tc_type, status, created_by,
                           overwrite_existing, tvp_id
                    FROM tc_generate_jobs WHERE id = :jid
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
            tc_type_default = str(job["tc_type"])
            created_by = job.get("created_by")
            overwrite = bool(job.get("overwrite_existing"))
            tvp_id_raw = job.get("tvp_id")
            tvp_uuid: uuid.UUID | None = (
                uuid.UUID(str(tvp_id_raw)) if tvp_id_raw else None
            )

            try:
                if overwrite:
                    await _delete_draft_for_screen(session, project_id, screen_name)
                    await session.commit()

                tvp_row: dict[str, Any] | None = None
                tvp_md = ""
                if tvp_uuid is not None:
                    tvp_row = await _fetch_tvp_for_tc(session, tvp_uuid)
                    if tvp_row is None:
                        await _exec_job_update(
                            session,
                            jid,
                            status="failed",
                            error_message="TVP không tồn tại",
                        )
                        await session.commit()
                        return
                    if str(tvp_row.get("project_id")) != str(project_id):
                        await _exec_job_update(
                            session,
                            jid,
                            status="failed",
                            error_message="TVP không thuộc project này",
                        )
                        await session.commit()
                        return
                    if str(tvp_row.get("status") or "") != "approved":
                        await _exec_job_update(
                            session,
                            jid,
                            status="failed",
                            error_message="TVP chưa được approve — không thể generate TC",
                        )
                        await session.commit()
                        return
                    tvp_md = str(tvp_row.get("content_md") or "")

                chunks = await _fetch_approved_chunks(session, project_id, screen_name, doc_types)
                if not chunks and not tvp_md:
                    await _exec_job_update(
                        session,
                        jid,
                        status="failed",
                        progress={"total_chunks": 0, "processed_chunks": 0, "percentage": 0},
                        error_message="Không có TVP cũng như chunk tài liệu approved để generate TC",
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
                if tvp_md:
                    tmpl = await ai_prompt_svc.get_ai_prompt(
                        session,
                        project_id,
                        ai_prompt_svc.TC_FROM_TVP_PROMPT,
                        ai_prompt_svc.DEFAULT_TC_FROM_TVP_PROMPT,
                    )
                    tmpl = ai_prompt_svc.inject_references(tmpl, ai_prompt_svc.TC_FROM_TVP_PROMPT)
                    prompt = tmpl.replace("{tvp_md}", tvp_md)
                    if "{context}" in prompt:
                        prompt = ai_prompt_svc.inject_context(prompt, context)
                    else:
                        prompt = prompt.rstrip() + "\n\n[TÀI LIỆU SPEC]\n" + context
                else:
                    tmpl = await ai_prompt_svc.get_ai_prompt(
                        session,
                        project_id,
                        ai_prompt_svc.TC_GENERATE_PROMPT,
                        ai_prompt_svc.DEFAULT_TC_GENERATE_PROMPT,
                    )
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

                tc_list = loads_llm_json_array(raw)

                proj = await session.get(Project, project_id)
                prefix = _slug_prefix(proj.slug if proj else "prj")

                created_ids: list[uuid.UUID] = []
                for tc_data in tc_list:
                    if not isinstance(tc_data, dict):
                        continue
                    title = (tc_data.get("title") or "Untitled")[:500]
                    steps = tc_data.get("steps") or []
                    if not isinstance(steps, list):
                        steps = []
                    steps_json = json.dumps([str(s) for s in steps])
                    expected = str(tc_data.get("expected_result") or "")[:10000]
                    priority = str(tc_data.get("priority") or "medium").lower()
                    if priority not in ("critical", "high", "medium", "low"):
                        priority = "medium"
                    row_tc_type = str(tc_data.get("tc_type") or tc_type_default).lower()
                    if row_tc_type not in ("manual", "api", "e2e"):
                        row_tc_type = tc_type_default

                    technique = _normalize_technique(tc_data.get("technique"))
                    src_section = str(tc_data.get("source_tvp_section") or "")[:300] or None

                    seq = await _next_tc_sequential(session, project_id)
                    tc_uuid = uuid.uuid4()
                    tc_id_str = f"TC-{prefix}-{seq:03d}"

                    base_ins = """
                            INSERT INTO testcases (
                              id, project_id, screen_name, title, tc_type, steps, expected_result,
                              priority, status, needs_review, tc_sequential, tc_id,
                              source_tvp_id, technique, source_tvp_section,
                              created_by, created_at, updated_at
                            ) VALUES (
                              CAST(:id AS uuid), CAST(:pid AS uuid), :sn, :title, :tct, CAST(:steps AS jsonb), :exp,
                              :pri, 'draft', false, :seq, :tcid,
                              CAST(:tvpid AS uuid), :tech, :tvpsec,
                              {created_by_value}, NOW(), NOW()
                            )
                            """
                    params_ins: dict[str, Any] = {
                        "id": str(tc_uuid),
                        "pid": str(project_id),
                        "sn": screen_name,
                        "title": title,
                        "tct": row_tc_type,
                        "steps": steps_json,
                        "exp": expected,
                        "pri": priority,
                        "seq": seq,
                        "tcid": tc_id_str,
                        "tvpid": str(tvp_uuid) if tvp_uuid else None,
                        "tech": technique,
                        "tvpsec": src_section,
                    }
                    if created_by:
                        params_ins["uid"] = str(created_by)
                        await session.execute(
                            text(base_ins.format(created_by_value="CAST(:uid AS uuid)")),
                            params_ins,
                        )
                    else:
                        await session.execute(
                            text(base_ins.format(created_by_value="NULL")),
                            params_ins,
                        )

                    chunk_idx = int(tc_data.get("source_chunk_index") or 0)
                    if chunk_idx < 0:
                        chunk_idx = 0
                    if chunk_idx < len(chunks):
                        ch = chunks[chunk_idx]
                        link_dt = str(ch.get("doc_type") or doc_types[0])
                        await session.execute(
                            text(
                                """
                                INSERT INTO testcase_chunk_links (
                                  id, testcase_id, chunk_id, link_type, relevance_score, is_primary, created_at
                                ) VALUES (
                                  gen_random_uuid(), CAST(:tc AS uuid), CAST(:ck AS uuid),
                                  CAST(:lt AS doc_type_enum), 1.0, true, NOW()
                                )
                                """
                            ),
                            {"tc": str(tc_uuid), "ck": str(ch["id"]), "lt": link_dt},
                        )

                    created_ids.append(tc_uuid)

                await session.commit()

                await _exec_job_update(
                    session,
                    jid,
                    status="done",
                    progress={"total_chunks": total, "processed_chunks": total, "percentage": 100},
                    result={
                        "created_count": len(created_ids),
                        "testcase_ids": [str(x) for x in created_ids],
                    },
                )
                await session.commit()

            except Exception as exc:
                logger.exception("tc_generate job failed")
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
                    logger.exception("failed to persist job failure state")

    try:
        await _run()
    finally:
        await engine.dispose()


def run_tc_generate_job_sync(job_id: str) -> None:
    """Sync wrapper for RQ."""
    import asyncio

    asyncio.run(run_tc_generate_job(job_id))
