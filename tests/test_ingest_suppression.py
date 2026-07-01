"""Durable ingest suppression + placeholder-address guard (2026-07-01, item 2)."""

from __future__ import annotations

from app.contrib.ingest_suppression import (
    clean_placeholder_address,
    is_placeholder_address,
    is_suppressed_business,
)

_VISITOR_CENTER = "Go Lake Havasu Visitor Center, 422 English Village | Lake Havasu City, AZ 86403"


def test_suppressed_business_matches_by_normalized_name() -> None:
    assert is_suppressed_business("Wake Surf Adventures")
    assert is_suppressed_business("wake surf adventures")  # case/spacing-insensitive
    assert is_suppressed_business("  Wake  Surf  Adventures ")
    # The real wakesurf shops are NOT suppressed.
    assert not is_suppressed_business("Lake Havasu Wakesurf Co.")
    assert not is_suppressed_business("Wakesurf Havasu")
    assert not is_suppressed_business(None)


def test_placeholder_address_detected_and_cleaned() -> None:
    assert is_placeholder_address(_VISITOR_CENTER)
    assert is_placeholder_address("go lake havasu visitor center")
    assert clean_placeholder_address(_VISITOR_CENTER) is None
    # A real address is preserved untouched.
    real = "2126 McCulloch Blvd N, Lake Havasu City, AZ 86403"
    assert not is_placeholder_address(real)
    assert clean_placeholder_address(real) == real
    assert clean_placeholder_address(None) is None


def test_partner_payload_nulls_placeholder_address() -> None:
    from app.contrib.golakehavasu_partners import PartnerListing, partner_to_entity_payload

    listing = PartnerListing(
        name="Some Tour Operator",
        url="https://golakehavasu.com/x",
        category=None,
        address=_VISITOR_CENTER,
        phone=None,
        website=None,
        description=None,
        lat=None,
        lng=None,
    )
    payload = partner_to_entity_payload(listing, category_slug="on-the-water")
    assert payload.address is None  # placeholder dropped, business kept
