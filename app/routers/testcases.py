"""S12 testcase list API (S12_TC_LIST_DESIGN.md §3)."""

from __future__ import annotations

import json
import math
import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from redis.exceptions import RedisError
from sqlalchemy import String, case, cast, column, delete, func, literal, select, table, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.deps import get_current_user
from app.exceptions import ApiError
from app.models.user import User
from app.project_access import is_system_admin, project_member_role, require_project_access
from app.redis_client import get_redis
from app.schemas.testcases import (
    GenerateProgressOut,
    GenerateResultOut,
    LinkedChunkOut,
    PaginationOut,
    ScreenAggItem,
    TestcaseBulkBody,
    TestcaseBulkResponse,
    TestcaseDeleteResponse,
    TestcaseGenerateAccepted,
    TestcaseGenerateBody,
    TestcaseGenerateJobStatusResponse,
    TestcaseListItem,
    TestcaseListResponse,
    TestcaseScreensResponse,
    TestcaseStatsResponse,
    TestcaseSummaryCounts,
    TestcaseUserBrief,
)
from app.worker import enqueue_tc_generate

router = APIRouter()

_tc = table(
    "testcases",
    column("id"),
    column("project_id"),
    column("screen_name"),
    column("title"),
    column("tc_type"),
    column("steps"),
    column("expected_result"),
    column("priority"),
    column("status"),
    column("needs_review"),
    column("tc_sequential"),
    column("tc_id"),
    column("technique"),
    column("source_tvp_id"),
    column("source_tvp_section"),
    column("created_at"),
    column("updated_at"),
    column("created_by"),
)
_users = table("users", column("id"), column("full_name"))
_projects = table("projects", column("id"), column("slug"))
_links = table(
    "testcase_chunk_links",
    column("testcase_id"),
    column("chunk_id"),
    column("link_type"),
    column("is_primary"),
    column("relevance_score"),
)
_chunks = table("chunks", column("id"), column("metadata"), column("doc_version_id"))
_doc_versions = table("doc_versions", column("id"), column("document_id"))

ALLOWED_TC_TYPE = {"manual", "api", "e2e"}
ALLOWED_PRIORITY = {"critical", "high", "medium", "low"}
ALLOWED_STATUS = {"active", "draft", "archived"}


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


def _can_write_tc(user: User, role: str | None) -> bool:
    if is_system_admin(user):
        return True
    return (role or "").lower() in {"owner", "pm", "qc"}


def _parse_status_filter(status_param: str | None) -> list[str]:
    if status_param is None or status_param.strip() == "":
        return ["active", "draft"]
    parts = [p.strip().lower() for p in status_param.split(",") if p.strip()]
    for p in parts:
        if p not in ALLOWED_STATUS:
            raise ApiError(422, "VALIDATION_ERROR", f"status không hợp lệ: {p}")
    return parts


def _priority_rank():
    pl = func.lower(cast(_tc.c.priority, String))
    return case(
        (pl == literal("critical"), 1),
        (pl == literal("high"), 2),
        (pl == literal("medium"), 3),
        (pl == literal("low"), 4),
        else_=5,
    )


def _steps_preview(steps_val: object) -> tuple[int, list[str]]:
    arr: list[str] = []
    if steps_val is None:
        return 0, []
    if isinstance(steps_val, list):
        arr = [str(x) for x in steps_val]
    elif isinstance(steps_val, str):
        try:
            parsed = json.loads(steps_val)
            if isinstance(parsed, list):
                arr = [str(x) for x in parsed]
        except json.JSONDecodeError:
            arr = []
    n = len(arr)
    if n <= 2:
        return n, arr
    return n, arr[:2] + ["..."]


