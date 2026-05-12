import asyncio
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.deps import get_current_user
from app.exceptions import ApiError
from app.models.external import ExternalIntegration, FigmaArtifact, ScreenExternalLink
from app.models.user import User
from app.project_access import is_system_admin, project_member_role, require_project_access
from app.redis_client import get_redis
from app.schemas.integrations import (
    FigmaTestBody,
    FigmaTestResponse,
    FigmaIngestBody,
    FigmaIngestResponse,
    IntegrationConfigOut,
    IntegrationConfigUpsertBody,
    IntegrationLinkOut,
    IntegrationLinkUpsertBody,
    SyncLinkRequestBody,
    SyncLinkResponse,
)
from app.worker import enqueue_external_sync, enqueue_figma_artifact_embedding

router = APIRouter()


async def _rate_limit(redis, key: str, limit: int) -> None:
    from time import time

    bucket = int(time() // 60)
    rkey = f"{key}:{bucket}"
    n = await redis.incr(rkey)
    if n == 1:
        await redis.expire(rkey, 120)
    if n > limit:
        raise ApiError(429, "TOO_MANY_REQUESTS", "Quá nhiều yêu cầu. Vui lòng thử lại sau.")


def _can_manage_integrations(user: User, project_role: str | None) -> bool:
    if is_system_admin(user):
        return True
    return (project_role or "").lower() in {"owner", "pm"}


@router.post("/test-figma", response_model=FigmaTestResponse)
async def test_figma_connection(
    user: Annotated[User, Depends(get_current_user)],
    body: FigmaTestBody,
) -> FigmaTestResponse:
    """Test a Figma token + file_key pair without saving anything."""
    import asyncio
    import requests as req

    headers = {
        "X-Figma-Token": body.personal_access_token,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def _test() -> FigmaTestResponse:
        # Bước 1: verify token qua /me (không bị rate limit)
        me_resp = req.get("https://api.figma.com/v1/me", headers=headers, timeout=10)
        if me_resp.status_code == 401:
            return FigmaTestResponse(ok=False, error="Token không hợp lệ hoặc đã hết hạn.")
        if me_resp.status_code != 200:
            return FigmaTestResponse(ok=False, error=f"Figma API trả về {me_resp.status_code}: {me_resp.text[:200]}")

        # Bước 2: verify file_key — nếu rate limit thì token vẫn OK, báo partial success
        file_resp = req.get(
            f"https://api.figma.com/v1/files/{body.file_key}",
            headers=headers,
            params={"depth": 1},
            timeout=10,
        )
        if file_resp.status_code == 429:
            return FigmaTestResponse(ok=True, file_name="(rate limit — thử sync sau 1 phút)")
        if file_resp.status_code == 404:
            return FigmaTestResponse(ok=False, error="File key không tồn tại hoặc token không có quyền truy cập.")
        if file_resp.status_code == 200:
            name = file_resp.json().get("name", "")
            return FigmaTestResponse(ok=True, file_name=name)
        return FigmaTestResponse(ok=False, error=f"Figma API trả về {file_resp.status_code}: {file_resp.text[:200]}")

    try:
        return await asyncio.to_thread(_test)
    except Exception as exc:
        return FigmaTestResponse(ok=False, error=str(exc)[:300])


@router.post("/figma/ingest", response_model=FigmaIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_figma_link(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    body: FigmaIngestBody,
) -> FigmaIngestResponse:
    """Phase 1: fetch Figma via REST, store to DB. Phase 2 embedding is optional."""
    from app.clients.figma import parse_figma_url
    from app.services.external_sync import ingest_figma_artifact_async

    redis = get_redis()
    await _rate_limit(redis, f"rl:int:figma:ingest:{user.id}", 30)

    await require_project_access(session, user, body.project_id)
    role = await project_member_role(session, user.id, body.project_id)
    if not _can_manage_integrations(user, role):
        raise ApiError(403, "FORBIDDEN", "Bạn không có quyền ingest Figma link")

    # Resolve config (token + file_key) and parse node_id from URL
    file_key, node_id = parse_figma_url(body.figma_url)
    integration = (
        await session.execute(
            select(ExternalIntegration).where(
                ExternalIntegration.project_id == body.project_id,
                ExternalIntegration.type == "figma",
            )
        )
    ).scalar_one_or_none()
    if integration is None:
        raise ApiError(404, "NOT_FOUND", "Chưa cấu hình Figma integration cho project này.")

    token = (body.personal_access_token or integration.config.get("personal_access_token") or "").strip()
    if not token:
        raise ApiError(422, "VALIDATION_ERROR", "Thiếu personal_access_token (chưa set trong integration config).")

    config = {**(integration.config or {})}
    config["personal_access_token"] = token
    config["file_key"] = file_key
    # Allow per-project config: integration.config.llm_markdown / llm_markdown_model

    # Upsert link (figma_frame) for screen
    now = datetime.now(UTC)
    link = (
        await session.execute(
            select(ScreenExternalLink).where(
                ScreenExternalLink.project_id == body.project_id,
                ScreenExternalLink.screen_name == body.screen_name,
                ScreenExternalLink.type == "figma_frame",
                ScreenExternalLink.external_id == node_id,
            )
        )
    ).scalar_one_or_none()

    if link is None:
        link = ScreenExternalLink(
            project_id=body.project_id,
            screen_name=body.screen_name,
            type="figma_frame",
            external_id=node_id,
            external_url=body.figma_url,
            sync_status="syncing",
            created_by=user.id,
            created_at=now,
            updated_at=now,
        )
        session.add(link)
        await session.flush()
    else:
        link.external_url = body.figma_url
        link.sync_status = "syncing"
        link.error_message = None
        link.updated_at = now
        await session.flush()

    # Ingest artifact (REST fetch + markdown + screenshot + upsert)
    artifact = await ingest_figma_artifact_async(session, link, config)
    link.figma_artifact_id = artifact.id
    link.sync_status = "synced"
    link.last_synced_at = datetime.now(UTC)
    link.error_message = None
    link.updated_at = datetime.now(UTC)
    await session.commit()

    # Enqueue embedding phase (optional)
    if settings.figma_embedding_enabled:
        rq_job_id = await asyncio.to_thread(enqueue_figma_artifact_embedding, str(artifact.id))
    else:
        rq_job_id = "disabled"

    # Best-effort refresh embed status after enqueue
    await session.refresh(artifact)
    embed_status = str(getattr(artifact, "embed_status", "pending")).lower()

    return FigmaIngestResponse(
        link_id=link.id,
        figma_artifact_id=artifact.id,
        sync_status="synced",
        embed_status=embed_status,  # type: ignore[arg-type]
        rq_job_id=rq_job_id,
        screenshot_url=artifact.screenshot_url,
        markdown=artifact.markdown,
    )


@router.get("/projects/{project_id}/configs", response_model=list[IntegrationConfigOut])
async def list_integration_configs(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
) -> list[IntegrationConfigOut]:
    redis = get_redis()
    await _rate_limit(redis, f"rl:int:cfg:list:{user.id}", 120)

    await require_project_access(session, user, project_id)

    rows = (
        await session.execute(
            select(ExternalIntegration)
            .where(ExternalIntegration.project_id == project_id)
            .order_by(ExternalIntegration.type.asc())
        )
    ).scalars().all()

    return [
        IntegrationConfigOut(
            id=r.id,
            project_id=r.project_id,
            type=r.type,
            config=r.config or {},
            created_by=r.created_by,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.put("/projects/{project_id}/configs/{integration_type}", response_model=IntegrationConfigOut)
async def upsert_integration_config(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
    integration_type: str,
    body: IntegrationConfigUpsertBody,
) -> IntegrationConfigOut:
    redis = get_redis()
    await _rate_limit(redis, f"rl:int:cfg:upsert:{user.id}", 60)

    t = integration_type.strip().lower()
    if t not in {"figma", "backlog"}:
        raise ApiError(422, "VALIDATION_ERROR", "integration_type phải là figma hoặc backlog")

    await require_project_access(session, user, project_id)
    role = await project_member_role(session, user.id, project_id)
    if not _can_manage_integrations(user, role):
        raise ApiError(403, "FORBIDDEN", "Bạn không có quyền quản lý integration config")

    row = (
        await session.execute(
            select(ExternalIntegration).where(
                ExternalIntegration.project_id == project_id,
                ExternalIntegration.type == t,
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if row is None:
        row = ExternalIntegration(
            project_id=project_id,
            type=t,
            config=body.config,
            created_by=user.id,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.config = body.config
        row.updated_at = now

    await session.commit()
    await session.refresh(row)

    return IntegrationConfigOut(
        id=row.id,
        project_id=row.project_id,
        type=row.type,
        config=row.config or {},
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete("/projects/{project_id}/configs/{integration_type}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration_config(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
    integration_type: str,
) -> None:
    redis = get_redis()
    await _rate_limit(redis, f"rl:int:cfg:delete:{user.id}", 30)

    t = integration_type.strip().lower()
    if t not in {"figma", "backlog"}:
        raise ApiError(422, "VALIDATION_ERROR", "integration_type phải là figma hoặc backlog")

    await require_project_access(session, user, project_id)
    role = await project_member_role(session, user.id, project_id)
    if not _can_manage_integrations(user, role):
        raise ApiError(403, "FORBIDDEN", "Bạn không có quyền quản lý integration config")

    row = (
        await session.execute(
            select(ExternalIntegration).where(
                ExternalIntegration.project_id == project_id,
                ExternalIntegration.type == t,
            )
        )
    ).scalar_one_or_none()

    if row is None:
        raise ApiError(404, "NOT_FOUND", "Integration config không tồn tại")

    await session.delete(row)
    await session.commit()


@router.get("/projects/{project_id}/links", response_model=list[IntegrationLinkOut])
async def list_project_links(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: uuid.UUID,
    screen_name: Annotated[str | None, Query()] = None,
    document_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[IntegrationLinkOut]:
    redis = get_redis()
    await _rate_limit(redis, f"rl:int:link:list:{user.id}", 120)

    await require_project_access(session, user, project_id)

    stmt = (
        select(ScreenExternalLink, FigmaArtifact.embed_status)
        .outerjoin(FigmaArtifact, FigmaArtifact.id == ScreenExternalLink.figma_artifact_id)
        .where(ScreenExternalLink.project_id == project_id)
        .order_by(ScreenExternalLink.created_at.desc())
    )
    if screen_name is not None and screen_name.strip():
        stmt = stmt.where(ScreenExternalLink.screen_name == screen_name.strip())
    if document_id is not None:
        stmt = stmt.where(ScreenExternalLink.document_id == document_id)

    rows = (await session.execute(stmt)).all()
    return [
        IntegrationLinkOut(
            id=link.id,
            project_id=link.project_id,
            screen_name=link.screen_name,
            document_id=link.document_id,
            type=link.type,
            external_id=link.external_id,
            external_url=link.external_url,
            doc_version_id=link.doc_version_id,
            sync_status=link.sync_status,
            embed_status=str(embed_status).lower() if embed_status is not None else None,
            error_message=link.error_message,
            last_synced_at=link.last_synced_at,
            created_by=link.created_by,
            created_at=link.created_at,
            updated_at=link.updated_at,
        )
        for (link, embed_status) in rows
    ]


@router.put("/links", response_model=IntegrationLinkOut)
async def upsert_link(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    body: IntegrationLinkUpsertBody,
) -> IntegrationLinkOut:
    redis = get_redis()
    await _rate_limit(redis, f"rl:int:link:upsert:{user.id}", 60)

    await require_project_access(session, user, body.project_id)
    role = await project_member_role(session, user.id, body.project_id)
    if not _can_manage_integrations(user, role):
        raise ApiError(403, "FORBIDDEN", "Bạn không có quyền quản lý external link")

    row = (
        await session.execute(
            select(ScreenExternalLink).where(
                ScreenExternalLink.project_id == body.project_id,
                ScreenExternalLink.screen_name == body.screen_name,
                ScreenExternalLink.type == body.type,
                ScreenExternalLink.external_id == body.external_id,
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if row is None:
        row = ScreenExternalLink(
            project_id=body.project_id,
            screen_name=body.screen_name,
            type=body.type,
            external_id=body.external_id,
            external_url=body.external_url,
            sync_status="pending",
            created_by=user.id,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.external_url = body.external_url
        row.sync_status = "pending"
        row.error_message = None
        row.updated_at = now

    await session.commit()
    await session.refresh(row)

    return IntegrationLinkOut(
        id=row.id,
        project_id=row.project_id,
        screen_name=row.screen_name,
        document_id=row.document_id,
        type=row.type,
        external_id=row.external_id,
        external_url=row.external_url,
        doc_version_id=row.doc_version_id,
        sync_status=row.sync_status,
        error_message=row.error_message,
        last_synced_at=row.last_synced_at,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    link_id: uuid.UUID,
) -> None:
    redis = get_redis()
    await _rate_limit(redis, f"rl:int:link:delete:{user.id}", 30)

    link = await session.get(ScreenExternalLink, link_id)
    if link is None:
        raise ApiError(404, "NOT_FOUND", "External link không tồn tại")

    await require_project_access(session, user, link.project_id)
    role = await project_member_role(session, user.id, link.project_id)
    if not _can_manage_integrations(user, role):
        raise ApiError(403, "FORBIDDEN", "Bạn không có quyền quản lý external link")

    await session.delete(link)
    await session.commit()


@router.post("/sync", response_model=SyncLinkResponse, status_code=status.HTTP_202_ACCEPTED)
async def sync_link(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    body: SyncLinkRequestBody,
) -> SyncLinkResponse:
    redis = get_redis()
    await _rate_limit(redis, f"rl:int:sync:{user.id}", 30)

    link = await session.get(ScreenExternalLink, body.link_id)
    if link is None:
        raise ApiError(404, "NOT_FOUND", "External link không tồn tại")

    await require_project_access(session, user, link.project_id)
    role = await project_member_role(session, user.id, link.project_id)
    if not _can_manage_integrations(user, role):
        raise ApiError(403, "FORBIDDEN", "Bạn không có quyền chạy sync")

    link.sync_status = "pending"
    link.error_message = None
    link.updated_at = datetime.now(UTC)
    await session.commit()

    try:
        rq_job_id = await asyncio.to_thread(enqueue_external_sync, str(link.id))
    except RedisError as exc:
        raise ApiError(
            503,
            "QUEUE_UNAVAILABLE",
            "Không thể đưa sync job vào hàng đợi. Kiểm tra REDIS_URL và RQ worker.",
        ) from exc

    return SyncLinkResponse(
        link_id=link.id,
        sync_status="pending",
        rq_job_id=rq_job_id,
        message="Sync job đã được đưa vào hàng đợi.",
    )
