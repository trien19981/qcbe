"""Presigned GET (R2/S3) và URL public CDN (R2_PUBLIC_BASE_URL)."""

from __future__ import annotations

from app.config import settings


def public_download_url(r2_key: str) -> str | None:
    """URL tải qua CDN/public nếu đã cấu hình R2_PUBLIC_BASE_URL."""
    base = settings.r2_public_base_url
    if not base or not r2_key:
        return None
    return f"{base.rstrip('/')}/{r2_key.lstrip('/')}"


def try_presign_download(r2_key: str, expires_seconds: int = 900) -> str | None:
    if not (
        settings.r2_endpoint_url
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.r2_bucket
    ):
        return None
    try:
        import boto3  # type: ignore[import-untyped]
        from botocore.client import Config  # type: ignore[import-untyped]
    except ImportError:
        return None

    region = (settings.r2_region or "auto").strip() or "auto"
    client = boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url.rstrip("/"),
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name=region,
    )
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket, "Key": r2_key},
        ExpiresIn=expires_seconds,
    )
