"""Media uploads: validation + local storage (S3-ready architecture)."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import MediaFile

ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
}
ALLOWED_KINDS = {"game_logo", "product", "avatar", "listing", "banner", "attachment"}


def storage_dir() -> Path:
    d = Path(settings.STORAGE_LOCAL_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


async def save_upload(db: AsyncSession, file: UploadFile, *, kind: str, owner_id: int | None) -> MediaFile:
    if kind not in ALLOWED_KINDS:
        raise ValueError("bad_kind")
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_MIME:
        raise ValueError("bad_file_type")
    data = await file.read()
    max_bytes = settings.STORAGE_MAX_FILE_MB * 1024 * 1024
    if not data or len(data) > max_bytes:
        raise ValueError("bad_file_size")
    # Extension from validated MIME, never from user filename (path safety).
    name = f"{kind}_{uuid.uuid4().hex}{ALLOWED_MIME[mime]}"
    dest = storage_dir() / name
    dest.write_bytes(data)
    width = height = None
    try:
        from PIL import Image  # type: ignore

        with Image.open(dest) as im:
            width, height = im.size
    except Exception:
        pass
    rec = MediaFile(owner_id=owner_id, kind=kind, filename=file.filename or name,
                    path=str(dest), url=f"/uploads/{name}", mime=mime,
                    size_bytes=len(data), width=width, height=height)
    db.add(rec)
    await db.flush()
    return rec
