"""C10 — binary ad-creative image storage on a Railway persistent volume.

Merchants can upload a creative image instead of supplying a hosted URL. Files
land in a directory on a Railway volume (so they survive redeploys) and are
served back through :func:`resolve_media_path` at ``/media/creatives/<name>``.

Storage location (first that applies):
  1. ``CREATIVE_UPLOAD_DIR``           — explicit override (used by tests).
  2. ``$RAILWAY_VOLUME_MOUNT_PATH/creatives`` — the attached Railway volume.
  3. ``<project_root>/data/creatives`` — local-dev fallback (``data/`` is
     gitignored).

Safety: the stored filename is generated server-side (uuid + a validated
extension), never derived from the client filename, and :func:`resolve_media_path`
refuses anything that isn't a bare ``<token>.<ext>`` in the allow-list — so the
serving route can't be walked out of the directory.
"""

from __future__ import annotations

import io
import os
import re
from pathlib import Path
from uuid import uuid4

from PIL import Image

from app.bootstrap_env import ensure_dotenv_loaded

MEDIA_URL_PREFIX = "/media/creatives"
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB

# content-type → on-disk extension. Pillow format names are mapped separately.
_MIME_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
_PIL_FORMAT_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}
ALLOWED_MIME_TYPES = frozenset(_MIME_EXT)
_SAFE_NAME = re.compile(r"^[a-f0-9]{32}\.(jpg|png|webp|gif)$")


class CreativeImageError(ValueError):
    """Raised when an uploaded file is missing, too big, or not a real image."""


def creative_upload_dir() -> Path:
    """The directory creative images are stored in (created if absent)."""
    ensure_dotenv_loaded()
    explicit = (os.environ.get("CREATIVE_UPLOAD_DIR") or "").strip()
    if explicit:
        base = Path(explicit)
    else:
        volume = (os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "").strip()
        if volume:
            base = Path(volume) / "creatives"
        else:
            base = Path(__file__).resolve().parents[2] / "data" / "creatives"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _sniff_image_mime(content: bytes) -> str | None:
    """Return the real image MIME by decoding with Pillow, or ``None`` if the
    bytes are not a supported image. Does not trust the client content-type."""
    try:
        with Image.open(io.BytesIO(content)) as img:
            fmt = img.format or ""
    except Exception:  # noqa: BLE001 — any decode failure means "not an image"
        return None
    return _PIL_FORMAT_MIME.get(fmt.upper())


def save_creative_image(content: bytes, *, declared_mime: str | None = None) -> str:
    """Validate ``content`` is a real, supported, size-bounded image and write it
    under a generated name. Returns the public media path
    (``/media/creatives/<name>``). Raises :class:`CreativeImageError` otherwise.

    The ``declared_mime`` (browser-supplied) is only an early reject; the stored
    extension comes from what Pillow actually decoded, so a mislabeled file can't
    smuggle a wrong extension.
    """
    if not content:
        raise CreativeImageError("empty_file")
    if len(content) > MAX_IMAGE_BYTES:
        raise CreativeImageError("file_too_large")
    if declared_mime and declared_mime not in ALLOWED_MIME_TYPES:
        raise CreativeImageError("unsupported_mime_type")

    real_mime = _sniff_image_mime(content)
    if real_mime is None:
        raise CreativeImageError("not_an_image")

    ext = _MIME_EXT[real_mime]
    name = f"{uuid4().hex}.{ext}"
    (creative_upload_dir() / name).write_bytes(content)
    return f"{MEDIA_URL_PREFIX}/{name}"


def resolve_media_path(filename: str) -> Path | None:
    """Map a requested media filename to a real file on disk, or ``None``.

    Returns ``None`` for anything that isn't a bare allow-listed name (blocks
    path traversal) or that doesn't exist — the route turns that into a 404.
    """
    if not _SAFE_NAME.match(filename or ""):
        return None
    path = creative_upload_dir() / filename
    if not path.is_file():
        return None
    return path
