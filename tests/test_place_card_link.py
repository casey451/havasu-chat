"""Place cards link OUT to an official website when the entity has one.

A Provider-less place entity (Aquatic Center, library) has no /provider/{slug}
page; when it carries a website contact point the leaf card links to it, else it
renders non-linking. Locks ``_place_website`` selection + ``_place_card`` output.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.categories.leaf_pages import _place_card, _place_website


def _entity(name: str, contacts: list[tuple[str, str]], *, district: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        location=SimpleNamespace(district=district, city="Lake Havasu City"),
        contact_points=[SimpleNamespace(kind=k, value=v) for k, v in contacts],
    )


def test_place_website_picks_first_web_contact() -> None:
    e = _entity(
        "Lake Havasu City Aquatic Center",
        [("phone", "928-555-0100"), ("website", "https://lhcaz.gov/aquatic")],
    )
    assert _place_website(e) == "https://lhcaz.gov/aquatic"


def test_place_website_accepts_web_and_url_kinds() -> None:
    assert _place_website(_entity("X", [("web", "https://a.test")])) == "https://a.test"
    assert _place_website(_entity("Y", [("url", "https://b.test")])) == "https://b.test"


def test_place_website_empty_when_no_web_contact() -> None:
    assert _place_website(_entity("Z", [("phone", "928-555-0000")])) == ""
    assert _place_website(_entity("Z", [])) == ""


def test_place_card_carries_website_and_no_slug() -> None:
    card = _place_card(
        _entity(
            "Lake Havasu City Aquatic Center",
            [("website", "https://lhcaz.gov/aquatic")],
            district="Uptown",
        )
    )
    assert card["slug"] is None
    assert card["website"] == "https://lhcaz.gov/aquatic"
    assert card["name"] == "Lake Havasu City Aquatic Center"
    assert card["area"] == "Uptown"


def test_place_card_without_website_is_blank_string() -> None:
    card = _place_card(_entity("Rotary Park", []))
    assert card["slug"] is None
    assert card["website"] == ""
