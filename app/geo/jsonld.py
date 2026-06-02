"""schema.org JSON-LD builders for AI answer-engine visibility (GEO/AEO).

LANE B6 (Phase B). Pure functions that turn a catalog row (Provider / Event)
or verified FAQ content into a schema.org dict, ready to be JSON-serialized
into a ``<script type="application/ld+json">`` block.

Hard rule: **emit only fields we actually have.** Every helper omits a key
rather than guessing or fabricating a value. A Provider with no rating gets
no ``aggregateRating``; an Event with no location gets no ``location``. The
unit tests in ``tests/test_geo_jsonld.py`` assert both that required keys are
present and that absent catalog fields are omitted.

These builders never touch the DB and never raise on a sparse row — they read
attributes defensively so a half-populated Provider still yields a valid
(smaller) node.
"""

from __future__ import annotations

import json
from typing import Any

# schema.org context string reused by every node.
_SCHEMA_CONTEXT = "https://schema.org"


def _clean_str(value: Any) -> str | None:
    """Return a stripped non-empty string, or None.

    Anything falsy / non-string-coercible collapses to None so the caller can
    decide to omit the key entirely (never emit an empty string).
    """
    if value is None:
        return None
    try:
        text = str(value).strip()
    except Exception:
        return None
    return text or None


def provider_to_jsonld(provider: Any, *, url: str | None = None) -> dict[str, Any]:
    """Build a schema.org ``LocalBusiness`` node from a Provider row.

    Required: ``@context``, ``@type``, ``name`` (name falls back to an empty
    string only if the row truly has none — callers should not emit a node for
    a nameless provider).

    Optional, emitted only when present on the row:
      * ``telephone``           <- ``provider.phone``
      * ``url``                 <- ``url`` arg (canonical profile URL)
      * ``address``             <- ``provider.address`` (PostalAddress)
      * ``aggregateRating``     <- only if ``google_rating`` is present; review
                                   count is added only if it is present too.
    """
    node: dict[str, Any] = {
        "@context": _SCHEMA_CONTEXT,
        "@type": "LocalBusiness",
    }
    name = _clean_str(getattr(provider, "provider_name", None))
    if name is not None:
        node["name"] = name

    phone = _clean_str(getattr(provider, "phone", None))
    if phone is not None:
        node["telephone"] = phone

    page_url = _clean_str(url)
    if page_url is not None:
        node["url"] = page_url

    website = _clean_str(getattr(provider, "website", None))
    if website is not None:
        node["sameAs"] = [website]

    address = _clean_str(getattr(provider, "address", None))
    if address is not None:
        node["address"] = {
            "@type": "PostalAddress",
            "streetAddress": address,
        }

    rating = getattr(provider, "google_rating", None)
    if rating is not None:
        try:
            rating_value = float(rating)
        except (TypeError, ValueError):
            rating_value = None
        if rating_value is not None:
            agg: dict[str, Any] = {
                "@type": "AggregateRating",
                "ratingValue": rating_value,
            }
            review_count = getattr(provider, "google_review_count", None)
            if review_count is not None:
                try:
                    rc = int(review_count)
                except (TypeError, ValueError):
                    rc = None
                if rc is not None and rc > 0:
                    agg["reviewCount"] = rc
            node["aggregateRating"] = agg

    return node


def event_to_jsonld(event: Any, *, url: str | None = None) -> dict[str, Any]:
    """Build a schema.org ``Event`` node from an Event row.

    Required: ``@context``, ``@type``, ``name``.
    Optional, emitted only when present:
      * ``startDate`` <- ISO-8601 combining ``event.date`` + ``event.start_time``
                         (falls back to date-only if there is no start_time).
      * ``location``  <- ``Place`` built from ``event.location_name``.
      * ``url``       <- ``url`` arg (canonical permalink).
      * ``endDate``   <- ISO date when ``event.end_date`` is present.
    """
    node: dict[str, Any] = {
        "@context": _SCHEMA_CONTEXT,
        "@type": "Event",
    }
    name = _clean_str(getattr(event, "title", None))
    if name is not None:
        node["name"] = name

    start_date = _event_start_iso(event)
    if start_date is not None:
        node["startDate"] = start_date

    end_date = getattr(event, "end_date", None)
    if end_date is not None:
        try:
            node["endDate"] = end_date.isoformat()
        except Exception:
            pass

    location_name = _clean_str(getattr(event, "location_name", None))
    if location_name is not None:
        node["location"] = {
            "@type": "Place",
            "name": location_name,
        }

    page_url = _clean_str(url)
    if page_url is not None:
        node["url"] = page_url

    return node


def _event_start_iso(event: Any) -> str | None:
    """ISO-8601 start timestamp from an Event's date + start_time, defensively."""
    day = getattr(event, "date", None)
    if day is None:
        return None
    start_time = getattr(event, "start_time", None)
    try:
        if start_time is not None:
            from datetime import datetime as _dt

            return _dt.combine(day, start_time).isoformat()
        return day.isoformat()
    except Exception:
        return None


def faqs_to_jsonld(faqs: list[dict[str, str]]) -> dict[str, Any] | None:
    """Build a schema.org ``FAQPage`` node from verified Q&A pairs.

    Each item must carry a non-empty ``q`` and ``a``; malformed entries are
    skipped. Returns ``None`` when no valid pairs remain so the caller can omit
    the block entirely rather than emit an empty FAQPage.
    """
    entities: list[dict[str, Any]] = []
    for faq in faqs or []:
        if not isinstance(faq, dict):
            continue
        question = _clean_str(faq.get("q"))
        answer = _clean_str(faq.get("a"))
        if question is None or answer is None:
            continue
        entities.append(
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": answer,
                },
            }
        )
    if not entities:
        return None
    return {
        "@context": _SCHEMA_CONTEXT,
        "@type": "FAQPage",
        "mainEntity": entities,
    }


def item_list_to_jsonld(
    items: list[dict[str, str]], *, name: str | None = None
) -> dict[str, Any] | None:
    """Build a schema.org ``ItemList`` node for a category page's listings.

    ``items`` is a list of ``{"name": ..., "url": ...}`` dicts. Entries with no
    name are skipped; ``url`` is included only when present. Returns ``None``
    when there are no usable items (so an empty category omits the node).
    """
    elements: list[dict[str, Any]] = []
    position = 1
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_name = _clean_str(item.get("name"))
        if item_name is None:
            continue
        element: dict[str, Any] = {
            "@type": "ListItem",
            "position": position,
            "name": item_name,
        }
        item_url = _clean_str(item.get("url"))
        if item_url is not None:
            element["url"] = item_url
        elements.append(element)
        position += 1
    if not elements:
        return None
    node: dict[str, Any] = {
        "@context": _SCHEMA_CONTEXT,
        "@type": "ItemList",
        "itemListElement": elements,
    }
    list_name = _clean_str(name)
    if list_name is not None:
        node["name"] = list_name
    return node


def to_script_block(node: dict[str, Any] | None) -> str:
    """Serialize a JSON-LD node to a ``<script type="application/ld+json">``.

    Returns an empty string for a ``None`` node so templates can unconditionally
    inline the result. Uses ``ensure_ascii=False`` for readable UTF-8 and slash
    escaping so ``</script>`` can never appear verbatim in the payload.
    """
    if not node:
        return ""
    payload = json.dumps(node, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/ld+json">{payload}</script>'
