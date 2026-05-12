"""Test Viewpoints API — step 2 in Q&A → TVP → TC pipeline.

Endpoints:
- POST   /api/v1/projects/{pid}/tvp/generate                      (owner/pm/qc)
- GET    /api/v1/projects/{pid}/tvp                                (any member)
- GET    /api/v1/projects/{pid}/tvp/jobs/{job_id}/status
- GET    /api/v1/tvp/{id}                                          (any member)
- PATCH  /api/v1/tvp/{id}                                          (owner/pm/qc)
- POST   /api/v1/tvp/{id}/approve                                  (owner/pm/qc)
- POST   /api/v1/tvp/{id}/archive                                  (owner/pm/qc)
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, status
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.deps import get_current_user
from app.exceptions import ApiError
from app.models.user import User
from app.project_access import is_system_admin, project_member_role, require_project_access
from app.redis_client import get_redis
from app.schemas.test_viewpoints import (
    TVPApproveResponse,
    TVPChecklistItem,
    TVPDetailResponse,
    TVPGenerateAccepted,
    TVPGenerateBody,
    TVPJobProgressOut,
    TVPJobResultOut,
    TVPJobStatusResponse,
    TVPListItem,
    TVPListResponse,
    TVPPatchBody,
    TVPUserBrief,
)
from app.worker import enqueue_tvp_generate

router = APIRouter()


async def _rate_limit_minute(redis, key: str, limit: int) -> None:
    bucket = int(time.time() // 60)
    rkey = f"{key}:{bucket}"
    try:
        n = await redis.incr(rkey)
        if n == 1:
            await redis.expire(rkey, 120)
    except RedisError as exc:
        raise ApiError(
            503,
            "REDIS_UNAVAILABLE",
            "Không kết nối được Redis. Kiểm tra REDIS_URL và dịch vụ Redis đang chạy.",
        ) from exc
    if n > limit:
        raise ApiError(429, "TOO_MANY_REQUESTS", "Quá nhiều yêu cầu. Vui lòng thử lại sau.")


def _can_write_tvp(user: User, role: str | None) -> bool:
    if is_system_admin(user):
        return True
    return (role or "").lower() in {"owner", "pm", "qc"}


async def _get_tvp_or_404(session: AsyncSession, tvp_id: uuid.UUID) -> dict[str, Any]:
    r = await session.execute(
        text(
            """
            SELECT id, project_id, screen_name, qa_analysis_id, status,
                   content_md, checklist_18, generated_by, approved_by, approved_at,
                   created_at, updated_at
            FROM test_viewpoints WHERE id = :tid
            """
        ),
        {"tid": str(tvp_id)},
    )
    row = r.mappings().first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "TVP không tồn tại")
    return dict(row)


async def _user_briefs(session: AsyncSession, uids: set[uuid.UUID]) -> dict[uuid.UUID, TVPUserBrief]:
    if not uids:
        return {}
    rows = await session.execute(
        text("SELECT id, full_name FROM users WHERE id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": [str(x) for x in uids]},
    )
    out: dict[uuid.UUID, TVPUserBrief] = {}
    for row in rows.mappings():
        u = uuid.UUID(str(row["id"]))
        out[u] = TVPUserBrief(id=u, full_name=str(row["full_name"] or ""))
    return out


def _coverage_counts(checklist: list[Any]) -> tuple[int, int, int]:
    """Return (total, covered, percent) — only count non-n_a items."""
    total = 0
    covered = 0
    if isinstance(checklist, list):
        for it in checklist:
            if not isinstance(it, dict):
                continue
            st = str(it.get("status") or "not_covered")
            if st == "n_a":
                continue
            total += 1
            if st == "covered":
                covered += 1
    pct = int(round(100.0 * covered / total)) if total > 0 else 0
    return total, covered, pct


@router.post(
    "/projects/{project_id}/tvp/generate",
    response_model=TVPGenerateAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_generate_tvp(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[uuid.UUID, Path(...)],
    body: TVPGenerateBody,
) -> TVPGenerateAccepted:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:tvp:gen:{user.id}", 5)
    await require_project_access(session, user, project_id)
    role = await project_member_role(session, user.id, project_id)
    if not _can_write_tvp(user, role):
        raise ApiError(403, "FORBIDDEN", "Không có quyền generate TVP")

    chk = await session.execute(
        text(
            """
            SELECT id FROM tvp_jobs
            WHERE project_id = CAST(:pid AS uuid) AND status IN ('queued', 'processing')
            LIMIT 1
            """
        ),
        {"pid": str(project_id)},
    )
    if chk.scalar_one_or_none():
        raise ApiError(409, "CONFLICT", "Đang có job TVP khác đang chạy")

    if body.qa_analysis_id is not None:
        qa_r = await session.execute(
            text(
                """
                SELECT id, project_id, screen_name, status, total_items, answered_items
                FROM qa_gap_analyses WHERE id = CAST(:aid AS uuid)
                """
            ),
            {"aid": str(body.qa_analysis_id)},
        )
        qa_row = qa_r.mappings().first()
        if qa_row is None or str(qa_row["project_id"]) != str(project_id):
            raise ApiError(404, "NOT_FOUND", "Q&A Analysis không tồn tại trong project")
        if str(qa_row.get("screen_name")) != body.screen_name:
            raise ApiError(
                400,
                "BAD_REQUEST",
                "Q&A Analysis thuộc màn hình khác — chọn đúng màn hình hoặc bỏ qua qa_analysis_id",
            )
        if str(qa_row.get("status") or "") != "completed":
            raise ApiError(
                409,
                "CONFLICT",
                f"Q&A chưa hoàn thành ({qa_row['answered_items']}/{qa_row['total_items']} đã trả lời). "
                "Hoàn thành Q&A trước khi gen TVP, hoặc bỏ qua qa_analysis_id.",
            )

    rchunks = await session.execute(
        text(
            """
            SELECT COUNT(*) FROM chunks c
            INNER JOIN doc_versions dv ON dv.id = c.doc_version_id AND dv.status = 'approved'
            INNER JOIN documents d ON d.id = dv.document_id
            WHERE d.project_id = CAST(:pid AS uuid)
              AND d.screen_name = :sn
              AND ( :no_doc_filter OR d.doc_type::text = ANY(:dts) )
            """
        ),
        {
            "pid": str(project_id),
            "sn": body.screen_name,
            "no_doc_filter": len(body.doc_types) == 0,
            "dts": body.doc_types,
        },
    )
    nchunks = int(rchunks.scalar_one() or 0)
    if nchunks == 0 and body.qa_analysis_id is None:
        raise ApiError(404, "NOT_FOUND", "Màn hình không có tài liệu approved cho doc_types đã chọn")

    if body.overwrite_existing:
        await session.execute(
            text(
                """
                DELETE FROM test_viewpoints
                WHERE project_id = CAST(:pid AS uuid) AND screen_name = :sn AND status = 'draft'
                """
            ),
            {"pid": str(project_id), "sn": body.screen_name},
        )

    job_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO tvp_jobs (
              id, project_id, screen_name, qa_analysis_id, doc_types,
              status, progress, result, created_by, created_at, updated_at
            ) VALUES (
              CAST(:id AS uuid), CAST(:pid AS uuid), :sn, CAST(:aid AS uuid), CAST(:dts AS text[]),
              'queued', '{}'::jsonb, '{}'::jsonb, CAST(:uid AS uuid), NOW(), NOW()
            )
            """
        ),
        {
            "id": str(job_id),
            "pid": str(project_id),
            "sn": body.screen_name,
            "aid": str(body.qa_analysis_id) if body.qa_analysis_id else None,
            "dts": body.doc_types,
            "uid": str(user.id),
        },
    )
    await session.commit()

    enqueue_tvp_generate(str(job_id))

    est = min(180, 30 + nchunks * 4)
    return TVPGenerateAccepted(
        job_id=job_id,
        screen_name=body.screen_name,
        qa_analysis_id=body.qa_analysis_id,
        estimated_seconds=est,
        message="Đang sinh TVP. Vui lòng chờ...",
    )


