"""#2 follow-up — marine-first reorder of the FINAL component items.

build_business_list re-sorts provider rows by relevance/rating, undoing the
upstream run_query reorder. _marine_first_items re-applies marine-first on the
built component items (boat_repair only), where it survives.
"""

from __future__ import annotations

from app.chat.intents.runtime import _marine_first_items


def test_marine_items_lead_after_rating_sort() -> None:
    # Order as build_business_list leaves it: descending review_count (the prod bug).
    items = [
        {"name": "BlackSheep RV LLC", "category": "Car Repair", "review_count": 149},
        {"name": "Britton's Auto Truck & RV Repair", "category": "Car Repair", "review_count": 100},
        {"name": "Carburetion Specialties Boat Service / Repair", "category": "Car Repair", "review_count": 35},
        {"name": "Desert RV Werks RV Repair Mobile", "category": "Car Repair", "review_count": 13},
        {"name": "JandJ Performance and Marine Service & Repair", "category": "Service", "review_count": 9},
    ]
    out = [it["name"] for it in _marine_first_items(items)]
    # The two marine shops (Boat / Marine in name) lead; auto/RV follow.
    assert out[0] == "Carburetion Specialties Boat Service / Repair"
    assert out[1] == "JandJ Performance and Marine Service & Repair"
    assert out[2:] == [
        "BlackSheep RV LLC",
        "Britton's Auto Truck & RV Repair",
        "Desert RV Werks RV Repair Mobile",
    ]


def test_marine_items_stable_when_no_marine() -> None:
    items = [{"name": "A Auto", "category": "Car Repair"}, {"name": "B Auto", "category": "Car Repair"}]
    assert [it["name"] for it in _marine_first_items(items)] == ["A Auto", "B Auto"]
