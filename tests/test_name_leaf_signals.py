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
        None,
        "",
    ],
)
def test_leaf_from_name_negative(name: str | None) -> None:
    assert leaf_from_name(name) is None


def test_fishing_beats_charter_ordering() -> None:
    # a "fishing charter" is a fishing guide, not a generic boat charter
    assert leaf_from_name("Big Bass Fishing Charter") == "fishing-charters-and-guides"
