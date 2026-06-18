"""Recover a real event description from the source's own detail page.

Aggregator index/listing pages (notably AllEvents.in) frequently carry only a
title + date in their JSON-LD, leaving the body empty — which previously became a
synthesised placeholder on our event detail page. This module fetches the event's
*own* page and pulls the genuine description from, in order of preference:

1. schema.org ``Event.description`` JSON-LD,
2. the ``og:description`` Open Graph meta tag,
3. the ``<meta name="description">`` tag.

The result is run through :func:`clean_event_description`, so metadata/placeholder
bodies still collapse to "". Network is dependency-injected (``fetch_text``) so the
behaviour is fully unit-testable offline, mirroring the scraper test style used
across ``app/contrib``.
"""

from __future__ import annotations

import html as html_mod
import json
import logging
from typing import Callable

from bs4 import BeautifulSoup

from app.contrib.event_record import EventRecord, _iter_jsonld_nodes, _type_is_event
from app.events.description_clean import clean_event_description, valid_event_url

logger = logging.getLogger(__name__)


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


def enrich_event_descriptions(
    records: list[EventRecord],
    *,
    fetch_text: Callable[[str], str | None],
    max_fetch: int = 250,
) -> int:
    """Fill empty descriptions in-place by fetching each event's detail page.

    Only events whose description is currently empty/placeholder (per
    :func:`clean_event_description`) and that have a valid http(s) ``url`` are
    fetched, capped at ``max_fetch``. Returns the number of records enriched.
    Network errors are swallowed per-record so a batch never fails wholesale.
    """
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
