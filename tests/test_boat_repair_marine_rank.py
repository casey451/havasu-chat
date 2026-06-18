"""#2 — boat_repair de-ranks auto/RV shops below genuine marine shops."""

from __future__ import annotations

from types import SimpleNamespace

from app.chat.intents.queries import _has_marine_signal, _marine_first


def _p(name: str, gcat: str = "", cat: str = ""):
    return SimpleNamespace(provider_name=name, google_primary_category=gcat, category=cat)


def test_marine_signal_detection() -> None:
    assert _has_marine_signal(_p("JandJ Performance and Marine Service & Repair")) is True
    assert _has_marine_signal(_p("Carburetion Specialties Boat Service / Repair")) is True
    assert _has_marine_signal(_p("BlackSheep RV LLC", gcat="car_repair", cat="Car Repair")) is False
    assert _has_marine_signal(_p("Britton's Auto Truck & RV Repair", cat="Car Repair")) is False


def test_marine_first_orders_marine_above_auto() -> None:
    rows = [
        _p("BlackSheep RV LLC", "car_repair", "Car Repair"),
        _p("Britton's Auto Truck & RV Repair", "car_repair", "Car Repair"),
        _p("Desert RV Werks RV Repair Mobile", "car_repair", "Car Repair"),
        _p("JandJ Performance and Marine Service & Repair", "services", "Service"),
    ]
    ordered = [p.provider_name for p in _marine_first(rows)]
    # The marine shop leads; auto/RV shops fall below it (order preserved within groups).
    assert ordered[0] == "JandJ Performance and Marine Service & Repair"
    assert ordered[1:] == [
        "BlackSheep RV LLC",
        "Britton's Auto Truck & RV Repair",
        "Desert RV Werks RV Repair Mobile",
    ]


def test_marine_first_is_stable_within_groups() -> None:
    rows = [
        _p("Marine A", cat="marine"),
        _p("Auto A", cat="Car Repair"),
        _p("Marine B", "boat_dealer"),
        _p("Auto B", cat="Car Repair"),
    ]
    assert [p.provider_name for p in _marine_first(rows)] == [
        "Marine A",
        "Marine B",
        "Auto A",
        "Auto B",
    ]
