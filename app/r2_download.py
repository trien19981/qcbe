"""Download bytes from Cloudflare R2 (S3-compatible) using boto3."""

from __future__ import annotations

from app.config import settings


def download_bytes_from_r2(r2_key: str) -> tuple[bytes, str | None]:
    if not (
        settings.r2_endpoint_url
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.r2_bucket
    ):
        raise RuntimeError("R2 not configured (missing R2_* env vars)")

    import boto3  # type: ignore[import-untyped]
    from botocore.client import Config  # type: ignore[import-untyped]

    region = (settings.r2_region or "auto").strip() or "auto"

    client = boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url.rstrip("/"),
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name=region,
    )

    obj = client.get_object(Bucket=settings.r2_bucket, Key=r2_key)
    body = obj["Body"].read()
    ctype = obj.get("ContentType")
    return body, ctype if isinstance(ctype, str) else None
