import time
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.exceptions import ApiError
from app.config import settings
from app.redis_client import get_redis
from app.schemas.embeddings import EmbedChunksRequest, EmbedChunksResponse
from app.models.user import User


router = APIRouter()

MAX_CHUNKS = 200


async def _rate_limit_minute(redis, key: str, limit: int) -> None:
    bucket = int(time.time() // 60)
    rkey = f"{key}:{bucket}"
    n = await redis.incr(rkey)
    if n == 1:
        await redis.expire(rkey, 120)
    if n > limit:
        raise ApiError(429, "TOO_MANY_REQUESTS", "Quá nhiều yêu cầu. Vui lòng thử lại sau.")


@router.post("/embedding/chunks", response_model=EmbedChunksResponse)
async def embed_chunks(
    body: EmbedChunksRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> EmbedChunksResponse:
    """
    Nhận danh sách chunk (text) từ FE/BE, chạy embedding và trả về vector.
    Không lưu vào DB/pgvector (endpoint tiện ích). Pipeline upload/version sẽ tự embed + lưu DB.
    """

    if len(body.chunks) > MAX_CHUNKS:
        raise ApiError(400, "VALIDATION_ERROR", f"Tối đa {MAX_CHUNKS} chunks mỗi request.")

    redis = get_redis()
    await _rate_limit_minute(redis, f"rl:embed:chunks:{user.id}", limit=30)

    if not settings.embedding_service_url:
        raise ApiError(
            500,
            "EMBEDDING_NOT_CONFIGURED",
            "Thiếu `EMBEDDING_SERVICE_URL`. Cấu hình embedding-service để dùng endpoint này.",
        )

    url = settings.embedding_service_url.rstrip("/") + "/embed/chunks"
    headers: dict[str, str] = {}
    if settings.embedding_service_internal_key:
        headers["X-Internal-Key"] = settings.embedding_service_internal_key

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(url, json=body.model_dump(mode="json"), headers=headers)
        if resp.status_code >= 400:
            raise ApiError(
                502,
                "EMBEDDING_SERVICE_ERROR",
                f"Embedding service trả lỗi: {resp.status_code}",
                extra={"response": resp.text[:500]},
            )
        payload = resp.json()
        return EmbedChunksResponse.model_validate(payload)
    except ApiError:
        raise
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        raise ApiError(
            502,
            "EMBEDDING_SERVICE_ERROR",
            f"Không thể gọi embedding service: {e}",
            extra={"elapsed_ms": elapsed_ms, "url": url},
        ) from None