async def _project_summary(session: AsyncSession, project_id: uuid.UUID) -> TestcaseSummaryCounts:
    r = await session.execute(select(func.count()).where(_tc.c.project_id == project_id))
    total = int(r.scalar_one() or 0)
    nr = await session.execute(
        select(func.count()).where(_tc.c.project_id == project_id, _tc.c.needs_review.is_(True))
    )
    needs_review_count = int(nr.scalar_one() or 0)

    by_status: dict[str, int] = {k: 0 for k in ["active", "draft", "archived"]}
    sr = await session.execute(
        select(_tc.c.status, func.count())
        .where(_tc.c.project_id == project_id)
        .group_by(_tc.c.status)
    )
    for st, cnt in sr.all():
        k = str(st).lower() if st else ""
        if k in by_status:
            by_status[k] = int(cnt)

    by_priority: dict[str, int] = {k: 0 for k in ["critical", "high", "medium", "low"]}
    pr = await session.execute(
        select(_tc.c.priority, func.count())
        .where(_tc.c.project_id == project_id)
        .group_by(_tc.c.priority)
    )
    for prv, cnt in pr.all():
        k = str(prv).lower() if prv else ""
        if k in by_priority:
            by_priority[k] = int(cnt)

    return TestcaseSummaryCounts(
        total=total,
        needs_review_count=needs_review_count,
        by_status=by_status,
        by_priority=by_priority,
    )


async def _load_linked_chunks_map(
    session: AsyncSession, testcase_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[LinkedChunkOut]]:
    if not testcase_ids:
        return {}
    section = _chunks.c.metadata.op("->>")("section")
    q = await session.execute(
        select(
            _links.c.testcase_id,
            _links.c.chunk_id,
            cast(_links.c.link_type, String).label("doc_type"),
            _links.c.is_primary,
            section.label("section"),
            _doc_versions.c.document_id,
        )
        .select_from(
            _links
            .join(_chunks, _chunks.c.id == _links.c.chunk_id)
            .join(_doc_versions, _doc_versions.c.id == _chunks.c.doc_version_id)
        )
        .where(_links.c.testcase_id.in_(testcase_ids))
        .order_by(_links.c.is_primary.desc(), _links.c.relevance_score.desc().nullslast())
    )
    out: dict[uuid.UUID, list[LinkedChunkOut]] = {}
    for row in q.all():
        tid = uuid.UUID(str(row[0]))
        out.setdefault(tid, []).append(
            LinkedChunkOut(
                chunk_id=uuid.UUID(str(row[1])),
                doc_type=str(row[2] or ""),
                is_primary=bool(row[3]),
                section=str(row[4]) if row[4] is not None else None,
                document_id=uuid.UUID(str(row[5])) if row[5] else None,
            )
        )
    return out


