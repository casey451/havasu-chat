"""2026-07-01 consolidated Phase 3 — code halves of the data-ops PR.

The DB writes ride the gated ``scripts/apply_search_data_ops_2026_07_01.py``
(Casey runs ``--apply``); this covers what ships in code:

* the durable ingest blocklist gains the two non-businesses the 06-30
  deactivation could not hold down (the re-scrape reactivated the Marine
  Program row within a day);
* the visitor-center placeholder address never renders — chat provider rows
  and category-card area lines drop it (the data op nulls the stored field,
  ingest already nulls new imports; this is the render guard);
* the three Phase-2-routed leaves are declared in the taxonomy seed and are no
  longer PENDING.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.categories import leaf_query
from app.contrib.ingest_suppression import is_suppressed_business

_SEED = Path(__file__).resolve().parents[1] / "docs" / "proposals" / "taxonomy-seed.json"


def test_non_businesses_are_durably_suppressed() -> None:
    assert is_suppressed_business(
        "Lake Havasu Marine Association Designated Operator Program"
    )
    assert is_suppressed_business("Outdoor Enthusiasts")
    # Real businesses are untouched.
    assert not is_suppressed_business("Wakesurf Havasu")
    assert not is_suppressed_business("Neat Pool & Supply")


def test_seeded_leaves_declared_and_not_pending() -> None:
    seed = json.loads(_SEED.read_text(encoding="utf-8"))
    assert "firearms-and-shooting-sports" in seed["shopping-and-retail"]["leaves"]
    assert "medical-specialists-and-imaging" in seed["health-and-medical"]["leaves"]
    assert "pediatrics" in seed["health-and-medical"]["leaves"]
    for slug in ("firearms-and-shooting-sports", "medical-specialists-and-imaging",
                 "pediatrics"):
        assert slug not in leaf_query.PENDING_LEAF_SLUGS, slug


class _FakeProvider:
    id = "x"
    slug = "x"
    phone = None
    category = None
    primary_category_label = None
    google_primary_category = None
    google_rating = None
    google_review_count = None
    hours_structured = None
    description = None
    tier = None
    sponsored_until = None
    entity_id = None
    district = None
    lat = None
    lng = None

    def __init__(self, name: str, address: str | None):
        self.provider_name = name
        self.address = address


def test_chat_row_drops_placeholder_address() -> None:
    from app.chat.intents.queries import _provider_to_row

    p = _FakeProvider("Ron's Fishing Guide",
                      "Go Lake Havasu Visitor Center, 422 English Village")
    assert _provider_to_row(p)["address"] is None
    real = _FakeProvider("Neat Pool & Supply", "1990 Mesquite Ave")
    assert _provider_to_row(real)["address"] == "1990 Mesquite Ave"


def test_category_card_area_drops_placeholder_address() -> None:
    from app.categories.queries import _card_area

    p = _FakeProvider("Ron's Fishing Guide",
                      "Go Lake Havasu Visitor Center, 422 English Village, Lake Havasu City")
    assert _card_area(p) == ""
    real = _FakeProvider("Neat Pool & Supply", "1990 Mesquite Ave, Lake Havasu City")
    assert _card_area(real) == "1990 Mesquite Ave"
