"""Upload bytes to Cloudflare R2 (S3-compatible) using boto3."""

from __future__ import annotations

from app.config import settings
from app.exceptions import ApiError


def upload_to_r2(r2_key: str, content: bytes, content_type: str) -> None:
    if not (
        settings.r2_endpoint_url
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.r2_bucket
    ):
        raise ApiError(
            503,
            "R2_NOT_CONFIGURED",
            "Chưa cấu hình R2. Thiết lập R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET trong môi trường API.",
        )

    import boto3  # type: ignore[import-untyped]
    from botocore.client import Config  # type: ignore[import-untyped]
    from botocore.exceptions import ClientError  # type: ignore[import-untyped]

    region = (settings.r2_region or "auto").strip() or "auto"

    client = boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url.rstrip("/"),
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name=region,
    )

    try:
        client.put_object(
            Bucket=settings.r2_bucket,
            Key=r2_key,
            Body=content,
            ContentType=content_type,
        )
    except ClientError as exc:
        code = (exc.response.get("Error") or {}).get("Code") or "Unknown"
        raise ApiError(
            502,
            "R2_UPLOAD_FAILED",
            f"Không thể tải file lên lưu trữ (R2/S3). Mã lỗi: {code}",
        ) from exc

