"""Owner-uploaded photos: R2 storage, Pillow processing, upload API (Phase 2B.1).

(schemas.py — PhotoListItem/PhotoUploadResponse — and r2_client.delete_object
were deleted 2026-07-02: the routes return raw dicts and photo deletion is a
status-only soft delete that never touches R2.)
"""

from __future__ import annotations

from app.photos.processor import process_uploaded_photo
from app.photos.r2_client import build_public_url, get_r2_client, upload_bytes
from app.photos.sweep import run_stuck_photo_sweep

__all__ = [
    "build_public_url",
    "get_r2_client",
    "process_uploaded_photo",
    "run_stuck_photo_sweep",
    "upload_bytes",
]