@router.get("/projects/{project_id}/testcases", response_model=TestcaseListResponse)
async def list_project_testcases(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[uuid.UUID, Path(...)],
    screen: Annotated[str | None, Query(description="screen_name")] = None,
    tc_type: Annotated[str | None, Query()] = None,
    priority: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    needs_review: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    sort_by: Annotated[str, Query()] = "updated_at",
    sort_dir: Annotated[str, Query()] = "desc",
) -> TestcaseListResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:tc:list:{user.id}", 60)

    await require_project_access(session, user, project_id)
    status_list = _parse_status_filter(status)

    if tc_type and tc_type.lower() not in ALLOWED_TC_TYPE:
        raise ApiError(422, "VALIDATION_ERROR", "tc_type không hợp lệ")
    if priority and priority.lower() not in ALLOWED_PRIORITY:
        raise ApiError(422, "VALIDATION_ERROR", "priority không hợp lệ")
    if sort_by not in ("created_at", "updated_at", "priority"):
        raise ApiError(422, "VALIDATION_ERROR", "sort_by không hợp lệ")
    if sort_dir.lower() not in ("asc", "desc"):
        raise ApiError(422, "VALIDATION_ERROR", "sort_dir không hợp lệ")
    sort_dir_lower = sort_dir.lower()

    base = select(
        _tc.c.id,
        _tc.c.project_id,
        _tc.c.screen_name,
        _tc.c.title,
        _tc.c.tc_type,
        _tc.c.priority,
        _tc.c.status,
        _tc.c.needs_review,
        _tc.c.steps,
        _tc.c.expected_result,
        _tc.c.tc_id,
        _tc.c.tc_sequential,
        _tc.c.technique,
        _tc.c.source_tvp_id,
        _tc.c.source_tvp_section,
        _tc.c.created_at,
        _tc.c.updated_at,
        _tc.c.created_by,
        _users.c.full_name.label("creator_name"),
        func.coalesce(func.jsonb_array_length(_tc.c.steps), 0).label("steps_len"),
    ).outerjoin(_users, _users.c.id == _tc.c.created_by)

    base = base.where(_tc.c.project_id == project_id, _tc.c.status.in_(status_list))
    if screen:
        base = base.where(func.lower(_tc.c.screen_name) == screen.strip().lower())
    if tc_type:
        base = base.where(func.lower(cast(_tc.c.tc_type, String)) == tc_type.lower())
    if priority:
        base = base.where(func.lower(cast(_tc.c.priority, String)) == priority.lower())
    if needs_review is not None:
        base = base.where(_tc.c.needs_review == needs_review)
    if search and search.strip():
        pat = f"%{search.strip()}%"
        base = base.where(_tc.c.title.ilike(pat))

    count_q = select(func.count()).select_from(base.subquery())
    total = int((await session.execute(count_q)).scalar_one() or 0)

    order_col = {
        "created_at": _tc.c.created_at,
        "updated_at": _tc.c.updated_at,
        "priority": _priority_rank(),
    }[sort_by]
    if sort_by == "priority":
        base = base.order_by(order_col.desc() if sort_dir_lower == "desc" else order_col.asc())
    else:
        base = base.order_by(
            order_col.desc().nullslast() if sort_dir_lower == "desc" else order_col.asc().nullslast()
        )

    offset = (page - 1) * per_page
    page_q = base.offset(offset).limit(per_page)
    qr = await session.execute(page_q)
    rows = qr.all()

    ids = [r.id for r in rows]
    links_map = await _load_linked_chunks_map(session, ids)

    proj_slug = (
        await session.execute(select(_projects.c.slug).where(_projects.c.id == project_id).limit(1))
    ).scalar_one_or_none()
    prefix = (str(proj_slug or "prj")[:3].upper() or "PRJ").ljust(3, "X")[:3]

    data: list[TestcaseListItem] = []
    for r in rows:
        steps_val = r.steps
        steps_count, preview = _steps_preview(steps_val)
        tid = uuid.UUID(str(r.id))
        links = links_map.get(tid, [])
        tc_id_disp = str(r.tc_id) if r.tc_id else ""
        if not tc_id_disp and r.tc_sequential is not None:
            tc_id_disp = f"TC-{prefix}-{int(r.tc_sequential):03d}"
        if not tc_id_disp:
            tc_id_disp = f"TC-{str(tid)[:8].upper()}"

        creator = None
        if r.created_by and r.creator_name:
            creator = TestcaseUserBrief(id=uuid.UUID(str(r.created_by)), full_name=str(r.creator_name))

        data.append(
            TestcaseListItem(
                id=tid,
                tc_id=tc_id_disp,
                project_id=uuid.UUID(str(r.project_id)),
                screen_name=str(r.screen_name or ""),
                title=str(r.title or ""),
                tc_type=str(r.tc_type or "manual"),
                priority=str(r.priority or "medium"),
                status=str(r.status or "draft"),
                needs_review=bool(r.needs_review),
                steps_count=steps_count or int(r.steps_len or 0),
                steps_preview=preview,
                expected_result=str(r.expected_result) if r.expected_result else None,
                technique=str(r.technique) if r.technique else None,
                source_tvp_id=uuid.UUID(str(r.source_tvp_id)) if r.source_tvp_id else None,
                source_tvp_section=str(r.source_tvp_section) if r.source_tvp_section else None,
                linked_chunks=links,
                linked_chunks_count=len(links),
                created_at=r.created_at,
                updated_at=r.updated_at,
                created_by=creator,
            )
        )

    summary = await _project_summary(session, project_id)
    total_pages = max(1, math.ceil(total / per_page)) if total else 1

    return TestcaseListResponse(
        data=data,
        pagination=PaginationOut(total=total, page=page, per_page=per_page, total_pages=total_pages),
        summary=summary,
    )


@router.get("/projects/{project_id}/testcases/screens", response_model=TestcaseScreensResponse)
async def list_testcase_screens(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[uuid.UUID, Path(...)],
) -> TestcaseScreensResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:tc:screens:{user.id}", 60)
    await require_project_access(session, user, project_id)

    nr_sum = func.sum(case((_tc.c.needs_review.is_(True), 1), else_=0))
    qr = await session.execute(
        select(_tc.c.screen_name, func.count().label("tc_count"), nr_sum.label("needs_review_count"))
        .where(_tc.c.project_id == project_id)
        .group_by(_tc.c.screen_name)
        .order_by(func.lower(_tc.c.screen_name))
    )
    screens: list[ScreenAggItem] = []
    for row in qr.all():
        sn = str(row[0] or "")
        if not sn:
            continue
        screens.append(
            ScreenAggItem(
                screen_name=sn,
                tc_count=int(row[1] or 0),
                needs_review_count=int(row[2] or 0),
            )
        )
    return TestcaseScreensResponse(screens=screens, total=len(screens))