@router.get(
    "/projects/{project_id}/tvp/jobs/{job_id}/status",
    response_model=TVPJobStatusResponse,
)
async def get_tvp_job_status(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[uuid.UUID, Path(...)],
    job_id: Annotated[uuid.UUID, Path(...)],
) -> TVPJobStatusResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:tvp:jobst:{user.id}", 60)
    await require_project_access(session, user, project_id)

    jr = await session.execute(
        text(
            """
            SELECT id, project_id, status, progress, result, error_message, tvp_id, updated_at
            FROM tvp_jobs WHERE id = CAST(:jid AS uuid)
            """
        ),
        {"jid": str(job_id)},
    )
    row = jr.mappings().first()
    if row is None or str(row["project_id"]) != str(project_id):
        raise ApiError(404, "NOT_FOUND", "Job không tồn tại")

    prog = row.get("progress") or {}
    if not isinstance(prog, dict):
        prog = {}
    res_out = None
    raw_res = row.get("result")
    if isinstance(raw_res, dict) and row.get("status") == "done":
        tid_raw = raw_res.get("tvp_id") or row.get("tvp_id")
        if tid_raw:
            try:
                res_out = TVPJobResultOut(tvp_id=uuid.UUID(str(tid_raw)))
            except (ValueError, TypeError):
                res_out = None

    st = str(row.get("status") or "queued")
    if st not in ("queued", "processing", "done", "failed"):
        st = "queued"

    return TVPJobStatusResponse(
        job_id=job_id,
        status=st,
        progress=TVPJobProgressOut(
            total_chunks=int(prog.get("total_chunks") or 0),
            processed_chunks=int(prog.get("processed_chunks") or 0),
            percentage=int(prog.get("percentage") or 0),
        ),
        result=res_out,
        error_message=str(row["error_message"]) if row.get("error_message") else None,
        updated_at=row.get("updated_at"),
    )


