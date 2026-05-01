import uuid
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.exceptions import ApiError
from app.models.user import User
from app.security import decode_access_token


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def check_origin_if_present(request: Request, allowed: list[str]) -> None:
    """Theo tài liệu: kiểm tra Origin. Thiếu Origin (curl, app) thì bỏ qua."""
    origin = request.headers.get("origin")
    if not origin or not allowed:
        return
    if origin not in allowed:
        raise ApiError(403, "FORBIDDEN", "Origin không được phép")


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "UNAUTHORIZED", "access_token không hợp lệ")
    token = authorization[7:].strip()
    if not token:
        raise ApiError(401, "UNAUTHORIZED", "access_token không hợp lệ")
    try:
        payload = decode_access_token(token)
    except Exception:
        raise ApiError(401, "UNAUTHORIZED", "access_token hết hạn hoặc không hợp lệ") from None
    if payload.get("typ") != "access":
        raise ApiError(401, "UNAUTHORIZED", "access_token không hợp lệ")
    sub = payload.get("sub")
    if not sub:
        raise ApiError(401, "UNAUTHORIZED", "access_token không hợp lệ")
    uid = sub if isinstance(sub, str) else str(sub)
    try:
        user_uuid = uuid.UUID(uid)
    except ValueError:
        raise ApiError(401, "UNAUTHORIZED", "access_token không hợp lệ") from None

    result = await session.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "access_token không hợp lệ")
    if user.is_active is False:
        raise ApiError(403, "FORBIDDEN", "Tài khoản đã bị khoá. Liên hệ Admin.")
    return user
