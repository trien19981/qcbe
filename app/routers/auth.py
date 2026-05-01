import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.deps import check_origin_if_present, get_client_ip, get_current_user
from app.exceptions import ApiError
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.auth import LoginRequest, LoginResponse, LogoutResponse, MeResponse, RefreshResponse, UserPublic
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    verify_dummy,
    verify_password,
)

router = APIRouter()


def _refresh_cookie_params() -> dict:
    same = settings.cookie_samesite.lower()
    if same not in ("strict", "lax", "none"):
        same = "lax"
    return {
        "key": "refresh_token",
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": same,
        "path": "/api/v1/auth",
        "max_age": settings.refresh_token_expire_seconds,
    }


async def _check_login_fail_rate(redis, ip: str) -> None:
    key = f"login_fail:{ip}"
    cur = await redis.get(key)
    if cur is not None and int(cur) >= 5:
        pttl = await redis.pttl(key)
        ms = pttl if pttl and pttl > 0 else 300_000
        sec = max(1, ms // 1000)
        raise ApiError(
            429,
            "TOO_MANY_REQUESTS",
            f"Quá nhiều lần thử. Vui lòng thử lại sau {sec} giây.",
            headers={"Retry-After": str(sec)},
        )


async def _incr_login_fail(redis, ip: str) -> None:
    key = f"login_fail:{ip}"
    c = await redis.incr(key)
    if c == 1:
        await redis.expire(key, 300)


async def _reset_login_fail(redis, ip: str) -> None:
    await redis.delete(f"login_fail:{ip}")


async def _refresh_rate_gate(redis, user_id: str) -> None:
    bucket = int(time.time() // 60)
    key = f"refresh_rl:{user_id}:{bucket}"
    n = await redis.incr(key)
    if n == 1:
        await redis.expire(key, 120)
    if n > 20:
        raise ApiError(429, "TOO_MANY_REQUESTS", "Quá nhiều lần làm mới token. Vui lòng thử lại sau.")


async def _me_rate_gate(redis, user_id: str) -> None:
    bucket = int(time.time() // 60)
    key = f"me_rl:{user_id}:{bucket}"
    n = await redis.incr(key)
    if n == 1:
        await redis.expire(key, 120)
    if n > 60:
        raise ApiError(429, "TOO_MANY_REQUESTS", "Quá nhiều yêu cầu. Vui lòng thử lại sau.")


def _role_str(role: object) -> str:
    return role if isinstance(role, str) else str(role)


@router.post("/login")
async def login(
    request: Request,
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> JSONResponse:
    check_origin_if_present(request, settings.cors_origin_list)
    ip = get_client_ip(request)
    try:
        redis = get_redis()
        await _check_login_fail_rate(redis, ip)
    except RedisError as e:
        raise ApiError(
            503,
            "SERVICE_UNAVAILABLE",
            "Không kết nối được Redis. Kiểm tra REDIS_URL và dịch vụ Redis.",
        ) from e

    result = await session.execute(select(User).where(User.email == str(body.email)))
    user = result.scalar_one_or_none()

    if user is None:
        verify_dummy(body.password)
        try:
            await _incr_login_fail(redis, ip)
        except RedisError:
            pass
        raise ApiError(401, "UNAUTHORIZED", "Email hoặc mật khẩu không đúng")

    if user.is_active is False:
        raise ApiError(403, "FORBIDDEN", "Tài khoản đã bị khoá. Liên hệ Admin.")

    if not verify_password(body.password, user.password_hash):
        try:
            await _incr_login_fail(redis, ip)
        except RedisError:
            pass
        raise ApiError(401, "UNAUTHORIZED", "Email hoặc mật khẩu không đúng")

    try:
        await _reset_login_fail(redis, ip)
    except RedisError as e:
        raise ApiError(
            503,
            "SERVICE_UNAVAILABLE",
            "Không kết nối được Redis. Kiểm tra REDIS_URL và dịch vụ Redis.",
        ) from e

    role = _role_str(user.role)
    access = create_access_token(user_id=str(user.id), role=role)
    refresh_jwt, jti = create_refresh_token(user_id=str(user.id))
    rkey = f"refresh:{user.id}:{jti}"
    try:
        await redis.set(rkey, "1", ex=settings.refresh_token_expire_seconds)
    except RedisError as e:
        raise ApiError(
            503,
            "SERVICE_UNAVAILABLE",
            "Không kết nối được Redis. Kiểm tra REDIS_URL và dịch vụ Redis.",
        ) from e

    payload = LoginResponse(
        access_token=access,
        token_type="bearer",
        expires_in=settings.access_token_expire_seconds,
        user=UserPublic.model_validate(user),
    )
    resp = JSONResponse(content=payload.model_dump(mode="json"))
    resp.set_cookie(value=refresh_jwt, **_refresh_cookie_params())
    return resp


@router.post("/refresh")
async def refresh_token(request: Request, session: Annotated[AsyncSession, Depends(get_session)]) -> JSONResponse:
    check_origin_if_present(request, settings.cors_origin_list)
    raw = request.cookies.get("refresh_token")
    if not raw:
        raise ApiError(401, "UNAUTHORIZED", "refresh_token không hợp lệ hoặc đã hết hạn")

    try:
        claims = decode_refresh_token(raw, verify_exp=True)
    except Exception:
        raise ApiError(401, "UNAUTHORIZED", "refresh_token không hợp lệ hoặc đã hết hạn") from None

    if claims.get("typ") != "refresh":
        raise ApiError(401, "UNAUTHORIZED", "refresh_token không hợp lệ hoặc đã hết hạn")

    sub = claims.get("sub")
    jti = claims.get("jti")
    if not sub or not jti:
        raise ApiError(401, "UNAUTHORIZED", "refresh_token không hợp lệ hoặc đã hết hạn")

    redis = get_redis()
    rkey = f"refresh:{sub}:{jti}"
    if await redis.get(rkey) is None:
        raise ApiError(401, "UNAUTHORIZED", "refresh_token không hợp lệ hoặc đã hết hạn")

    try:
        uid = uuid.UUID(str(sub))
    except ValueError:
        raise ApiError(401, "UNAUTHORIZED", "refresh_token không hợp lệ hoặc đã hết hạn") from None

    result = await session.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "refresh_token không hợp lệ hoặc đã hết hạn")
    if user.is_active is False:
        raise ApiError(403, "FORBIDDEN", "Tài khoản bị khoá")

    await _refresh_rate_gate(redis, str(user.id))

    access = create_access_token(user_id=str(user.id), role=_role_str(user.role))
    out = RefreshResponse(
        access_token=access,
        token_type="bearer",
        expires_in=settings.access_token_expire_seconds,
    )
    return JSONResponse(content=out.model_dump(mode="json"))


@router.post("/logout", response_model=LogoutResponse)
async def logout(request: Request) -> JSONResponse:
    """Luôn 200: xoá cookie và cố gắng revoke refresh trong Redis."""
    check_origin_if_present(request, settings.cors_origin_list)
    redis = get_redis()
    raw = request.cookies.get("refresh_token")

    if raw:
        try:
            claims = decode_refresh_token(raw, verify_exp=False)
            if claims.get("typ") == "refresh":
                sub, jti = claims.get("sub"), claims.get("jti")
                if sub and jti:
                    await redis.delete(f"refresh:{sub}:{jti}")
        except Exception:
            pass

    same = settings.cookie_samesite.lower()
    if same not in ("strict", "lax", "none"):
        same = "lax"
    resp = JSONResponse(content=LogoutResponse(message="Đăng xuất thành công").model_dump())
    resp.delete_cookie(
        key="refresh_token",
        path="/api/v1/auth",
        secure=settings.cookie_secure,
        httponly=True,
        samesite=same,
    )
    return resp


@router.get("/me", response_model=MeResponse)
async def me(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> MeResponse:
    check_origin_if_present(request, settings.cors_origin_list)
    redis = get_redis()
    await _me_rate_gate(redis, str(user.id))
    return MeResponse.model_validate(user)