@router.get("/projects/{project_id}/testcases/stats", response_model=TestcaseStatsResponse)
async def testcase_stats(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[uuid.UUID, Path(...)],
) -> TestcaseStatsResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:tc:stats:{user.id}", 30)
    await require_project_access(session, user, project_id)

    summary = await _project_summary(session, project_id)

    by_tc_type: dict[str, int] = {"manual": 0, "api": 0, "e2e": 0}
    tr = await session.execute(
        select(_tc.c.tc_type, func.count()).where(_tc.c.project_id == project_id).group_by(_tc.c.tc_type)
    )
    for tt, cnt in tr.all():
        k = str(tt).lower() if tt else ""
        if k in by_tc_type:
            by_tc_type[k] = int(cnt)

    scr = await session.execute(
        select(_tc.c.screen_name, func.count())
        .where(_tc.c.project_id == project_id)
        .group_by(_tc.c.screen_name)
        .order_by(func.count().desc())
    )
    by_screen: list[dict[str, int | str]] = [
        {"screen_name": str(r[0] or ""), "count": int(r[1] or 0)} for r in scr.all() if r[0]
    ]

    screens_total_r = await session.execute(
        text(
            "SELECT COUNT(DISTINCT screen_name) FROM documents WHERE project_id = CAST(:pid AS uuid)"
        ),
        {"pid": str(project_id)},
    )
    screens_total = int(screens_total_r.scalar_one() or 0)
    screens_with_tc_r = await session.execute(
        text(
            "SELECT COUNT(DISTINCT screen_name) FROM testcases WHERE project_id = CAST(:pid AS uuid) AND screen_name <> ''"
        ),
        {"pid": str(project_id)},
    )
    screens_with_tc = int(screens_with_tc_r.scalar_one() or 0)
    cov_pct = round(100.0 * screens_with_tc / screens_total, 1) if screens_total else 0.0

    return TestcaseStatsResponse(
        project_id=project_id,
        total_testcases=summary.total,
        needs_review=summary.needs_review_count,
        by_status=summary.by_status,
        by_priority=summary.by_priority,
        by_tc_type=by_tc_type,
        by_screen=by_screen,
        coverage={
            "screens_with_tc": screens_with_tc,
            "screens_total": screens_total,
            "coverage_percent": cov_pct,
        },
    )


