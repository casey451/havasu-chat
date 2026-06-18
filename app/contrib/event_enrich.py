"""Recover real event fields from the source's own detail page.

Aggregator index/listing pages (notably AllEvents.in) frequently carry only a
title + date in their JSON-LD, leaving the body empty, the start time at
midnight (a date-only artifact), and the venue as a bare street address. That
previously rendered as a placeholder description, a missing time, and a generic
location on our event detail page.

This module fetches the event's *own* page and recovers, from its schema.org
``Event`` JSON-LD (falling back to og/meta for the description):

* the real **description**,
* the real **start/end time** (when ours is missing or midnight),
* the real **venue** — preferring the organizer name (e.g. "Lighthouse Lounge")
  when the location is only a street address,
* the event **image**, and the organizer (kept in ``raw`` for downstream
  music/nightlife tagging).

Network is dependency-injected (``fetch_text``) so behaviour is fully
unit-testable offline, matching the scraper test style across ``app/contrib``.
"""

from __future__ import annotations

import html as html_mod
import json
import logging
import re
from datetime import time as _time
from typing import Callable

from bs4 import BeautifulSoup

from app.contrib.event_record import (
    EventRecord,
    _iter_jsonld_nodes,
    _type_is_event,
    parse_jsonld_events,
)
from app.events.description_clean import clean_event_description, valid_event_url

logger = logging.getLogger(__name__)

_MIDNIGHT = _time(0, 0)
_STREET_ADDRESS_RE = re.compile(r"^\s*\d")  # "317 S Lake Havasu Ave" -> street, not a venue name


def _jsonld_description(soup: BeautifulSoup) -> str:
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        for node in _iter_jsonld_nodes(data):
            if isinstance(node, dict) and _type_is_event(node):
                d = node.get("description")
                if isinstance(d, str) and d.strip():
                    return html_mod.unescape(d)
    return ""


def _meta_content(soup: BeautifulSoup, **attrs: str) -> str:
    tag = soup.find("meta", attrs=attrs)
    if tag is not None:
        val = tag.get("content")
        if isinstance(val, str) and val.strip():
            return html_mod.unescape(val)
    return ""


def description_from_detail_html(html_text: str) -> str:
    """Best-effort real description from a detail page's HTML (cleaned, or "")."""
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    candidate = (
        _jsonld_description(soup)
        or _meta_content(soup, property="og:description")
        or _meta_content(soup, name="description")
    )
    return clean_event_description(candidate)


def record_from_detail_html(html_text: str, *, source: str) -> EventRecord | None:
    """Parse the detail page's schema.org Event JSON-LD into an EventRecord.

    Returns the first Event node (the page's own event), or ``None`` when the
    page has no parseable Event JSON-LD.
    """
    if not html_text:
        return None
    records = parse_jsonld_events(html_text, source=source)
    return records[0] if records else None


def best_venue_name(venue_name: str | None, organizer: str | None) -> str:
    """Pick the most useful venue label.

    AllEvents stores the street address in ``location.name`` and the actual
    venue (a bar/lounge/etc.) as the ``organizer`` — so when the location is a
    bare street address, prefer the organizer name.
    """
    vn = (venue_name or "").strip()
    org = (organizer or "").strip()
    if vn and not _STREET_ADDRESS_RE.match(vn):
        return vn
    if org:
        return org
    return vn


_GENERIC_VENUES = {"", "lake havasu city", "lake havasu"}


def _needs_enrichment(rec: EventRecord) -> bool:
    """A record is thin if it lacks real prose, a real time, or a real venue."""
    if not clean_event_description(rec.description):
        return True
    if rec.start_time is None or rec.start_time == _MIDNIGHT:
        return True
    if (rec.venue_name or "").strip().lower() in _GENERIC_VENUES:
        return True
    return False


def enrich_event_records(
    records: list[EventRecord],
    *,
    fetch_text: Callable[[str], str | None],
    source: str = "allevents",
    max_fetch: int = 250,
) -> int:
    """Fill thin records in-place from their detail pages. Returns count enriched.

    Only fills fields that are currently missing/thin — a real value the index
    already provided is never overwritten. Network errors are swallowed
    per-record so a batch never fails wholesale.
    """
    enriched = 0
    fetched = 0
    for rec in records:
        if fetched >= max_fetch:
            break
        if not _needs_enrichment(rec):
            continue
        url = valid_event_url(rec.url)
        if not url:
            continue
        fetched += 1
        try:
            html_text = fetch_text(url)
        except Exception as e:  # noqa: BLE001 — best-effort enrichment
            logger.debug("enrich fetch failed for %s: %s", url, e)
            continue
        if not html_text:
            continue
        detail = record_from_detail_html(html_text, source=source)
        changed = False
        # No Event JSON-LD: still try to recover a description from og/meta.
        if detail is None:
            if not clean_event_description(rec.description):
                better = description_from_detail_html(html_text)
                if better:
                    rec.description = better
                    enriched += 1
            continue

        # Description — only when ours is empty/placeholder. Prefer the
        # JSON-LD body, fall back to og:description/meta.
        if not clean_event_description(rec.description):
            better = clean_event_description(detail.description) or description_from_detail_html(html_text)
            if better:
                rec.description = better
                changed = True

        # Start/end time — only when ours is missing or midnight (date-only).
        if (rec.start_time is None or rec.start_time == _MIDNIGHT) and detail.start_time and detail.start_time != _MIDNIGHT:
            rec.start_time = detail.start_time
            if detail.start_date:
                rec.start_date = detail.start_date
            if detail.end_time:
                rec.end_time = detail.end_time
            if detail.end_date:
                rec.end_date = detail.end_date
            changed = True

        # Venue — only when ours is missing/generic; prefer organizer over a
        # bare street address.
        organizer = (detail.raw or {}).get("organizer")
        if (rec.venue_name or "").strip().lower() in _GENERIC_VENUES:
            vn = best_venue_name(detail.venue_name, organizer)
            if vn and vn.strip().lower() not in _GENERIC_VENUES:
                rec.venue_name = vn
                if detail.venue_address:
                    rec.venue_address = detail.venue_address
                changed = True

        # Image + organizer provenance (organizer powers music/nightlife tagging).
        if not rec.image_url and detail.image_url:
            rec.image_url = detail.image_url
        if organizer and not (rec.raw or {}).get("organizer"):
            rec.raw = {**(rec.raw or {}), "organizer": organizer}

        if changed:
            enriched += 1
    return enriched


# Description-only enrichment: fills empty/placeholder bodies (og/meta fallback
# included), leaving time/venue untouched. Kept for callers that only want the
# body; ``enrich_event_records`` is the full recovery used by the scrapers.
def enrich_event_descriptions(
    records: list[EventRecord],
    *,
    fetch_text: Callable[[str], str | None],
    max_fetch: int = 250,
) -> int:
    enriched = 0
    fetched = 0
    for rec in records:
        if fetched >= max_fetch:
            break
        if clean_event_description(rec.description):
            continue
        url = valid_event_url(rec.url)
        if not url:
            continue
        fetched += 1
        try:
            html_text = fetch_text(url)
        except Exception as e:  # noqa: BLE001 — best-effort enrichment
            logger.debug("enrich fetch failed for %s: %s", url, e)
            continue
        if not html_text:
            continue
        better = description_from_detail_html(html_text)
        if better:
            rec.description = better
            enriched += 1
    return enriched
