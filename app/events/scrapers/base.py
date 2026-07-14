"""Event ingest clients extending Phase 4 BaseIngestClient (Phase 9b)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, time

import httpx

from app.contrib.ingest_base import BaseIngestClient, EnrichedHit, EntityPayload
from app.contrib.river_scene import USER_AGENT
from app.db import contribution_store as cs
from app.schemas.contribution import ContributionCreate, ContributionSource


def _decode_response(resp: httpx.Response) -> str:
    """Decode an httpx response as text, defaulting to UTF-8 (not latin-1).

    When the server declares an explicit charset in its Content-Type header we
    honor it. When it does not, httpx falls back to a guessed codec that
    corrupts multibyte/emoji characters (e.g. "💋" -> "?"), so we force UTF-8
    with replacement decoding instead.
    """
    if not resp.charset_encoding:
        return resp.content.decode("utf-8", errors="replace")
    return resp.text


@dataclass
class EventPayload(EntityPayload):
    """EntityPayload specialized for entity_type='event' ingest."""

    entity_type: str = "event"
    start_date: date | None = None
    end_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    venue_name: str | None = None
    venue_entity_id: str | None = None
    rrule: str | None = None
    tags: list[str] = field(default_factory=list)
    event_url: str | None = None
    description: str = ""
    source_stable_url: str | None = None
    image_url: str | None = None


class EventIngestClient(BaseIngestClient):
    """Event-source scraper base."""

    scrape_source: str = "operator_backfill"

    def to_entity_payload(self, hit: EnrichedHit) -> EventPayload:  # type: ignore[override]
        return self.to_event_payload(hit)

    def to_event_payload(self, hit: EnrichedHit) -> EventPayload:
        raise NotImplementedError

    def fetch_text(
        self,
        url: str,
        *,
        client: httpx.Client | None = None,
        timeout: float = 60.0,
    ) -> str:
        """GET URL as text with with_retry envelope."""

        def _inner() -> str:
            from app.contrib.url_fetcher import is_blocked_target

            # SSRF guard (audit L1/L2): reject detail URLs parsed from remote
            # vendor content that resolve to private/reserved hosts before we
            # connect. Initial-URL check only — full per-redirect validation
            # would need the manual-redirect loop used in url_fetcher.
            _blocked, _reason = is_blocked_target(url)
            if _blocked:
                raise RuntimeError(f"blocked_ssrf:{_reason}:{url}")
            c = client
            owns = False
            if c is None:
                c = httpx.Client(
                    timeout=timeout,
                    headers={"User-Agent": USER_AGENT},
                    follow_redirects=True,
                )
                owns = True
            try:
                r = c.get(url, timeout=timeout)
                r.raise_for_status()
                return _decode_response(r)
            finally:
                if owns:
                    c.close()

        from app.core.background import with_retry

        result = with_retry(_inner, max_attempts=3)
        if result is None:
            raise RuntimeError(f"fetch failed for {url}")
        return result


def normalize_event_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


# A venue name is a short label ("Lake Havasu Visitor Center", "Buoy 5"), never a
# paragraph of prose. The JSON-LD ``location`` field on some sources leaks
# description-shaped text (a full event blurb, a stringified PostalAddress dict, or
# the organizer suite address block). VENUE_NAME_MAX_LEN caps a real venue name --
# longer than this it is almost certainly description prose and must be rejected
# rather than stored as the venue.
VENUE_NAME_MAX_LEN = 120

# Markers that a candidate venue is actually a stringified dict (PostalAddress leak).
_VENUE_DICT_LEAK_MARKERS = ("@type", "PostalAddress", "{'", '{"')


def is_valid_venue_shape(
    venue: str | None,
    *,
    description: str | None = None,
) -> bool:
    """True when ``venue`` is shaped like a real venue name, not description prose.

    Shape rules (B-08 / E-4): a venue name must be a single short line --
    * non-empty after stripping;
    * no more than :data:`VENUE_NAME_MAX_LEN` characters;
    * contains no blank-line (double-newline) paragraph break;
    * is not a stringified dict (PostalAddress leak);
    * is not the leading slice of the event description (a venue field that just
      echoes the first sentences of the body is the corruption we reject).

    This is the single gate both the scraper (so new rows land clean) and the
    backfill (so existing rows get repaired) use to decide whether a candidate
    venue may be kept.
    """
    v = (venue or "").strip()
    if not v:
        return False
    if len(v) > VENUE_NAME_MAX_LEN:
        return False
    if "\n\n" in v.replace("\r\n", "\n"):
        return False
    if any(marker in v for marker in _VENUE_DICT_LEAK_MARKERS):
        return False
    desc = (description or "").strip()
    if desc:
        # Reject a venue that is just the description prefix (or vice versa): a
        # real venue is not the opening of the event blurb.
        head = desc[: len(v)]
        if v and (v == head or desc.startswith(v) and len(v) >= 40):
            return False
    return True


def clean_venue_shape(
    venue: str | None,
    *,
    description: str | None = None,
) -> str | None:
    """Return ``venue`` when it passes :func:`is_valid_venue_shape`, else ``None``.

    Convenience wrapper for ingest call sites that want "keep it or drop it":
    a description-shaped or dict-leaked venue is dropped to ``None`` so the row
    lands with no fabricated venue rather than a paragraph of prose.
    """
    v = (venue or "").strip() or None
    if v is None:
        return None
    return v if is_valid_venue_shape(v, description=description) else None


def event_payload_to_contribution(
    payload: EventPayload,
    *,
    scrape_source: str,
) -> ContributionCreate:
    """Map :class:`EventPayload` to contributions queue row."""
    url = (payload.event_url or payload.source_stable_url or "").strip()
    if not url:
        raise ValueError("event payload requires event_url or source_stable_url")
    if not payload.start_date:
        raise ValueError("event payload requires start_date")
    # A missing start_time is valid: the events time-label contract
    # (app/events/time_labels.py) renders a NULL start as "Time TBD" rather
    # than fabricating a placeholder. Dropping the event would lose a real
    # listing, so let it through with an unset time.
    name = (payload.name or "").strip()
    if not name:
        raise ValueError("event payload requires name")
    # Prepend metadata header lines the review-queue approver recovers
    # (approve_pending_events._venue_from_notes / _tags_from_notes) and that
    # clean_event_description strips back out of the public body (_METADATA_LINE_RE
    # covers both "venue:" and "categories:"). Without the Categories line a
    # review-gated scraper's ``payload.tags`` are lost on manual approval — the row
    # publishes with tags=[] and no derived Event.category. (The auto-approve path
    # passes ``payload.tags`` straight to approval and is unaffected.)
    notes = (payload.description or "").strip()
    header: list[str] = []
    if payload.venue_name:
        header.append(f"Venue: {payload.venue_name}")
    if payload.tags:
        header.append(f"Categories: {', '.join(payload.tags)}")
    if header:
        notes = ("\n".join(header) + (f"\n\n{notes}" if notes else "")).strip()
    src: ContributionSource = scrape_source  # type: ignore[assignment]
    return ContributionCreate(
        entity_type="event",
        submission_name=name,
        submission_url=url,
        source_url=cs.normalize_submission_url(url),
        submission_category_hint=scrape_source,
        submission_notes=notes or None,
        event_date=payload.start_date,
        event_end_date=payload.end_date,
        event_time_start=payload.start_time,
        event_time_end=payload.end_time,
        source=src,
    )


__all__ = [
    "VENUE_NAME_MAX_LEN",
    "EventIngestClient",
    "EventPayload",
    "clean_venue_shape",
    "event_payload_to_contribution",
    "is_valid_venue_shape",
    "normalize_event_title",
]
