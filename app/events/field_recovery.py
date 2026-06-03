"""Recover scrambled event venue/address/image from a corrupted description (ED-1).

Some ingested events — notably the Go Lake Havasu JSON-LD feed — landed with their
fields scrambled: ``location_name`` holds a paragraph of description prose (or a
stringified ``PostalAddress`` dict), while the *real* venue/address sits inside the
description body on a ``LOCATION:`` line. The description also carries ingest noise:
a ``Date:``/``Time:`` header (redundant with the structured columns), a dead
``Click here to sign up!`` CTA, an ``Image: https://…`` line, and a trailing
``Stay Connected``.

This module is the single deterministic recovery pass used by **both** the ingest
scraper (so new rows land clean) and the one-time backfill (so existing rows get
repaired). It is pure (no DB/ORM) and conservative: it only overrides
``location_name`` when the stored value is detectably corrupt, so it never clobbers
a good venue.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A ``LOCATION:`` line inside the description holds the authoritative venue/address.
_LOCATION_RE = re.compile(r"^[ \t]*LOCATION:[ \t]*(.+?)[ \t]*$", re.IGNORECASE | re.MULTILINE)
# An ``Image: https://…`` line carries the event image URL.
_IMAGE_RE = re.compile(r"^[ \t]*Image:[ \t]*(https?://\S+)[ \t]*$", re.IGNORECASE | re.MULTILINE)
# Redundant ``Date:`` / ``Time:`` header lines (structured columns already hold these).
_DATE_HEADER_RE = re.compile(r"^[ \t]*Date:[ \t]*.+$", re.IGNORECASE | re.MULTILINE)
_TIME_HEADER_RE = re.compile(r"^[ \t]*Time:[ \t]*.+$", re.IGNORECASE | re.MULTILINE)
# Dead CTA and trailing social boilerplate.
_SIGNUP_RE = re.compile(r"^[ \t]*Click here to sign up!?[ \t]*$", re.IGNORECASE | re.MULTILINE)
_STAY_CONNECTED_RE = re.compile(r"^[ \t]*Stay Connected[ \t]*$", re.IGNORECASE | re.MULTILINE)
# A bare leading ``Venue: …`` prefix that base.event_payload_to_contribution prepends.
_VENUE_PREFIX_RE = re.compile(r"^[ \t]*Venue:[ \t]*(.+)$", re.IGNORECASE)
# Address segment heuristic: the first comma-part that begins with a street number.
_STREET_NUMBER_RE = re.compile(r"^\d+\s")
# Markers that a ``location_name`` is actually a stringified dict (PostalAddress leak).
_DICT_LEAK_MARKERS = ("@type", "PostalAddress", "{'", '{"')


@dataclass(frozen=True)
class RecoveredFields:
    """Result of a recovery pass. ``changed`` is True when anything was rewritten."""

    location_name: str
    address: str | None
    image_url: str | None
    description: str
    changed: bool


def _looks_like_prose(value: str) -> bool:
    """Heuristic: a ``location_name`` that is really description prose, not a venue.

    Real venue names are short and don't read like sentences. We treat a value as
    prose when it is long *and* sentence-like (ends/contains terminal punctuation),
    or when it is a stringified dict.
    """
    v = (value or "").strip()
    if not v:
        return False
    if any(marker in v for marker in _DICT_LEAK_MARKERS):
        return True
    if len(v) > 80 and re.search(r"[.!?]", v):
        return True
    return False


def _split_venue_address(location: str) -> tuple[str | None, str | None]:
    """Split a flat ``LOCATION:`` string into (venue, address).

    ``"Mohave College, Building 200, 1977 W Acoma Blvd, Lake Havasu City, AZ 86403"``
    → venue ``"Mohave College, Building 200"``, address ``"1977 W Acoma Blvd, …"``.
    The street address starts at the first comma-segment beginning with a number.

    - No street number found → ``(whole, None)`` (all venue, no parseable address).
    - Street number leads → ``(None, whole)`` (pure address, no venue name).
    """
    parts = [p.strip() for p in location.split(",") if p.strip()]
    if not parts:
        return location.strip() or None, None
    street_idx = next((i for i, p in enumerate(parts) if _STREET_NUMBER_RE.match(p)), None)
    if street_idx is None:
        return ", ".join(parts), None
    if street_idx == 0:
        return None, ", ".join(parts)
    venue = ", ".join(parts[:street_idx])
    address = ", ".join(parts[street_idx:])
    return venue, address


def _clean_description(description: str) -> str:
    """Strip ingest noise (headers, LOCATION/Image lines, dead CTA, boilerplate)."""
    text = description or ""
    for pattern in (
        _DATE_HEADER_RE,
        _TIME_HEADER_RE,
        _LOCATION_RE,
        _IMAGE_RE,
        _SIGNUP_RE,
        _STAY_CONNECTED_RE,
    ):
        text = pattern.sub("", text)
    # Collapse 3+ blank lines to a single blank line; trim each line's trailing space.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def recover_event_fields(
    *,
    location_name: str | None,
    description: str | None,
) -> RecoveredFields:
    """Best-effort recovery of venue/address/image from a scrambled event.

    Conservative: ``location_name`` is only replaced when the stored value is
    detectably corrupt (empty, prose, or a dict leak) AND a ``LOCATION:`` line is
    available to recover from. The description is always de-noised.
    """
    raw_loc = (location_name or "").strip()
    raw_desc = description or ""

    # A leading "Venue: …" prefix (from event_payload_to_contribution) — peel it off
    # the description's first line so it doesn't read as body text.
    first_nl = raw_desc.find("\n")
    first_line = raw_desc[: first_nl if first_nl >= 0 else len(raw_desc)]
    prefix_match = _VENUE_PREFIX_RE.match(first_line)
    prefixed_venue = prefix_match.group(1).strip() if prefix_match else None
    if prefix_match:
        raw_desc = raw_desc[first_nl + 1 :] if first_nl >= 0 else ""

    loc_match = _LOCATION_RE.search(raw_desc)
    img_match = _IMAGE_RE.search(raw_desc)
    recovered_location = loc_match.group(1).strip() if loc_match else None
    image_url = img_match.group(1).strip() if img_match else None

    venue: str
    address: str | None = None
    loc_corrupt = (not raw_loc) or _looks_like_prose(raw_loc)

    if recovered_location:
        rv, address = _split_venue_address(recovered_location)
        # When the stored location is corrupt, prefer the recovered venue; if the
        # LOCATION line was a pure street address (no venue name), use it whole.
        venue = (rv or recovered_location) if loc_corrupt else raw_loc
    elif prefixed_venue and loc_corrupt:
        venue = prefixed_venue
    elif loc_corrupt:
        venue = "Location TBD"
    else:
        venue = raw_loc

    cleaned_desc = _clean_description(raw_desc)

    changed = (
        venue != raw_loc
        or cleaned_desc != (description or "").strip()
        or image_url is not None
    )
    return RecoveredFields(
        location_name=venue,
        address=address,
        image_url=image_url,
        description=cleaned_desc,
        changed=changed,
    )
