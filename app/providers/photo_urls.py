"""Google Places Photo Media URL construction and ref resolution."""

from __future__ import annotations

import functools
import logging
import os
import re
from typing import Iterator, Protocol

import httpx
import sentry_sdk

from app.contrib.rate_limiter import GOOGLE_PLACES_LIMITER

logger = logging.getLogger(__name__)

_PHOTO_MEDIA_BASE = "https://places.googleapis.com/v1"
_PLACES_PHOTO_REF_RE = re.compile(r"^places/[^/]+/photos/.+")


class _GooglePhotoProvider(Protocol):
    google_photo_urls: list[str] | list[str | None] | None
    google_photo_refs: list[str] | None


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


def _is_renderable_http_url(candidate: object) -> bool:
    return isinstance(candidate, str) and (
        candidate.startswith("http://") or candidate.startswith("https://")
    )


def iter_renderable_google_photos(provider: _GooglePhotoProvider) -> Iterator[str]:
    """Yield card/hero-ready Google photo URLs for ``provider``.

    Order:

    1. ``google_photo_urls`` -- backfilled, already-resolved URLs. Any
       renderable http(s) entries are yielded in stored order. If at
       least one entry is renderable, the refs fallback is skipped (the
       backfill is authoritative once it ran).
    2. ``google_photo_refs`` -- fallback when the urls column is empty,
       missing, or yields zero renderable entries (e.g. backfill never
       ran, or every resolved url was ``None`` after a credential
       outage). Renderable http(s) ref entries are yielded directly;
       raw ``places/.../photos/...`` resource names are upgraded to a
       Photo Media URL via :func:`google_photo_url` and yielded when
       an API key is configured.

    Hoisting the raw-ref upgrade into this helper restores symmetry
    between the provider profile path (``derive_hero_photo`` /
    ``derive_gallery``) and the home/categories path
    (``_provider_image_url``). Before this change, only home/categories
    upgraded raw refs (PR #43); the profile path silently dropped them
    after PR #41 collapsed the two branches. A provider whose ingest
    backfill never landed -- e.g. ``GOOGLE_PLACES_API_KEY`` was unset
    during ingest -- now renders on every surface that the backfill
    eventually fixes, not just home/categories.
    """
    yielded_any = False
    urls = getattr(provider, "google_photo_urls", None)
    if urls:
        for candidate in urls:
            if _is_renderable_http_url(candidate):
                yielded_any = True
                yield candidate
    if yielded_any:
        return
    for candidate in provider.google_photo_refs or []:
        if not isinstance(candidate, str):
            continue
        cleaned = candidate.strip()
        if not cleaned:
            continue
        if _is_renderable_http_url(cleaned):
            yield cleaned
            continue
        # Raw Places resource name -- upgrade via the PR #37 helper.
        # Returns ``None`` when no API key is configured; we then fall
        # through to the next candidate (the previous behavior dropped
        # raw refs entirely on the profile surface).
        upgraded = google_photo_url(cleaned)
        if upgraded:
            yield upgraded


def first_renderable_google_photo(provider: _GooglePhotoProvider) -> str | None:
    """First card/hero-ready Google photo URL for a provider."""
    for url in iter_renderable_google_photos(provider):
        return url
    return None


@functools.lru_cache(maxsize=2048)
def _resolve_photo_ref_cached(ref: str, max_width: int) -> str | None:
    key = _places_api_key()
    if not key:
        sentry_sdk.add_breadcrumb(
            category="google_photo_url",
            message="GOOGLE_PLACES_API_KEY unset; photo ref not resolved",
            level="warning",
            data={"ref": ref},
        )
        return None

    media_url = (
        f"{_PHOTO_MEDIA_BASE}/{ref}/media"
        f"?maxWidthPx={max_width}&key={key}"
    )
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = GOOGLE_PLACES_LIMITER.call_with_retry(
                lambda: client.get(media_url)
            )
    except httpx.HTTPError:
        logger.warning(
            "resolve_photo_ref.transport_error",
            extra={"ref": ref},
            exc_info=True,
        )
        return None

    if response.status_code != 200:
        logger.warning(
            "resolve_photo_ref.http_error",
            extra={"ref": ref, "status": response.status_code},
        )
        return None

    final = str(response.url)
    if not _is_renderable_http_url(final):
        return None
    return final


def resolve_photo_ref(ref: str, *, max_width: int = 1200) -> str | None:
    """Resolve a Places photo resource name to a long-lived Google media URL.

    Calls ``places.photos.getMedia`` (via GET on the media endpoint), follows
    the redirect, and returns the canonical ``https://lh3.googleusercontent.com/``
    URL. Returns ``None`` for malformed refs, missing API key, or API errors.
    """
    cleaned = (ref or "").strip()
    if not cleaned:
        return None
    if _is_renderable_http_url(cleaned):
        return cleaned
    if not _PLACES_PHOTO_REF_RE.match(cleaned):
        return None

    resolved = _resolve_photo_ref_cached(cleaned, max_width)
    if resolved is not None:
        logger.info(
            "resolve_photo_ref.resolved",
            extra={"ref": cleaned, "max_width": max_width},
        )
    return resolved


def resolve_photo_refs(
    refs: list[str] | None, *, max_width: int = 1200
) -> list[str | None] | None:
    """Resolve each ref in parallel to ``google_photo_urls`` column shape."""
    if not refs:
        return None
    return [resolve_photo_ref(ref, max_width=max_width) for ref in refs]