@router.post(
    "/projects/{project_id}/testcases/generate",
    response_model=TestcaseGenerateAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_generate_testcases(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[uuid.UUID, Path(...)],
    body: TestcaseGenerateBody,
) -> TestcaseGenerateAccepted:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:tc:gen:{user.id}", 5)
    await require_project_access(session, user, project_id)
    role = await project_member_role(session, user.id, project_id)
    if not _can_write_tc(user, role):
        raise ApiError(403, "FORBIDDEN", "Không có quyền")

    chk = await session.execute(
        text(
            """
            SELECT id FROM tc_generate_jobs
            WHERE project_id = CAST(:pid AS uuid) AND status IN ('queued', 'processing')
            LIMIT 1
            """
        ),
        {"pid": str(project_id)},
    )
    if chk.scalar_one_or_none():
        raise ApiError(409, "CONFLICT", "Đang có job generate đang chạy")

    doc_types = body.doc_types

    # Validate TVP nếu có
    if body.tvp_id is not None:
        tr = await session.execute(
            text(
                """
                SELECT id, project_id, screen_name, status
                FROM test_viewpoints WHERE id = CAST(:tid AS uuid)
                """
            ),
            {"tid": str(body.tvp_id)},
        )
        trow = tr.mappings().first()
        if trow is None:
            raise ApiError(404, "NOT_FOUND", "TVP không tồn tại")
        if str(trow["project_id"]) != str(project_id):
            raise ApiError(400, "BAD_REQUEST", "TVP không thuộc project này")
        if str(trow.get("screen_name")) != body.screen_name:
            raise ApiError(
                400,
                "BAD_REQUEST",
                f"TVP thuộc màn hình '{trow.get('screen_name')}' khác với '{body.screen_name}'",
            )
        if str(trow.get("status") or "") != "approved":
            raise ApiError(409, "CONFLICT", "TVP chưa được approve — không thể generate TC từ TVP")

    nchunks = 0
    if doc_types:
        rchunks = await session.execute(
            text(
                """
                SELECT COUNT(*) FROM chunks c
                INNER JOIN doc_versions dv ON dv.id = c.doc_version_id AND dv.status = 'approved'
                INNER JOIN documents d ON d.id = dv.document_id
                WHERE d.project_id = CAST(:pid AS uuid)
                  AND d.screen_name = :sn
                  AND d.doc_type::text = ANY(:dts)
                """
            ),
            {"pid": str(project_id), "sn": body.screen_name, "dts": doc_types},
        )
        nchunks = int(rchunks.scalar_one() or 0)

    if body.tvp_id is None and nchunks == 0:
        raise ApiError(
            404, "NOT_FOUND", "Màn hình không có tài liệu approved cho doc_types đã chọn"
        )

    job_id = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO tc_generate_jobs (
              id, project_id, screen_name, doc_types, tc_type, overwrite_existing,
              tvp_id, status, progress, result, created_by, created_at, updated_at
            ) VALUES (
              CAST(:id AS uuid), CAST(:pid AS uuid), :sn, CAST(:dts AS text[]), :tct, :ov,
              CAST(:tvpid AS uuid),
              'queued', '{}'::jsonb, '{}'::jsonb, CAST(:uid AS uuid), NOW(), NOW()
            )
            """
        ),
        {
            "id": str(job_id),
            "pid": str(project_id),
            "sn": body.screen_name,
            "dts": doc_types,
            "tct": body.tc_type,
            "ov": body.overwrite_existing,
            "tvpid": str(body.tvp_id) if body.tvp_id else None,
            "uid": str(user.id),
        },
    )
    await session.commit()

    enqueue_tc_generate(str(job_id))

    est = min(120, 15 + nchunks * 3)
    return TestcaseGenerateAccepted(
        job_id=job_id,
        screen_name=body.screen_name,
        doc_types=doc_types,
        tvp_id=body.tvp_id,
        estimated_tc_count=min(40, max(6, nchunks * 2 if nchunks else 16)),
        estimated_seconds=est,
        message="Đang generate testcase. Vui lòng chờ...",
    )


@router.get(
    "/projects/{project_id}/testcases/generate/{job_id}/status",
    response_model=TestcaseGenerateJobStatusResponse,
)
async def get_generate_job_status(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[uuid.UUID, Path(...)],
    job_id: Annotated[uuid.UUID, Path(...)],
) -> TestcaseGenerateJobStatusResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:tc:genst:{user.id}", 60)
    await require_project_access(session, user, project_id)

    jr = await session.execute(
        text(
            """
            SELECT id, project_id, status, progress, result, error_message, updated_at
            FROM tc_generate_jobs WHERE id = CAST(:jid AS uuid)
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
    total_chunks = int(prog.get("total_chunks") or 0)
    processed = int(prog.get("processed_chunks") or 0)
    pct = int(prog.get("percentage") or 0)

    res_out = None
    raw_res = row.get("result")
    if isinstance(raw_res, dict) and row.get("status") == "done":
        ids_raw = raw_res.get("testcase_ids") or []
        ids_u: list[uuid.UUID] = []
        for x in ids_raw:
            try:
                ids_u.append(uuid.UUID(str(x)))
            except (ValueError, TypeError):
                continue
        res_out = GenerateResultOut(created_count=int(raw_res.get("created_count") or 0), testcase_ids=ids_u)

    st = str(row.get("status") or "queued")
    if st not in ("queued", "processing", "done", "failed"):
        st = "queued"

    return TestcaseGenerateJobStatusResponse(
        job_id=job_id,
        status=st,
        progress=GenerateProgressOut(
            total_chunks=total_chunks,
            processed_chunks=processed,
            percentage=pct,
        ),
        result=res_out,
        error_message=str(row["error_message"]) if row.get("error_message") else None,
        updated_at=row.get("updated_at"),
    )


@router.patch("/projects/{project_id}/testcases/bulk", response_model=TestcaseBulkResponse)
async def bulk_testcase_actions(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[uuid.UUID, Path(...)],
    body: TestcaseBulkBody,
) -> TestcaseBulkResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:tc:bulk:{user.id}", 20)
    await require_project_access(session, user, project_id)
    role = await project_member_role(session, user.id, project_id)
    if not _can_write_tc(user, role):
        raise ApiError(403, "FORBIDDEN", "Không có quyền")

    if body.action == "set_priority" and body.priority is None:
        raise ApiError(400, "BAD_REQUEST", "Thiếu priority cho action set_priority")

    ids = body.testcase_ids
    skipped: list[uuid.UUID] = []
    affected: list[uuid.UUID] = []

    for tc_id in ids:
        r = await session.execute(
            select(_tc.c.id).where(_tc.c.id == tc_id, _tc.c.project_id == project_id).limit(1)
        )
        if r.scalar_one_or_none() is None:
            skipped.append(tc_id)
            continue
        affected.append(tc_id)

    if not affected:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy testcase nào trong project")

    chunk_ids_bust: list[str] = []
    if body.action == "archive":
        await session.execute(
            update(_tc)
            .where(_tc.c.project_id == project_id, _tc.c.id.in_(affected))
            .values(status="archived", updated_at=func.now())
        )
        msg = f"Đã archive {len(affected)} testcase"
    elif body.action == "delete":
        lr0 = await session.execute(
            select(_links.c.chunk_id).where(_links.c.testcase_id.in_(affected))
        )
        chunk_ids_bust.extend(str(r[0]) for r in lr0.all())
        await session.execute(delete(_links).where(_links.c.testcase_id.in_(affected)))
        await session.execute(delete(_tc).where(_tc.c.project_id == project_id, _tc.c.id.in_(affected)))
        msg = f"Đã xoá {len(affected)} testcase"
    elif body.action == "set_priority":
        await session.execute(
            update(_tc)
            .where(_tc.c.project_id == project_id, _tc.c.id.in_(affected))
            .values(priority=body.priority, updated_at=func.now())
        )
        msg = f"Đã đổi priority cho {len(affected)} testcase"
    elif body.action == "mark_reviewed":
        await session.execute(
            update(_tc)
            .where(_tc.c.project_id == project_id, _tc.c.id.in_(affected))
            .values(needs_review=False, updated_at=func.now())
        )
        msg = f"Đã đánh dấu đã review cho {len(affected)} testcase"
    else:
        raise ApiError(400, "BAD_REQUEST", "action không hợp lệ")

    await session.commit()

    if body.action == "delete":
        try:
            for cid in chunk_ids_bust:
                await redis.delete(f"chunk_tcs:{cid}")
        except RedisError:
            pass

    return TestcaseBulkResponse(
        action=body.action,
        affected_count=len(affected),
        testcase_ids=affected,
        skipped_ids=skipped,
        message=msg,
    )


@router.delete("/testcases/{testcase_id}", response_model=TestcaseDeleteResponse)
async def delete_testcase(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    testcase_id: Annotated[uuid.UUID, Path(...)],
) -> TestcaseDeleteResponse:
    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:tc:del:{user.id}", 30)

    r = await session.execute(
        select(_tc.c.project_id, _tc.c.tc_id, _tc.c.title).where(_tc.c.id == testcase_id).limit(1)
    )
    row = r.first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Testcase không tồn tại")
    project_id = uuid.UUID(str(row[0]))
    tc_label = str(row[1] or row[2] or testcase_id)

    await require_project_access(session, user, project_id)
    role = await project_member_role(session, user.id, project_id)
    if not _can_write_tc(user, role):
        raise ApiError(403, "FORBIDDEN", "Không có quyền xoá")

    lr = await session.execute(
        text("SELECT chunk_id::text FROM testcase_chunk_links WHERE testcase_id = CAST(:tid AS uuid)"),
        {"tid": str(testcase_id)},
    )
    chunk_rows = [x[0] for x in lr.all()]
    n_links = len(chunk_rows)

    await session.execute(delete(_links).where(_links.c.testcase_id == testcase_id))
    await session.execute(delete(_tc).where(_tc.c.id == testcase_id))
    await session.commit()

    for cid in chunk_rows:
        try:
            await redis.delete(f"chunk_tcs:{cid}")
        except RedisError:
            pass

    return TestcaseDeleteResponse(
        message=f"Đã xoá testcase {tc_label}",
        testcase_id=testcase_id,
        unlinked_chunks=n_links,
    )
