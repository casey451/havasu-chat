"""Vision-LLM flyer reader for the Lake Havasu Senior Center (build-only, inert).

The senior center posts dated specials as FLYER IMAGES on its Current Events page
(and two monthly IMAGE calendars on the home/seniors page). The text parser can't
read images, so today those specials are transcribed BY HAND into
``app.events.senior_center.CURATED_SPECIAL_EVENTS``. This is the same generic
vision engine (:mod:`app.contrib.vision_calendar`) pointed at the senior center --
a thin adapter, not a rewrite -- and is the path to retiring that manual table.

**Build-only.** Returns ``senior``-tagged :class:`EventRecord` objects; performs
no DB writes, has its own CLI, and does NOT touch the live senior loader
(``scripts/load_senior_center.py``). Turning it on (and deciding whether it
supersedes ``CURATED_SPECIAL_EVENTS``) is Casey's go/no-go after a dry-run review.

Discovery note: the Current Events page hosts ~37 images on the LeadConnector CDN
with NO alt text, so flyers can't be told from decorative photos in the markup.
We don't need to: a decorative photo yields no dated row carrying a ``source_cell``
(provenance guard) and is dropped. We cap the vision calls (``SENIOR_FLYER_MAX``)
so a blind scan stays cheap; the engine's guards filter the non-events.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from app.contrib.event_record import EventRecord
from app.contrib.parks_rec_loader import _all_tags
from app.contrib.vision_calendar import (
    ExtractionResult,
    VisionEventRow,
    extract_flyer_rows,
    validate_flyer_image,
)
from app.events.senior_center import (
    CALENDAR_IMAGES,
    EVENTS_URL,
    SENIOR_TAGS,
    VENUE_ADDRESS,
    VENUE_NAME,
    fetch_events_page,
)
from app.utils.slug import slugify

logger = logging.getLogger(__name__)

SOURCE = "senior_center_flyers"
CONTEXT_LABEL = "the Lake Havasu Senior Center"
SENIOR_FLYER_MAX_DEFAULT = 12

# The Current Events page serves flyers through the LeadConnector image proxy;
# the two monthly grids on the home page live on the same CDN.
_CDN_MARKERS = ("leadconnectorhq.com", "filesafe.space", "storage.googleapis.com")


def _is_cdn_image(url: str) -> bool:
    u = (url or "").lower()
    return u.startswith("http") and any(m in u for m in _CDN_MARKERS)


def discover_flyer_images(html: str) -> list[str]:
    """Return the LeadConnector-CDN image URLs on the Current Events page.

    No alt/title to filter on, so this returns every CDN image (deduped, order
    preserved); the caller caps the count and the engine's guards drop the
    non-event (decorative) images.
    """
    try:
        from bs4 import BeautifulSoup
    except Exception:  # pragma: no cover
        return []
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[str] = []
    seen: set[str] = set()
    for img in soup.find_all("img"):
        src = (img.get("src") or img.get("data-src") or "").strip()
        if not src or src.lower().startswith("data:") or not _is_cdn_image(src):
            continue
        if src in seen:
            continue
        seen.add(src)
        out.append(src)
    return out


def senior_image_urls(html: str) -> list[str]:
    """Flyer images on the Current Events page + the two monthly calendar grids.

    The monthly grids (lunch menu, weekly activities) carry no dated event rows,
    so the engine returns nothing usable from them (the weekly activities are
    already seeded as recurring rows); they're included per the brief but cost a
    capped vision call at most and drop out cleanly.
    """
    urls = discover_flyer_images(html)
    for grid in CALENDAR_IMAGES.values():
        if grid not in urls:
            urls.append(grid)
    return urls


def _synthetic_url(row: VisionEventRow) -> str:
    slug = slugify(row.title) or "event"
    hhmm = (
        f"{row.start_time.hour:02d}-{row.start_time.minute:02d}"
        if row.start_time is not None
        else "00-00"
    )
    return f"{EVENTS_URL}#flyer|{row.event_date.isoformat()}|{slug}|{hhmm}"


def _description(row: VisionEventRow) -> str:
    bits: list[str] = [row.title.rstrip(".") + "."]
    if row.audience:
        bits.append(f"For {row.audience}.")
    if row.cost:
        bits.append(f"Cost: {row.cost}.")
    if row.notes:
        bits.append(row.notes.rstrip(".") + ".")
    bits.append(f"At the {VENUE_NAME}. Source: senior center flyer.")
    return " ".join(bits)


def _tags(row: VisionEventRow) -> list[str]:
    text = " ".join(x for x in (row.title, row.audience or "", row.notes or "") if x)
    tags = list(SENIOR_TAGS)
    for t in _all_tags(text):
        if t not in tags:
            tags.append(t)
    return tags


def row_to_event_record(row: VisionEventRow, image_url: str) -> EventRecord:
    """Map a validated flyer row to a ``senior``-tagged :class:`EventRecord`."""
    return EventRecord(
        source=SOURCE,
        title=row.title,
        start_date=row.event_date,
        start_time=row.start_time,
        end_date=None,
        end_time=row.end_time,
        venue_name=row.location or VENUE_NAME,
        venue_address=VENUE_ADDRESS,
        url=_synthetic_url(row),
        description=_description(row),
        tags=_tags(row),
        image_url=image_url,
        raw={
            "source_cell": row.source_cell,
            "confidence": row.confidence,
            "should_hide": row.should_hide,
            "kind": "senior_flyer",
        },
    )


@dataclass
class SeniorFlyerPullResult:
    records: list[EventRecord]
    images_considered: int = 0
    images_extracted: int = 0
    held_low_confidence: int = 0
    dropped_out_of_month: int = 0
    dropped_no_provenance: int = 0
    dropped_bad_title: int = 0
    dropped_bad_date: int = 0
    # Fetched payloads that were not a supported raster image (skipped pre-call).
    skipped_non_image: int = 0
    errors: list[str] = field(default_factory=list)


def _accumulate(out: SeniorFlyerPullResult, ext: ExtractionResult) -> None:
    s = ext.stats
    out.held_low_confidence += s.held_low_confidence
    out.dropped_out_of_month += s.dropped_out_of_month
    out.dropped_no_provenance += s.dropped_no_provenance
    out.dropped_bad_title += s.dropped_bad_title
    out.dropped_bad_date += s.dropped_bad_date


def pull_senior_flyers(
    *,
    html: str | None = None,
    max_flyers: int | None = None,
    # Test seams -- inject the page HTML, image bytes, and recorded model JSON.
    image_bytes_by_url: dict[str, tuple[bytes, str]] | None = None,
    raw_text_by_url: dict[str, str] | None = None,
) -> SeniorFlyerPullResult:
    """Discover + transcribe senior-center flyer images into senior EventRecords."""
    if max_flyers is None:
        try:
            max_flyers = int(os.getenv("SENIOR_FLYER_MAX", str(SENIOR_FLYER_MAX_DEFAULT)))
        except ValueError:
            max_flyers = SENIOR_FLYER_MAX_DEFAULT
    out = SeniorFlyerPullResult(records=[])
    page = html if html is not None else fetch_events_page()
    urls = senior_image_urls(page)[: max(0, max_flyers)]
    out.images_considered = len(urls)
    for url in urls:
        raw_text = (raw_text_by_url or {}).get(url)
        img: tuple[bytes, str] | None = None
        mime = "image/png"
        if raw_text is None:
            img = (image_bytes_by_url or {}).get(url) or _fetch_image(url)
            if img is None:
                out.errors.append(f"image fetch failed: {url}")
                continue
            # Skip non-image payloads (the CDN proxy can return HTML/other) so we
            # never trip the vision API's 400 "Failed to load image".
            mime, reason = validate_flyer_image(img[0], content_type=img[1])
            if mime is None:
                out.skipped_non_image += 1
                logger.warning(
                    "senior_center_flyers: skipping non-image %s (%s, %d bytes, ct=%s)",
                    url, reason, len(img[0]), img[1],
                )
                continue
        ext = extract_flyer_rows(
            img[0] if img else b"",
            context_label=CONTEXT_LABEL,
            mime=mime,
            raw_text=raw_text,
        )
        if ext.rows:
            out.images_extracted += 1
        out.records.extend(row_to_event_record(r, url) for r in ext.rows)
        _accumulate(out, ext)
    return out


def _fetch_image(url: str) -> tuple[bytes, str] | None:
    """Reuse the Parks & Rec image fetcher (SSRF-guarded, retry envelope, cache)."""
    from app.contrib.lhc_parks_rec_calendar import fetch_image_bytes

    return fetch_image_bytes(url)


__all__ = [
    "SOURCE",
    "SeniorFlyerPullResult",
    "discover_flyer_images",
    "pull_senior_flyers",
    "row_to_event_record",
    "senior_image_urls",
]
