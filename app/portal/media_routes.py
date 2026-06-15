"""Serve uploaded ad-creative images from the Railway volume.

A bare FastAPI route (not a StaticFiles mount) so the directory doesn't have to
exist at boot and every request is filtered through
:func:`app.portal.creative_store.resolve_media_path`, which blocks path
traversal and only serves allow-listed names.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.portal.creative_store import resolve_media_path

router = APIRouter(tags=["media"])


@router.get("/media/creatives/{filename}", response_model=None)
def serve_creative_image(filename: str) -> FileResponse:
    path = resolve_media_path(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="not_found")
    # Uploaded creatives are immutable (unique generated names) → cache hard.
    return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})
