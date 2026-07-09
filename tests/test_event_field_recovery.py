"""ED-1 — recover scrambled event venue/address/image from corrupted descriptions."""

from __future__ import annotations

from app.events.field_recovery import recover_event_fields

# Verbatim shape of the live "Moonshot" Go Lake Havasu event (the audit's example):
# location_name held description prose; the real venue sat on a LOCATION: line.
MOONSHOT_DESC = (
    "Date: June 03, 2026\n"
    "Time: 09:00 - 15:30\n"
    "\n"
    "Hey Lake Havasu risk takers, business leaders, and entrepreneurs!\n"
    "\n"
    "Do you have a \"moonshot\" business idea or an existing business you'd like to "
    "expand? If you answered YES, join us for Moonshot's 7th Annual Pitch Competition!\n"
    "\n"
    "LOCATION: Mohave College, Building 200, 1977 W Acoma Blvd, Lake Havasu City, AZ 86403\n"
    "\n"
    "SCHEDULE 9:00 AM: Welcome + Pitch Worksheet Workshop\n"
    "\n"
    "Click here to sign up!\n"
    "\n"
    "The Moonshot Rural AZ Pitch Competition is a 501c3 nonprofit program.\n"
    "\n"
    "Stay Connected"
)
MOONSHOT_LOC = (
    "Do you have a \"moonshot\" business idea or an existing business you'd like to "
    "expand? Or maybe you have a product or business idea scribbled down on a napkin?!"
)


def test_recovers_venue_and_address_from_location_line() -> None:
    out = recover_event_fields(location_name=MOONSHOT_LOC, description=MOONSHOT_DESC)
    assert out.changed
    assert out.location_name == "Mohave College, Building 200"
    assert out.address == "1977 W Acoma Blvd, Lake Havasu City, AZ 86403"


def test_cleans_description_noise() -> None:
    out = recover_event_fields(location_name=MOONSHOT_LOC, description=MOONSHOT_DESC)
    assert "LOCATION:" not in out.description
    assert "Date:" not in out.description
    assert "Time: 09:00" not in out.description
    assert "Click here to sign up" not in out.description
    assert "Stay Connected" not in out.description
    # Real prose is preserved.
    assert "Hey Lake Havasu risk takers" in out.description
    assert "Moonshot's 7th Annual Pitch Competition" in out.description
    # No run of 3+ newlines remains.
    assert "\n\n\n" not in out.description


def test_recovers_image_url() -> None:
    desc = MOONSHOT_DESC + "\nImage: https://www.golakehavasu.com/imager/x.jpg"
    out = recover_event_fields(location_name=MOONSHOT_LOC, description=desc)
    assert out.image_url == "https://www.golakehavasu.com/imager/x.jpg"
    assert "Image:" not in out.description


def test_good_venue_is_preserved() -> None:
    # A clean, short venue must not be clobbered even if a LOCATION: line exists.
    out = recover_event_fields(
        location_name="London Bridge Resort",
        description="A fun night out.\nLOCATION: 1477 Queens Bay, Lake Havasu City, AZ 86403",
    )
    assert out.location_name == "London Bridge Resort"
    # Address is still recovered from the LOCATION line for downstream use.
    assert out.address == "1477 Queens Bay, Lake Havasu City, AZ 86403"


def test_empty_location_falls_back_to_tbd() -> None:
    out = recover_event_fields(location_name="", description="Just a description, no location.")
    assert out.location_name == "Location TBD"
    assert out.address is None


def test_stringified_dict_leak_is_treated_as_corrupt() -> None:
    leak = "{'@type': 'PostalAddress', 'streetAddress': '210 Swanson Ave'}"
    out = recover_event_fields(
        location_name=leak,
        description="Live music tonight.\nLOCATION: Shugrue's, 1425 McCulloch Blvd N, Lake Havasu City, AZ 86403",
    )
    assert out.location_name == "Shugrue's"
    assert out.address == "1425 McCulloch Blvd N, Lake Havasu City, AZ 86403"


def test_venue_prefix_is_peeled_from_description() -> None:
    # base.event_payload_to_contribution prepends "Venue: …" — it must not read as body.
    out = recover_event_fields(
        location_name="",
        description="Venue: The Nautical Beachfront Resort\n\nSunset social hour.",
    )
    assert out.location_name == "The Nautical Beachfront Resort"
    assert "Venue:" not in out.description
    assert "Sunset social hour." in out.description


def test_clean_event_is_unchanged() -> None:
    out = recover_event_fields(
        location_name="Rotary Park",
        description="Community cleanup day. Bring gloves.",
    )
    assert not out.changed
    assert out.location_name == "Rotary Park"
    assert out.description == "Community cleanup day. Bring gloves."


# ── visitor-center placeholder override (2026-07-08 re-audit) ──────────────────
def test_visitor_center_placeholder_is_overridden_when_prose_names_a_venue() -> None:
    # A GLH event tagged to the shared visitor-center placeholder whose LOCATION:
    # line names the real venue (Bunco @ Mudshark). The placeholder is a real-
    # shaped string, but it's a stand-in the prose should override.
    out = recover_event_fields(
        location_name="Go Lake Havasu Visitor Center",
        description=(
            "Red, White and Blue Bunco Party!\n"
            "LOCATION: Mudshark Public House, 210 Swanson Ave, Lake Havasu City, AZ 86403"
        ),
    )
    assert out.changed
    assert out.location_name == "Mudshark Public House"
    assert out.address == "210 Swanson Ave, Lake Havasu City, AZ 86403"


def test_visitor_center_placeholder_is_kept_when_no_real_venue_recovered() -> None:
    # A genuine visitor-center event (no better venue in the prose) keeps its
    # label — the placeholder must never be blanked to "Location TBD".
    out = recover_event_fields(
        location_name="Go Lake Havasu Visitor Center",
        description="Stop by the visitor center for maps and local tips.",
    )
    assert out.location_name == "Go Lake Havasu Visitor Center"
