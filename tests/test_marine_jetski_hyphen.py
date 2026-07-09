"""Marine signal handles all jet-ski spellings (CodeRabbit nit on #390)."""

from __future__ import annotations

from types import SimpleNamespace

from app.chat.intents.queries import _has_marine_signal
from app.chat.intents.runtime import _marine_first_items


def test_has_marine_signal_jetski_variants() -> None:
    for name in ("Havasu Jet Ski Repair", "Havasu Jet-Ski Repair", "Havasu JetSki Repair"):
        assert _has_marine_signal(SimpleNamespace(provider_name=name, google_primary_category="", category="")) is True
    assert _has_marine_signal(SimpleNamespace(provider_name="Auto Repair LLC", google_primary_category="car_repair", category="Car Repair")) is False


def test_marine_first_items_jetski_hyphen_leads() -> None:
    items = [
        {"name": "Britton's Auto Repair", "category": "Car Repair"},
        {"name": "Lake Jet-Ski Service", "category": "Service"},
    ]
    assert [it["name"] for it in _marine_first_items(items)] == [
        "Lake Jet-Ski Service",
        "Britton's Auto Repair",
    ]
