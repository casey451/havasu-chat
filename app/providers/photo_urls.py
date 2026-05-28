"""Google Places Photo Media URL construction for provider hero/gallery."""

from __future__ import annotations

import functools
import logging
import os

import sentry_sdk

logger = logging.getLogger(__name__)

_PHOTO_MEDIA_BASE = "https://places.googleapis.com/v1"


def _places_api_key() -> str:
    return (os.getenv("GOOGLE_PLACES_API_KEY") or "").strip()


@functools.lru_cache(maxsize=2048)
def _google_photo_url_cached(ref: str, max_width_px: int) -> str | None:
    key = _places_api_key()
    if not key:
        sentry_sdk.add_breadcrumb(
            category="google_photo_url",
            message="GOOGLE_PLACES_API_KEY unset; photo URL not built",
            level="warning",
            data={"ref": ref},
        )
        return None
    return (
        f"{_PHOTO_MEDIA_BASE}/{ref}/media"
        f"?maxWidthPx={max_width_px}&key={key}"
    )


def google_photo_url(ref: str, *, max_width_px: int = 1200) -> str | None:
    """Build a browser-fetchable Photo Media URL for a Places photo resource name."""
    url = _google_photo_url_cached(ref, max_width_px)
    if url is not None:
        logger.info(
            "google_photo_url.issued",
            extra={"ref": ref, "max_width_px": max_width_px},
        )
    return url
