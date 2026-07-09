"""Tests for name-signal → leaf rules (charters / tours / fishing / paddle)."""

from __future__ import annotations

import pytest

from app.contrib.name_leaf_signals import leaf_from_name


@pytest.mark.parametrize(
    "name,leaf",
    [
        # Fishing guides (beat generic charter)
        ("Havasu Net 'Em Guide Service", "fishing-charters-and-guides"),
        ("Ron's Fishing Guide Service", "fishing-charters-and-guides"),
        ("Capt Kenne Fishing Charter", "fishing-charters-and-guides"),
        # Captained tours / charters
        ("Captain Bob's Boat Adventures", "boat-tours-and-charters"),
        ("Lake Havasu Luxury Charter LLC", "boat-tours-and-charters"),
        ("Sunset Cruise Havasu", "boat-tours-and-charters"),
        ("London Bridge Jet Boat Tour", "boat-tours-and-charters"),
        ("Havasu Tiki Tours", "boat-tours-and-charters"),
        ("Rubba Duck Safari", "boat-tours-and-charters"),
        ("Havasu Excursions", "boat-tours-and-charters"),
        # Kayak / paddle
        ("Havasu Kayak & Paddle", "kayak-and-paddle"),
        ("Standup Paddle Havasu", "kayak-and-paddle"),
        ("Bluewater Canoe Rentals", "kayak-and-paddle"),
        # Jet ski / motorised watersports
        ("Havasu Jet Ski Rentals", "jet-ski-and-watersports"),
        ("WaveRunner Adventures", "jet-ski-and-watersports"),
        ("Parasail Havasu", "jet-ski-and-watersports"),
        # Marinas
        ("Havasu Springs Marina", "marinas-and-launch-ramps"),
        ("Site Six Boat Launch", "marinas-and-launch-ramps"),
        # Off-road / UTV rentals (Session 6b): vehicle token + rental token, or a
        # standalone recreational-rental term (rzr / side-by-side).
        ("Desert Experience UTV Offroad Rentals", "utv-and-offroad-rentals"),
        ("Wet Monkey Powersport Rentals", "utv-and-offroad-rentals"),
        ("Havasu RZR Rentals", "utv-and-offroad-rentals"),
        ("Lake Havasu Side by Side Adventures", "utv-and-offroad-rentals"),
        ("Havasu Dirt Bike Rentals", "utv-and-offroad-rentals"),
        # Golf carts (sales/service/rental hub — any golf-cart operator).
        ("Premier Golf Cars", "golf-carts"),
        ("Havasu Golf Cart Rentals", "golf-carts"),
        # Bikes / e-bikes.
        ("Havasu E-Bikes", "bikes-and-e-bikes"),
        ("Cycle Therapy Bike & E-bike Shop", "bikes-and-e-bikes"),
        ("Lake Havasu Bike Rentals", "bikes-and-e-bikes"),
    ],
)
def test_leaf_from_name_positive(name: str, leaf: str) -> None:
    assert leaf_from_name(name) == leaf


@pytest.mark.parametrize(
    "name",
    [
        # Negative guard: education, not a boat charter
        "Telesis Charter School",
        "Havasu Charter Academy",
        # No water signal at all
        "Main Street Diner",
        "Desert Sun Salon",
        "Havasu Auto Repair",
        # "tour" without a water anchor is not a boat tour here
        "Historic Downtown Walking Tour",
        # Land-rental negatives (Session 6b): conservative anchors mean a dealer /
        # trailhead / gym stays put rather than being pulled into a rental leaf.
        "Havasu Powersports",          # dealer — off-road vehicle, no rental token
        "SARA Park OHV Trailhead",     # trails — "ohv" but no rental language
        "Lake Havasu Bike & Fitness",  # bike, but no rental/shop context (gym-ish)
        "Riverside Motorcycle Repair",  # motorcycle, not a pedal/e-bike
        "Desert Dirt Bike Tours",      # off-road motorbike, but no rental token
        "Havasu Golf Course Pro Shop",  # golf course != golf cart
        None,
        "",
    ],
)
def test_leaf_from_name_negative(name: str | None) -> None:
    assert leaf_from_name(name) is None


def test_fishing_beats_charter_ordering() -> None:
    # a "fishing charter" is a fishing guide, not a generic boat charter
    assert leaf_from_name("Big Bass Fishing Charter") == "fishing-charters-and-guides"


def test_powersports_dealer_vs_rental_ordering() -> None:
    # The same "powersport" token routes on the presence of a rental anchor:
    # a rental goes to the rentals leaf, a bare dealer stays unmatched (falls
    # through to the Google-type / legacy dealer path).
    assert leaf_from_name("Wet Monkey Powersport Rentals") == "utv-and-offroad-rentals"
    assert leaf_from_name("Havasu Powersports") is None
