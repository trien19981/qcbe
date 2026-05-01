from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Lỗi API với body cố định: error, message, status_code (+ extra tùy chọn)."""

    __slots__ = ("status_code", "error", "message", "headers", "extra")

    def __init__(
        self,
        status_code: int,
        error: str,
        message: str,
        headers: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.error = error
        self.message = message
        self.headers = headers
        self.extra = extra or {}


def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    body: dict[str, Any] = {
        "error": exc.error,
        "message": exc.message,
        "status_code": exc.status_code,
    }
    body.update(exc.extra)
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(body),
        headers=exc.headers,
    )
