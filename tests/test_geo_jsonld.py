"""LANE B6 — schema.org JSON-LD builders (pure functions).

Asserts: (1) emitted JSON-LD parses and carries the required @type/keys;
(2) absent catalog fields are OMITTED, not guessed; (3) builders never
fabricate values beyond the supplied row.
"""

from __future__ import annotations

import json
from datetime import date, time
from types import SimpleNamespace

from app.geo.jsonld import (
    event_to_jsonld,
    faqs_to_jsonld,
    item_list_to_jsonld,
    provider_to_jsonld,
    to_script_block,
)


def _provider(**over) -> SimpleNamespace:
    base = dict(
        provider_name="Hangar 24 Taproom",
        phone="(928) 846-4447",
        address="5600 Hwy 95 N #6, Lake Havasu City, AZ 86404",
        website="https://hangar24.example",
        google_rating=4.8,
        google_review_count=284,
    )
    base.update(over)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------
# LocalBusiness
# --------------------------------------------------------------------------
def test_provider_localbusiness_has_required_keys() -> None:
    node = provider_to_jsonld(_provider(), url="https://x/provider/hangar-24")
    assert node["@context"] == "https://schema.org"
    assert node["@type"] == "LocalBusiness"
    assert node["name"] == "Hangar 24 Taproom"
    assert node["telephone"] == "(928) 846-4447"
    assert node["url"] == "https://x/provider/hangar-24"
    assert node["address"]["@type"] == "PostalAddress"
    assert node["address"]["streetAddress"].startswith("5600 Hwy 95")
    assert node["aggregateRating"]["@type"] == "AggregateRating"
    assert node["aggregateRating"]["ratingValue"] == 4.8
    assert node["aggregateRating"]["reviewCount"] == 284


def test_provider_omits_rating_when_absent() -> None:
    node = provider_to_jsonld(_provider(google_rating=None, google_review_count=None))
    assert "aggregateRating" not in node


def test_provider_rating_without_review_count_omits_review_count() -> None:
    node = provider_to_jsonld(_provider(google_review_count=None))
    assert node["aggregateRating"]["ratingValue"] == 4.8
    assert "reviewCount" not in node["aggregateRating"]


def test_provider_zero_review_count_is_omitted() -> None:
    node = provider_to_jsonld(_provider(google_review_count=0))
    assert "reviewCount" not in node["aggregateRating"]


def test_provider_omits_absent_phone_address_url() -> None:
    node = provider_to_jsonld(
        _provider(phone=None, address=None, website=None),
        url=None,
    )
    assert node["name"] == "Hangar 24 Taproom"
    for absent in ("telephone", "address", "url", "sameAs"):
        assert absent not in node


def test_provider_blank_strings_are_omitted() -> None:
    node = provider_to_jsonld(_provider(phone="   ", address=""))
    assert "telephone" not in node
    assert "address" not in node


# --------------------------------------------------------------------------
# Event
# --------------------------------------------------------------------------
def _event(**over) -> SimpleNamespace:
    base = dict(
        title="The SpongeBob Musical",
        date=date(2026, 6, 5),
        start_time=time(19, 0),
        end_date=None,
        location_name="GraceArts Live",
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_event_has_required_keys() -> None:
    node = event_to_jsonld(_event(), url="https://x/events/123")
    assert node["@type"] == "Event"
    assert node["name"] == "The SpongeBob Musical"
    assert node["startDate"] == "2026-06-05T19:00:00"
    assert node["location"]["@type"] == "Place"
    assert node["location"]["name"] == "GraceArts Live"
    assert node["url"] == "https://x/events/123"


def test_event_omits_location_when_absent() -> None:
    node = event_to_jsonld(_event(location_name=None))
    assert "location" not in node


def test_event_start_date_falls_back_to_date_only() -> None:
    node = event_to_jsonld(_event(start_time=None))
    assert node["startDate"] == "2026-06-05"


def test_event_omits_start_date_when_no_date() -> None:
    node = event_to_jsonld(_event(date=None))
    assert "startDate" not in node


# --------------------------------------------------------------------------
# FAQPage
# --------------------------------------------------------------------------
def test_faqpage_structure() -> None:
    node = faqs_to_jsonld(
        [
            {"q": "Is there a taco place?", "a": "Yes, Dos Amigos Taco's."},
            {"q": "Coffee?", "a": "The Human Bean."},
        ]
    )
    assert node["@type"] == "FAQPage"
    assert len(node["mainEntity"]) == 2
    first = node["mainEntity"][0]
    assert first["@type"] == "Question"
    assert first["name"] == "Is there a taco place?"
    assert first["acceptedAnswer"]["@type"] == "Answer"
    assert first["acceptedAnswer"]["text"] == "Yes, Dos Amigos Taco's."


def test_faqpage_none_when_empty_or_malformed() -> None:
    assert faqs_to_jsonld([]) is None
    assert faqs_to_jsonld([{"q": "", "a": ""}]) is None
    assert faqs_to_jsonld([{"q": "Only question"}]) is None


# --------------------------------------------------------------------------
# ItemList
# --------------------------------------------------------------------------
def test_item_list_positions_and_urls() -> None:
    node = item_list_to_jsonld(
        [
            {"name": "Place A", "url": "https://x/provider/a"},
            {"name": "Place B"},
        ],
        name="Eat & Drink",
    )
    assert node["@type"] == "ItemList"
    assert node["name"] == "Eat & Drink"
    els = node["itemListElement"]
    assert els[0]["position"] == 1
    assert els[0]["url"] == "https://x/provider/a"
    assert els[1]["position"] == 2
    assert "url" not in els[1]


def test_item_list_none_when_no_named_items() -> None:
    assert item_list_to_jsonld([]) is None
    assert item_list_to_jsonld([{"url": "https://x"}]) is None


# --------------------------------------------------------------------------
# Script block serialization
# --------------------------------------------------------------------------
def test_to_script_block_parses_as_json() -> None:
    node = provider_to_jsonld(_provider())
    block = to_script_block(node)
    assert block.startswith('<script type="application/ld+json">')
    inner = block[len('<script type="application/ld+json">') : -len("</script>")]
    parsed = json.loads(inner.replace("<\\/", "</"))
    assert parsed["@type"] == "LocalBusiness"


def test_to_script_block_empty_for_none() -> None:
    assert to_script_block(None) == ""
    assert to_script_block({}) == ""


def test_to_script_block_escapes_closing_script() -> None:
    node = provider_to_jsonld(_provider(provider_name="Bad </script> Co"))
    block = to_script_block(node)
    inner = block[len('<script type="application/ld+json">') : -len("</script>")]
    assert "</script>" not in inner