@router.get("/projects/{project_id}/tvp", response_model=TVPListResponse)
async def list_tvp(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[uuid.UUID, Path(...)],
) -> TVPListResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:tvp:list:{user.id}", 60)
    await require_project_access(session, user, project_id)

    rows = await session.execute(
        text(
            """
            SELECT id, project_id, screen_name, qa_analysis_id, status,
                   content_md, checklist_18, generated_by, approved_by, approved_at,
                   created_at, updated_at
            FROM test_viewpoints
            WHERE project_id = CAST(:pid AS uuid)
            ORDER BY created_at DESC
            """
        ),
        {"pid": str(project_id)},
    )
    items = [dict(r) for r in rows.mappings().all()]

    user_ids: set[uuid.UUID] = set()
    for it in items:
        if it.get("generated_by"):
            user_ids.add(uuid.UUID(str(it["generated_by"])))
        if it.get("approved_by"):
            user_ids.add(uuid.UUID(str(it["approved_by"])))
    briefs = await _user_briefs(session, user_ids)

    data: list[TVPListItem] = []
    for it in items:
        cl = it.get("checklist_18")
        if isinstance(cl, str):
            try:
                cl = json.loads(cl)
            except json.JSONDecodeError:
                cl = []
        total, covered, pct = _coverage_counts(cl if isinstance(cl, list) else [])
        gb = it.get("generated_by")
        ab = it.get("approved_by")
        data.append(
            TVPListItem(
                id=uuid.UUID(str(it["id"])),
                project_id=uuid.UUID(str(it["project_id"])),
                screen_name=str(it.get("screen_name") or ""),
                status=str(it.get("status") or "draft"),
                qa_analysis_id=uuid.UUID(str(it["qa_analysis_id"]))
                if it.get("qa_analysis_id")
                else None,
                coverage_total=total,
                coverage_covered=covered,
                coverage_percent=pct,
                generated_by=briefs.get(uuid.UUID(str(gb))) if gb else None,
                approved_by=briefs.get(uuid.UUID(str(ab))) if ab else None,
                approved_at=it.get("approved_at"),
                created_at=it.get("created_at"),
                updated_at=it.get("updated_at"),
            )
        )

    return TVPListResponse(data=data, total=len(data))


@router.get("/tvp/{tvp_id}", response_model=TVPDetailResponse)
async def get_tvp_detail(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    tvp_id: Annotated[uuid.UUID, Path(...)],
) -> TVPDetailResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:tvp:detail:{user.id}", 60)

    tvp = await _get_tvp_or_404(session, tvp_id)
    project_id = uuid.UUID(str(tvp["project_id"]))
    await require_project_access(session, user, project_id)

    cl_raw = tvp.get("checklist_18")
    if isinstance(cl_raw, str):
        try:
            cl_raw = json.loads(cl_raw)
        except json.JSONDecodeError:
            cl_raw = []
    cl_list = cl_raw if isinstance(cl_raw, list) else []
    total, covered, pct = _coverage_counts(cl_list)

    user_ids: set[uuid.UUID] = set()
    if tvp.get("generated_by"):
        user_ids.add(uuid.UUID(str(tvp["generated_by"])))
    if tvp.get("approved_by"):
        user_ids.add(uuid.UUID(str(tvp["approved_by"])))
    briefs = await _user_briefs(session, user_ids)

    checklist_out: list[TVPChecklistItem] = []
    for it in cl_list:
        if not isinstance(it, dict):
            continue
        checklist_out.append(
            TVPChecklistItem(
                key=str(it.get("key") or ""),
                label=str(it.get("label") or "") or None,
                status=str(it.get("status") or "not_covered"),  # type: ignore[arg-type]
                note=str(it.get("note") or "") or None,
            )
        )

    gb = tvp.get("generated_by")
    ab = tvp.get("approved_by")
    return TVPDetailResponse(
        id=uuid.UUID(str(tvp["id"])),
        project_id=project_id,
        screen_name=str(tvp.get("screen_name") or ""),
        qa_analysis_id=uuid.UUID(str(tvp["qa_analysis_id"]))
        if tvp.get("qa_analysis_id")
        else None,
        status=str(tvp.get("status") or "draft"),
        content_md=str(tvp.get("content_md") or ""),
        checklist_18=checklist_out,
        coverage_total=total,
        coverage_covered=covered,
        coverage_percent=pct,
        generated_by=briefs.get(uuid.UUID(str(gb))) if gb else None,
        approved_by=briefs.get(uuid.UUID(str(ab))) if ab else None,
        approved_at=tvp.get("approved_at"),
        created_at=tvp.get("created_at"),
        updated_at=tvp.get("updated_at"),
    )


