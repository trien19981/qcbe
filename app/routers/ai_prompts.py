"""Per-project AI prompt overrides (Q&A, suggested questions, TC generation)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.deps import get_current_user
from app.exceptions import ApiError
from app.models.user import User
from app.project_access import is_system_admin, project_member_role, require_project_access
from app.schemas.ai_prompts import (
    AiPromptDeleteResponse,
    AiPromptListResponse,
    AiPromptItemOut,
    AiPromptPatchBody,
    AiPromptPatchResponse,
)
from app.services import ai_prompts as ap

router = APIRouter()

ALLOWED_KEYS = frozenset(
    {
        ap.QA_ANSWER_SYSTEM,
        ap.QA_SUGGESTED_QUESTIONS_USER,
        ap.TC_GENERATE_PROMPT,
    }
)


def _can_edit_prompts(user: User, role: str | None) -> bool:
    if is_system_admin(user):
        return True
    return (role or "").lower() in {"owner", "pm"}


@router.get("/projects/{project_id}/ai-prompts", response_model=AiPromptListResponse)
async def list_ai_prompts(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[uuid.UUID, Path(...)],
) -> AiPromptListResponse:
    await require_project_access(session, user, project_id)
    items = [
        AiPromptItemOut(
            key=ap.QA_ANSWER_SYSTEM,
            content=await ap.get_ai_prompt(session, project_id, ap.QA_ANSWER_SYSTEM, ap.DEFAULT_QA_ANSWER_SYSTEM),
        ),
        AiPromptItemOut(
            key=ap.QA_SUGGESTED_QUESTIONS_USER,
            content=await ap.get_ai_prompt(
                session, project_id, ap.QA_SUGGESTED_QUESTIONS_USER, ap.DEFAULT_QA_SUGGESTED_QUESTIONS_USER
            ),
        ),
        AiPromptItemOut(
            key=ap.TC_GENERATE_PROMPT,
            content=await ap.get_ai_prompt(session, project_id, ap.TC_GENERATE_PROMPT, ap.DEFAULT_TC_GENERATE_PROMPT),
        ),
    ]
    return AiPromptListResponse(prompts=items)


@router.patch("/projects/{project_id}/ai-prompts/{prompt_key}", response_model=AiPromptPatchResponse)
async def upsert_ai_prompt(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[uuid.UUID, Path(...)],
    prompt_key: Annotated[str, Path(...)],
    body: AiPromptPatchBody,
) -> AiPromptPatchResponse:
    await require_project_access(session, user, project_id)
    role = await project_member_role(session, user.id, project_id)
    if not _can_edit_prompts(user, role):
        raise ApiError(403, "FORBIDDEN", "Chỉ owner / PM / admin mới chỉnh được prompt AI.")

    if prompt_key not in ALLOWED_KEYS:
        raise ApiError(422, "VALIDATION_ERROR", f"prompt_key không hợp lệ: {prompt_key}")

    await session.execute(
        text(
            """
            INSERT INTO ai_prompts (id, project_id, prompt_key, content, updated_at, updated_by)
            VALUES (gen_random_uuid(), CAST(:pid AS uuid), :pk, :content, NOW(), CAST(:uid AS uuid))
            ON CONFLICT (project_id, prompt_key)
            DO UPDATE SET content = EXCLUDED.content, updated_at = NOW(), updated_by = EXCLUDED.updated_by
            """
        ),
        {"pid": str(project_id), "pk": prompt_key, "content": body.content, "uid": str(user.id)},
    )
    await session.commit()
    return AiPromptPatchResponse(key=prompt_key, message="Đã lưu prompt.")


@router.delete(
    "/projects/{project_id}/ai-prompts/{prompt_key}",
    response_model=AiPromptDeleteResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_ai_prompt_override(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    project_id: Annotated[uuid.UUID, Path(...)],
    prompt_key: Annotated[str, Path(...)],
) -> AiPromptDeleteResponse:
    await require_project_access(session, user, project_id)
    role = await project_member_role(session, user.id, project_id)
    if not _can_edit_prompts(user, role):
        raise ApiError(403, "FORBIDDEN", "Chỉ owner / PM / admin mới chỉnh được prompt AI.")

    if prompt_key not in ALLOWED_KEYS:
        raise ApiError(422, "VALIDATION_ERROR", f"prompt_key không hợp lệ: {prompt_key}")

    res = await session.execute(
        text("DELETE FROM ai_prompts WHERE project_id = CAST(:pid AS uuid) AND prompt_key = :pk"),
        {"pid": str(project_id), "pk": prompt_key},
    )
    await session.commit()
    if res.rowcount == 0:
        raise ApiError(404, "NOT_FOUND", "Không có override cho prompt này.")
    return AiPromptDeleteResponse(key=prompt_key, message="Đã xoá override; dùng lại prompt mặc định.")
