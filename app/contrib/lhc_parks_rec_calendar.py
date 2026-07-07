"""Vision-LLM calendar/flyer scraper for Lake Havasu City Parks & Recreation.

**Build-only / inert.** This module fetches + parses + (vision-) transcribes and
returns :class:`app.contrib.event_record.EventRecord` objects. It performs no DB
writes and is wired into no orchestrator. The integration step (registering a
source in ``scripts/run_scrapes.py`` / a load branch + the
``parks-rec-scrapes.yml`` cron) is Casey's per-source go/no-go after reviewing
the dry-run output -- see ``docs/source-rollout-checklist.md``.

The gap this closes
-------------------
Parks & Rec publishes its monthly program calendar as a flyer IMAGE (and most
special events as individual flyer images) at ``/185/Parks-Recreation``. Those
carry free/drop-in/special items that appear nowhere else machine-readable: not
in WebTrac (only bookable sections), not in the CivicPlus iCal (meetings + civic
events), not in the Aquatic PDFs. Our text scrapers cannot see them. This reads
the image(s) into structured events via :mod:`app.contrib.vision_calendar`, with
hard guards against hallucinated dates and against duplicating events other
sources already carry.

Dedup (build brief §7)
----------------------
Every row carries a SYNTHETIC per-occurrence stable URL
(``…/185/Parks-Recreation#cal|YYYY-MM-DD|<slug>|HH-MM``) as its ``EventRecord.url``
so re-running the same image is idempotent. At ingest time the rows route through
the shared event funnel (:func:`app.contrib.event_ingest.ingest_event_records`)
whose reconciler + same-day (title, date, venue) guard skip anything WebTrac /
aquatic / civic already carries (those are richer -- they have registration
links/pricing). The calendar scraper contributes only the RESIDUE.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from app.contrib.event_record import EventRecord
from app.contrib.parks_rec_loader import DEFAULT_PROVIDER_WEBTRAC, _all_tags
from app.contrib.vision_calendar import (
    MONTH_INDEX,
    VISION_CALENDAR_TILES,
    ExtractionResult,
    VisionEventRow,
    calendar_system_prompt,
    extract_calendar_tiled,
    extract_flyer_rows,
    extract_validated_rows,
    validate_flyer_image,
    vision_model,
)
from app.utils.slug import slugify

logger = logging.getLogger(__name__)

SOURCE = "parks_rec_calendar"
FLYER_SOURCE = "parks_rec_flyers"

BASE_URL = "https://www.lhcaz.gov"
PARKS_REC_PAGE_URL = "https://www.lhcaz.gov/185/Parks-Recreation"
IMAGE_REPO_PATH = "/ImageRepository/Document"
DEFAULT_VENUE = DEFAULT_PROVIDER_WEBTRAC  # "Lake Havasu City Parks & Recreation"

# Known LHC Parks & Recreation facilities (from the /185 Parks-Recreation page,
# 2026-07-07). A vision row whose "location" is NOT one of these is a mis-mapped
# field — the monthly grid prints the INSTRUCTOR in the cell, so "Jane Camlin"
# landed in the venue slot. Such a row is dropped to DEFAULT_VENUE and quarantined
# rather than published with a person's name (or a bare room like "Kitchen") as
# the "Where". Normalized (lowercase, alnum+space).
PARKS_REC_FACILITIES: frozenset[str] = frozenset({
    "aquatic center", "community center", "recreation center", "rec center",
    "asu fields", "avalon park", "cypress park", "dick samp memorial park",
    "dick samp", "grand island park", "indian bend park", "island ball fields",
    "jack hardie park", "london bridge beach", "mesquite park", "realtor park",
    "robyn parrott park", "rotary community park", "sara park",
    "site six", "site 6",  # Site Six / Windsor Beach — printed both ways
    "wheeler park", "yonder park", "after school program",
})


def _norm_venue(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


# Generic venue vocabulary. A real location names a PLACE — a park, a court, a
# pool, "Site 6", "Kitchen", "Room 153". A mis-mapped instructor ("Jane Camlin")
# contains none of these, which is exactly how we tell a real venue from a
# scrambled person name (INSTRUCTOR_NAMES is only a handful of first names, so a
# name blocklist is unreliable — the positive place-signal is what's robust).
_LOCATION_KEYWORDS: frozenset[str] = frozenset({
    "park", "center", "centre", "beach", "field", "fields", "ballfield",
    "ballfields", "court", "courts", "pool", "gym", "gymnasium", "kitchen",
    "ramp", "site", "room", "rooms", "hall", "studio", "complex", "arena",
    "pavilion", "library", "lot", "aquatic", "recreation", "lanes", "range",
    "annex", "clubhouse", "marina", "dock", "stadium", "track", "trail",
    "plaza", "patio", "lawn", "dome", "gardens", "amphitheater", "amphitheatre",
})
# Explicit room / unit codes: "Room 153", "Rm 12", "#4". (A bare building code
# like "S3" alone is deliberately NOT a location — "S3 - Jane Camlin" stays a
# reject; the real "S3 - Room 153/154" is accepted via the "room" keyword.)
_LOCATION_CODE_RE = re.compile(r"\b(?:room|rm)\s*\d+\b|#\s*\d+")


def is_known_facility(location: str | None, *, strict: bool = False) -> bool:
    """True when ``location`` names a real P&R location.

    Default (ingest guard, #750): accepts a named facility (allowlist), a generic
    venue word (park/court/kitchen/site/room…), or an explicit room/unit code —
    deliberately permissive so a plausible sub-venue isn't over-held. A person's
    name — the mis-mapped-instructor bug — names no place and is rejected.

    ``strict=True`` (the WS6.3 review lint): ONLY a named facility from the
    allowlist (or the default P&R venue) counts. A bare generic word ("Kitchen"),
    a room code ("Room 153"), or an instructor name is *not* a recognized
    facility — it's ambiguous (which kitchen? which room?) and worth a review.
    This never mutates data; it only feeds the review queue."""
    if not location:
        return False
    loc = _norm_venue(location)
    if not loc:
        return False
    default = _norm_venue(DEFAULT_VENUE)
    if loc == default or default in loc:
        return True
    if any(fac in loc for fac in PARKS_REC_FACILITIES):
        return True
    # A short venue that is itself a fragment of a known facility name
    # ("aquatic" ⊂ "aquatic center") is a named facility either way.
    if len(loc) >= 5 and any(loc in fac for fac in PARKS_REC_FACILITIES):
        return True
    if strict:
        # Named facilities only — a generic word / room code / person name is
        # unrecognized and gets a human glance rather than silent publishing.
        return False
    if set(loc.split()) & _LOCATION_KEYWORDS:
        return True
    if _LOCATION_CODE_RE.search(loc):
        return True
    return False


USER_AGENT = "Mozilla/5.0 (compatible; AskHavaBot/1.0; +https://askhava.com)"

# Cap flyer vision calls per run (each flyer ~= one extra call). Override via env.
FLYER_MAX_DEFAULT = 8

# Raw model output is snapshotted here for audit (build brief §6.5) -- never
# overwritten; one file per (document_id, run).
SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "data" / "scrapes" / SOURCE

# A gallery image whose alt/title looks like a monthly calendar flyer.
_CALENDAR_RE = re.compile(r"(?:^|[-_ ])calendar\b", re.IGNORECASE)
# alt/title tokens that mark a gallery image we never treat as an event flyer.
_NON_FLYER_RE = re.compile(
    r"\b(logo|banner|header|footer|slideshow|placeholder|spacer|icon|background)\b",
    re.IGNORECASE,
)
_MONTH_TOKEN_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b", re.IGNORECASE
)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_DOCID_RE = re.compile(r"documentid=(\d+)", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Gallery image references
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GalleryImage:
    """One image discovered in the Parks & Rec gallery."""

    url: str  # absolute ImageRepository (or other) URL
    title: str  # alt/title text, used for calendar detection + month parse
    document_id: str | None
    is_calendar: bool
    month: int | None  # title-derived (calendars only)
    year: int | None
    # True when the image came from a lazy-load attribute (data-delay-load /
    # data-src) -- i.e. a slideshow/gallery image, not page chrome (the homepage
    # logo / search icon / banner all use a plain ``src``).
    is_gallery: bool = False


def _abs_url(src: str) -> str:
    return urljoin(BASE_URL + "/", src.strip())


def _document_id(url: str) -> str | None:
    m = _DOCID_RE.search(url)
    return m.group(1) if m else None


def infer_year_for_month(month: int, *, today: date | None = None) -> int:
    """Pick the year for a month named without one (nearest future-or-current).

    A "June Calendar" with no year means this year if June hasn't passed, else
    next year. Same month as today counts as current (the calendar is live now).
    """
    today = today or date.today()
    if month >= today.month:
        return today.year
    return today.year + 1


def parse_month_year(title: str, *, today: date | None = None) -> tuple[int | None, int | None]:
    """Derive (month, year) from a calendar image title.

    "July-2026-Calendar" -> (7, 2026); "June Calendar" -> (6, inferred year). The
    month is authoritative for month-bounding; a missing year is inferred to the
    nearest future month so we never bound against the wrong year.
    """
    mt = _MONTH_TOKEN_RE.search(title or "")
    if not mt:
        return None, None
    month = MONTH_INDEX.get(mt.group(1).lower()) or MONTH_INDEX.get(mt.group(1).lower()[:3])
    if month is None:
        return None, None
    ym = _YEAR_RE.search(title or "")
    year = int(ym.group(1)) if ym else infer_year_for_month(month, today=today)
    return month, year


def _image_candidates(html: str) -> list[tuple[str, str, bool]]:
    """Return (absolute_url, title, is_gallery) for every image. Tolerant parser.

    ``is_gallery`` is True when the URL came from a lazy-load attribute
    (``data-delay-load`` / ``data-src`` / ``data-original``) -- CivicPlus renders
    slideshow/gallery images that way while page chrome (logo, search icon,
    banner) uses a plain ``src``. Flyer discovery keys on that to avoid hauling in
    nav images. Also catches bare ImageRepository ``<a href>`` links some
    slideshow markup uses (treated as non-gallery: link, not lazy-loaded image).
    """
    try:
        from bs4 import BeautifulSoup
    except Exception:  # pragma: no cover -- bs4 always present in prod
        return []
    soup = BeautifulSoup(html or "", "html.parser")
    out: list[tuple[str, str, bool]] = []
    seen: set[str] = set()
    for img in soup.find_all("img"):
        lazy = (
            img.get("data-delay-load") or img.get("data-src") or img.get("data-original")
        )
        src = lazy or img.get("src") or ""
        if not src or src.strip().lower().startswith("data:"):
            continue
        url = _abs_url(src)
        title = (img.get("alt") or img.get("title") or "").strip()
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append((url, title, bool(lazy)))
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if IMAGE_REPO_PATH.lower() not in href.lower():
            continue
        url = _abs_url(href)
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append((url, (a.get("title") or a.get_text(" ", strip=True) or "").strip(), False))
    return out


def discover_images(html: str, *, today: date | None = None) -> list[GalleryImage]:
    """Parse the gallery into :class:`GalleryImage` refs (calendars flagged)."""
    refs: list[GalleryImage] = []
    for url, title, is_gallery in _image_candidates(html):
        is_cal = bool(_CALENDAR_RE.search(title))
        month = year = None
        if is_cal:
            month, year = parse_month_year(title, today=today)
            # A title that says "calendar" but yields no parseable month is not a
            # month grid we can month-bound -- treat it as a non-calendar image.
            if month is None:
                is_cal = False
        refs.append(
            GalleryImage(
                url=url,
                title=title,
                document_id=_document_id(url),
                is_calendar=is_cal,
                month=month,
                year=year,
                is_gallery=is_gallery,
            )
        )
    return refs


def discover_calendar_images(html: str, *, today: date | None = None) -> list[GalleryImage]:
    """Calendar images only (current + next month, typically 1-2)."""
    return [r for r in discover_images(html, today=today) if r.is_calendar and r.month and r.year]


def discover_flyer_images(html: str, *, today: date | None = None) -> list[GalleryImage]:
    """Event-flyer images: gallery images that are neither calendars nor chrome."""
    out: list[GalleryImage] = []
    for r in discover_images(html, today=today):
        if r.is_calendar:
            continue
        # Gallery (lazy-loaded) images only -- excludes the homepage logo, search
        # icon, and banner (all plain-``src`` chrome that would otherwise pass).
        if not r.is_gallery:
            continue
        if _NON_FLYER_RE.search(r.title):
            continue
        # Only keep real document images (a flyer lives in the ImageRepository).
        if r.document_id is None and IMAGE_REPO_PATH.lower() not in r.url.lower():
            continue
        out.append(r)
    return out


# --------------------------------------------------------------------------- #
# Live fetchers (politeness: descriptive UA, retry envelope, per-id cache)
# --------------------------------------------------------------------------- #
_IMAGE_CACHE: dict[str, tuple[bytes, str]] = {}


def fetch_gallery_html(timeout: float = 60.0) -> str:
    """GET the Parks & Rec gallery HTML; ``""`` on failure (graceful)."""
    try:
        import httpx
    except Exception:  # pragma: no cover
        return ""

    def _inner() -> str:
        with httpx.Client(
            timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:
            resp = client.get(PARKS_REC_PAGE_URL)
            resp.raise_for_status()
            return resp.text

    from app.core.background import with_retry

    return with_retry(_inner, max_attempts=3) or ""


def _is_png_or_jpeg(content: bytes) -> bool:
    return content[:8] == b"\x89PNG\r\n\x1a\n" or content[:3] == b"\xff\xd8\xff"


def _transcode_to_model_readable(content: bytes, mime: str) -> tuple[bytes, str]:
    """Vision models (Ollama / llama.cpp's clip) decode only PNG and JPEG.

    Some sources serve other formats -- e.g. LeadConnector's CDN returns ``f_webp``
    for the Senior Center flyers -- and the model rejects those with a 400
    "Failed to load image or audio file". Transcode anything that isn't already
    PNG/JPEG to PNG via Pillow so every vision source is readable.

    Best-effort: if Pillow is missing or the bytes don't decode, return the
    original unchanged (the caller's guards already fail safe on a bad read).
    """
    if _is_png_or_jpeg(content):
        return content, ("image/png" if content[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg")
    try:
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(content)) as im:
            buf = BytesIO()
            im.convert("RGB").save(buf, format="PNG")
        logger.info("parks_rec_calendar: transcoded %s image -> PNG for the vision model", mime)
        return buf.getvalue(), "image/png"
    except Exception:
        logger.warning("parks_rec_calendar: could not transcode %s image; passing through", mime)
        return content, mime


def fetch_image_bytes(url: str, *, timeout: float = 60.0) -> tuple[bytes, str] | None:
    """GET an image; return (bytes, mime) or ``None``. Cached by URL per run.

    SSRF-guarded (rejects private/reserved hosts) before connecting -- the gallery
    URL is parsed from remote HTML. Non-PNG/JPEG payloads (e.g. WebP) are
    transcoded to PNG so the vision model can decode them.
    """
    cache_key = url.lower()
    if cache_key in _IMAGE_CACHE:
        return _IMAGE_CACHE[cache_key]
    try:
        import httpx

        from app.contrib.url_fetcher import is_blocked_target
    except Exception:  # pragma: no cover
        return None

    blocked, reason = is_blocked_target(url)
    if blocked:
        logger.warning("parks_rec_calendar: blocked image target %s (%s)", url, reason)
        return None

    def _inner() -> tuple[bytes, str]:
        with httpx.Client(
            timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            mime = (resp.headers.get("Content-Type") or "image/png").split(";")[0].strip()
            if not mime.startswith("image/"):
                mime = "image/png"
            return _transcode_to_model_readable(resp.content, mime)

    from app.core.background import with_retry

    result = with_retry(_inner, max_attempts=3)
    if result is None:
        return None
    _IMAGE_CACHE[cache_key] = result
    return result


def _snapshot_raw_output(ref: GalleryImage, raw_text: str) -> None:
    """Append the raw model output for one image to the audit trail (best-effort).

    Never overwrites history (build brief §6.5); one timestamped file per image.
    Failures are swallowed -- the snapshot is an audit nicety, not a gate.
    """
    if not raw_text:
        return
    try:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        doc = ref.document_id or slugify(ref.title) or "image"
        path = SNAPSHOT_DIR / f"{stamp}_{doc}.json"
        import json

        path.write_text(
            json.dumps(
                {
                    "captured_at": stamp,
                    "image_url": ref.url,
                    "document_id": ref.document_id,
                    "title": ref.title,
                    "month": ref.month,
                    "year": ref.year,
                    "raw_model_output": raw_text,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:  # pragma: no cover -- audit nicety
        logger.exception("parks_rec_calendar: failed to snapshot raw output")


# --------------------------------------------------------------------------- #
# Row -> EventRecord
# --------------------------------------------------------------------------- #
def synthetic_url(row: VisionEventRow) -> str:
    """Per-occurrence stable URL (idempotency key) -- build brief §7."""
    slug = slugify(row.title) or "event"
    if row.start_time is not None:
        hhmm = f"{row.start_time.hour:02d}-{row.start_time.minute:02d}"
    else:
        hhmm = "00-00"
    return f"{PARKS_REC_PAGE_URL}#cal|{row.event_date.isoformat()}|{slug}|{hhmm}"


def _compose_description(row: VisionEventRow, *, kind: str) -> str:
    bits: list[str] = [row.title.rstrip(".") + "."]
    if row.location:
        bits.append(f"At {row.location}.")
    if row.audience:
        bits.append(f"For {row.audience}.")
    if row.cost:
        bits.append(f"Cost: {row.cost}.")
    if row.notes:
        bits.append(row.notes.rstrip(".") + ".")
    src = "monthly calendar" if kind == "calendar" else "event flyer"
    bits.append(f"Source: LHC Parks & Rec {src}.")
    return " ".join(bits)


def row_to_event_record(
    row: VisionEventRow,
    ref: GalleryImage,
    *,
    source: str,
    kind: str,
) -> EventRecord:
    """Map a validated vision row to the shared :class:`EventRecord`."""
    tag_text = " ".join(
        x for x in (row.title, row.audience or "", row.notes or "") if x
    )
    # Field-schema guard: the venue must be a real P&R facility. When the model
    # slotted a non-facility (usually the instructor's name — "Jane Camlin") into
    # ``location``, drop it to the default venue AND hold the row: a scrambled
    # venue means the cell's whole field mapping is untrustworthy.
    venue_ok = is_known_facility(row.location)
    hold = row.should_hide or (bool(row.location) and not venue_ok)
    return EventRecord(
        source=source,
        title=row.title,
        start_date=row.event_date,
        start_time=row.start_time,
        end_date=None,
        end_time=row.end_time,
        venue_name=row.location if venue_ok else DEFAULT_VENUE,
        venue_address=None,
        # Synthetic per-occurrence URL = the idempotency key. It carries a #cal
        # fragment so a click still lands on the real Parks & Rec page.
        url=synthetic_url(row),
        description=_compose_description(row, kind=kind),
        tags=_all_tags(tag_text),
        image_url=ref.url,
        raw={
            "source_cell": row.source_cell,
            "confidence": row.confidence,
            "should_hide": hold,
            "calendar_month": ref.month,
            "calendar_year": ref.year,
            "document_id": ref.document_id,
            "kind": kind,
            "vision_model": vision_model(),
        },
    )


def _records_from_result(
    result: ExtractionResult,
    ref: GalleryImage,
    *,
    source: str,
    kind: str,
) -> list[EventRecord]:
    return [
        row_to_event_record(row, ref, source=source, kind=kind) for row in result.rows
    ]


# --------------------------------------------------------------------------- #
# Orchestration (fetch -> vision -> validate -> EventRecords)
# --------------------------------------------------------------------------- #
@dataclass
class CalendarPullResult:
    records: list[EventRecord]
    images_considered: int = 0
    images_extracted: int = 0
    held_low_confidence: int = 0
    dropped_out_of_month: int = 0
    dropped_no_provenance: int = 0
    dropped_bad_title: int = 0
    dropped_bad_date: int = 0
    # Fetched payloads that were not a supported raster image (HTML/PDF/empty/wrong
    # type/oversize) and so were skipped before the vision call (2026-06-25).
    skipped_non_image: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def _accumulate(result_holder: CalendarPullResult, ext: ExtractionResult) -> None:
    s = ext.stats
    result_holder.held_low_confidence += s.held_low_confidence
    result_holder.dropped_out_of_month += s.dropped_out_of_month
    result_holder.dropped_no_provenance += s.dropped_no_provenance
    result_holder.dropped_bad_title += s.dropped_bad_title
    result_holder.dropped_bad_date += s.dropped_bad_date


def pull_calendars(
    *,
    html: str | None = None,
    today: date | None = None,
    self_check: bool = False,
    write_snapshot: bool = True,
    tiles: int | None = None,
    # Test seams -- inject the gallery HTML, image bytes, and recorded model JSON
    # so the suite never makes a live HTTP/LLM call.
    image_bytes_by_url: dict[str, tuple[bytes, str]] | None = None,
    raw_text_by_url: dict[str, str] | None = None,
) -> CalendarPullResult:
    """Discover + transcribe the monthly calendar image(s) into EventRecords.

    ``tiles`` (default ``VISION_CALENDAR_TILES``) splits each calendar image into N
    overlapping bands so a small CPU model isn't asked to emit the whole dense
    grid at once; rows are merged + deduped across tiles. Tiling is a live-image
    path only -- an injected ``raw_text_by_url`` (whole-image recorded JSON) takes
    the un-tiled path so existing fixtures still work.
    """
    if tiles is None:
        tiles = VISION_CALENDAR_TILES
    out = CalendarPullResult(records=[])
    page = html if html is not None else fetch_gallery_html()
    refs = discover_calendar_images(page, today=today)
    out.images_considered = len(refs)
    for ref in refs:
        assert ref.month is not None and ref.year is not None  # discover guarantees
        raw_text = (raw_text_by_url or {}).get(ref.url)
        img: tuple[bytes, str] | None = None
        if raw_text is None:
            img = (image_bytes_by_url or {}).get(ref.url) or fetch_image_bytes(ref.url)
            if img is None:
                out.errors.append(f"image fetch failed: {ref.url}")
                continue
        prompt = calendar_system_prompt(month=ref.month, year=ref.year)
        if raw_text is None and tiles > 1:
            ext = extract_calendar_tiled(
                img[0],
                system_prompt=prompt,
                month=ref.month,
                year=ref.year,
                n_tiles=tiles,
                mime=img[1],
            )
        else:
            ext = extract_validated_rows(
                img[0] if img else b"",
                system_prompt=prompt,
                month=ref.month,
                year=ref.year,
                mime=img[1] if img else "image/png",
                raw_text=raw_text,
                self_check=self_check,
            )
        if raw_text is None and write_snapshot:
            _snapshot_raw_output(ref, ext.raw_text)
        if ext.rows:
            out.images_extracted += 1
        out.records.extend(_records_from_result(ext, ref, source=SOURCE, kind="calendar"))
        _accumulate(out, ext)
    return out


def pull_flyers(
    *,
    html: str | None = None,
    today: date | None = None,
    max_flyers: int | None = None,
    write_snapshot: bool = True,
    image_bytes_by_url: dict[str, tuple[bytes, str]] | None = None,
    raw_text_by_url: dict[str, str] | None = None,
) -> CalendarPullResult:
    """Discover + transcribe individual event-flyer images into EventRecords.

    A flyer has no calendar month grid to bound against; we month-bound each row
    against its own parsed date's month/year (so an out-of-flyer stray date is
    still dropped) and trust the flyer's printed year.
    """
    import os as _os

    if max_flyers is None:
        try:
            max_flyers = int(_os.getenv("PARKS_REC_FLYER_MAX", str(FLYER_MAX_DEFAULT)))
        except ValueError:
            max_flyers = FLYER_MAX_DEFAULT
    out = CalendarPullResult(records=[])
    page = html if html is not None else fetch_gallery_html()
    refs = discover_flyer_images(page, today=today)[: max(0, max_flyers)]
    out.images_considered = len(refs)
    for ref in refs:
        raw_text = (raw_text_by_url or {}).get(ref.url)
        img: tuple[bytes, str] | None = None
        mime = "image/png"
        if raw_text is None:
            img = (image_bytes_by_url or {}).get(ref.url) or fetch_image_bytes(ref.url)
            if img is None:
                out.errors.append(f"image fetch failed: {ref.url}")
                continue
            # Some gallery documentIDs are not raster images (HTML/PDF/empty/wrong
            # type). Validate by magic bytes and skip non-images so we never send a
            # payload the vision API rejects with a 400 "Failed to load image".
            mime, reason = validate_flyer_image(img[0], content_type=img[1])
            if mime is None:
                out.skipped_non_image += 1
                logger.warning(
                    "parks_rec_flyers: skipping non-image flyer %s (%s, %d bytes, ct=%s)",
                    ref.url, reason, len(img[0]), img[1],
                )
                continue
        # A flyer is bounded against the month of whatever date the model reads;
        # run the validate pass per parsed-month so each row self-bounds.
        ext = _extract_flyer(
            img[0] if img else b"",
            mime=mime,
            ref=ref,
            raw_text=raw_text,
        )
        if raw_text is None and write_snapshot:
            _snapshot_raw_output(ref, ext.raw_text)
        if ext.rows:
            out.images_extracted += 1
        out.records.extend(_records_from_result(ext, ref, source=FLYER_SOURCE, kind="flyer"))
        _accumulate(out, ext)
    return out


def _extract_flyer(
    image_bytes: bytes,
    *,
    mime: str,
    ref: GalleryImage,
    raw_text: str | None,
) -> ExtractionResult:
    """Parks & Rec flyer extraction -- delegates to the shared engine entry."""
    return extract_flyer_rows(
        image_bytes,
        context_label="Lake Havasu City Parks & Recreation",
        mime=mime,
        raw_text=raw_text,
    )


__all__ = [
    "DEFAULT_VENUE",
    "FLYER_SOURCE",
    "PARKS_REC_PAGE_URL",
    "SOURCE",
    "CalendarPullResult",
    "GalleryImage",
    "discover_calendar_images",
    "discover_flyer_images",
    "discover_images",
    "fetch_gallery_html",
    "fetch_image_bytes",
    "infer_year_for_month",
    "parse_month_year",
    "pull_calendars",
    "pull_flyers",
    "row_to_event_record",
    "synthetic_url",
]
