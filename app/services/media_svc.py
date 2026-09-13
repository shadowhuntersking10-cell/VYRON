"""Media library: validated local uploads + records."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.utils.security import new_token

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/svg+xml"}


class MediaError(Exception):
    pass


def save_upload(db: Session, filename: str, content: bytes, mime: str,
                media_type: str = "PRODUCT_IMAGE", alt: str = "",
                game_id: int | None = None, product_id: int | None = None,
                uploaded_by: int | None = None) -> models.Media:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXT or (mime and mime not in ALLOWED_MIME):
        raise MediaError("invalid_file_type")
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes or len(content) == 0:
        raise MediaError("invalid_file_size")
    width = height = 0
    if ext != ".svg":
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(content))
            width, height = img.size
        except Exception:
            raise MediaError("invalid_image")
    media_dir = Path(settings.MEDIA_DIR)
    media_dir.mkdir(parents=True, exist_ok=True)
    safe = f"{new_token(12)}{ext}"
    (media_dir / safe).write_bytes(content)
    row = models.Media(
        filename=filename[:250], path=f"/{settings.MEDIA_DIR}/{safe}",
        mime_type=mime or "", size=len(content), width=width, height=height,
        alt_text=alt or filename, type=media_type, game_id=game_id,
        product_id=product_id, uploaded_by=uploaded_by,
    )
    db.add(row)
    db.flush()
    return row
