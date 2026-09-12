"""File upload service — S3-compatible storage with local fallback.

Validation (never trust the client):
- size limit (UPLOAD_MAX_BYTES)
- MAGIC-BYTE sniffing for the allowed image types (client MIME ignored)
- random filename; original name never used on disk
"""

from __future__ import annotations

import io
import os
import uuid
from typing import Optional, Tuple

from vyron.config import settings
from vyron.errors import ValidationError
from vyron.logging import get_logger

log = get_logger("vyron.uploads")

MAGIC_SIGNATURES: list[Tuple[bytes, str, str, Optional[int]]] = [
    (b"\xff\xd8\xff", "image/jpeg", "jpg", None),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png", None),
    (b"GIF87a", "image/gif", "gif", None),
    (b"GIF89a", "image/gif", "gif", None),
    (b"RIFF", "image/webp", "webp", 8),  # RIFF....WEBP — check offset 8
]


def sniff_mime(data: bytes) -> Optional[Tuple[str, str]]:
    for signature, mime, ext, offset in MAGIC_SIGNATURES:
        if data.startswith(signature):
            if offset is not None:
                if data[offset : offset + 4] != b"WEBP":
                    continue
            return mime, ext
    return None


def validate_image(data: bytes) -> Tuple[str, str]:
    if not data:
        raise ValidationError("Empty file.", code="UPLOAD_EMPTY")
    if len(data) > settings.upload_max_bytes:
        raise ValidationError(
            f"File exceeds the {settings.upload_max_bytes // (1024 * 1024)}MB limit.", code="UPLOAD_TOO_LARGE"
        )
    sniffed = sniff_mime(data)
    if sniffed is None:
        raise ValidationError("Only JPG, PNG, WebP and GIF images are allowed.", code="UPLOAD_INVALID_TYPE")
    return sniffed


def store_image(data: bytes, folder: str = "uploads") -> str:
    """Store the image and return a public URL (S3 when configured, else local)."""
    mime, ext = validate_image(data)
    filename = f"{uuid.uuid4().hex}.{ext}"

    if settings.s3_configured:
        return _store_s3(data, folder, filename, mime)
    return _store_local(data, folder, filename)


def _store_s3(data: bytes, folder: str, filename: str, mime: str) -> str:
    from minio import Minio

    endpoint = settings.s3_endpoint.replace("https://", "").replace("http://", "").rstrip("/")
    client = Minio(
        endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
        secure=settings.s3_secure,
    )
    if not client.bucket_exists(settings.s3_bucket):
        client.make_bucket(settings.s3_bucket, location=settings.s3_region)
    key = f"{folder.strip('/')}/{filename}"
    client.put_object(settings.s3_bucket, key, io.BytesIO(data), length=len(data), content_type=mime)
    if settings.s3_public_url:
        return f"{settings.s3_public_url.rstrip('/')}/{key}"
    scheme = "https" if settings.s3_secure else "http"
    return f"{scheme}://{endpoint}/{settings.s3_bucket}/{key}"


def _store_local(data: bytes, folder: str, filename: str) -> str:
    directory = os.path.join(settings.local_upload_dir, folder.strip("/"))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    with open(path, "wb") as fh:
        fh.write(data)
    log.info("stored local upload", path=path)
    return f"/{settings.local_upload_dir}/{folder.strip('/')}/{filename}"
