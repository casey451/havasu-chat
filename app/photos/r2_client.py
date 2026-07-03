"""Cloudflare R2 (S3-compatible) client — lazy singleton, upload + delete helpers."""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.config import Config

_r2_client: Any = None

_REQUIRED_ENV = (
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_ENDPOINT_URL",
    "R2_BUCKET_NAME",
    "R2_PUBLIC_URL_BASE",
)


def _missing_env_vars() -> list[str]:
    return [k for k in _REQUIRED_ENV if not (os.getenv(k) or "").strip()]


def get_r2_client() -> Any:
    """Return a process-wide boto3 S3 client configured for R2.

    Raises ``RuntimeError`` if any required env var is missing (call time, not
    import time).
    """
    global _r2_client
    if _r2_client is not None:
        return _r2_client
    missing = _missing_env_vars()
    if missing:
        raise RuntimeError(
            "R2 is not configured: missing environment variable(s): " + ", ".join(missing)
        )
    _r2_client = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"].strip(),
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"].strip(),
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"].strip(),
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )
    return _r2_client


def build_public_url(key: str) -> str:
    """Join ``R2_PUBLIC_URL_BASE`` with object ``key`` (slash-safe)."""
    base = (os.getenv("R2_PUBLIC_URL_BASE") or "").strip().rstrip("/")
    k = (key or "").lstrip("/")
    return f"{base}/{k}" if k else base


def upload_bytes(key: str, content: bytes, content_type: str) -> str:
    """Upload bytes to R2; return public URL. Sets long-cache immutable headers."""
    client = get_r2_client()
    bucket = os.environ["R2_BUCKET_NAME"].strip()
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentType=content_type,
        CacheControl="public, max-age=31536000, immutable",
    )
    return build_public_url(key)



def reset_r2_client_for_tests() -> None:
    """Clear lazy singleton (tests only)."""
    global _r2_client
    _r2_client = None