@router.patch("/tvp/{tvp_id}", response_model=TVPDetailResponse)
async def patch_tvp(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    tvp_id: Annotated[uuid.UUID, Path(...)],
    body: TVPPatchBody,
) -> TVPDetailResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:tvp:patch:{user.id}", 60)

    tvp = await _get_tvp_or_404(session, tvp_id)
    project_id = uuid.UUID(str(tvp["project_id"]))
    await require_project_access(session, user, project_id)
    role = await project_member_role(session, user.id, project_id)
    if not _can_write_tvp(user, role):
        raise ApiError(403, "FORBIDDEN", "Không có quyền sửa TVP")

    if body.content_md is None and body.checklist_18 is None:
        raise ApiError(400, "BAD_REQUEST", "Phải cung cấp content_md hoặc checklist_18")

    parts: list[str] = ["updated_at = NOW()"]
    params: dict[str, Any] = {"tid": str(tvp_id)}
    if body.content_md is not None:
        parts.append("content_md = :md")
        params["md"] = body.content_md
    if body.checklist_18 is not None:
        parts.append("checklist_18 = CAST(:cl AS jsonb)")
        params["cl"] = json.dumps([item.model_dump() for item in body.checklist_18])

    await session.execute(
        text(f"UPDATE test_viewpoints SET {', '.join(parts)} WHERE id = CAST(:tid AS uuid)"),
        params,
    )
    await session.commit()

    return await get_tvp_detail(session, user, tvp_id)


@router.post("/tvp/{tvp_id}/approve", response_model=TVPApproveResponse)
async def approve_tvp(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    tvp_id: Annotated[uuid.UUID, Path(...)],
) -> TVPApproveResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:tvp:approve:{user.id}", 30)

    tvp = await _get_tvp_or_404(session, tvp_id)
    project_id = uuid.UUID(str(tvp["project_id"]))
    await require_project_access(session, user, project_id)
    role = await project_member_role(session, user.id, project_id)
    if not _can_write_tvp(user, role):
        raise ApiError(403, "FORBIDDEN", "Không có quyền approve TVP")

    cl_raw = tvp.get("checklist_18")
    if isinstance(cl_raw, str):
        try:
            cl_raw = json.loads(cl_raw)
        except json.JSONDecodeError:
            cl_raw = []
    if isinstance(cl_raw, list):
        for it in cl_raw:
            if not isinstance(it, dict):
                continue
            st = str(it.get("status") or "")
            note = str(it.get("note") or "").strip()
            if st in ("not_covered", "n_a") and not note:
                raise ApiError(
                    409,
                    "CONFLICT",
                    f"Mục checklist {it.get('key')} status = {st} nhưng chưa có note giải thích.",
                )

    await session.execute(
        text(
            """
            UPDATE test_viewpoints
            SET status = 'approved',
                approved_by = CAST(:uid AS uuid),
                approved_at = NOW(),
                updated_at = NOW()
            WHERE id = CAST(:tid AS uuid)
            """
        ),
        {"uid": str(user.id), "tid": str(tvp_id)},
    )
    await session.commit()

    return TVPApproveResponse(
        id=tvp_id,
        status="approved",
        approved_at=None,
        message="Đã approve TVP. Có thể tiến tới generate test cases.",
    )


@router.post("/tvp/{tvp_id}/archive", response_model=TVPApproveResponse)
async def archive_tvp(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    tvp_id: Annotated[uuid.UUID, Path(...)],
) -> TVPApproveResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:tvp:archive:{user.id}", 30)

    tvp = await _get_tvp_or_404(session, tvp_id)
    project_id = uuid.UUID(str(tvp["project_id"]))
    await require_project_access(session, user, project_id)
    role = await project_member_role(session, user.id, project_id)
    if not _can_write_tvp(user, role):
        raise ApiError(403, "FORBIDDEN", "Không có quyền archive TVP")

    await session.execute(
        text(
            """
            UPDATE test_viewpoints
            SET status = 'archived', updated_at = NOW()
            WHERE id = CAST(:tid AS uuid)
            """
        ),
        {"tid": str(tvp_id)},
    )
    await session.commit()
    return TVPApproveResponse(id=tvp_id, status="archived", approved_at=None, message="Đã archive TVP.")
