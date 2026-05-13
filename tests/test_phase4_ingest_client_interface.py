"""Phase 4.2 — layered-scrape ``BaseIngestClient`` + Google Places library."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.contrib.google_places_scraper import GooglePlacesClient
from app.contrib.google_types_mapping import map_google_types_to_slug_and_place_type
from app.contrib.ingest_base import BaseIngestClient, EnrichedHit, EntityPayload, RawHit
from app.contrib.rate_limiter import GOOGLE_PLACES_LIMITER


def test_base_ingest_client_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseIngestClient()  # type: ignore[abstract,misc]


def test_subclass_missing_discover_raises() -> None:
    class C(BaseIngestClient):
        source_name = "x"

        def enrich(self, hit: RawHit) -> EnrichedHit:
            return EnrichedHit(raw_hit=hit)

        def dedupe_key(self, hit: RawHit) -> str:
            return ""

        def to_entity_payload(self, hit: EnrichedHit) -> EntityPayload:
            return EntityPayload(name="", entity_type="commercial")

    with pytest.raises(TypeError):
        C()  # type: ignore[abstract,misc]


def test_subclass_missing_enrich_raises() -> None:
    class C(BaseIngestClient):
        source_name = "x"

        def discover(self, query: dict[str, Any]) -> list[RawHit]:
            return []

        def dedupe_key(self, hit: RawHit) -> str:
            return ""

        def to_entity_payload(self, hit: EnrichedHit) -> EntityPayload:
            return EntityPayload(name="", entity_type="commercial")

    with pytest.raises(TypeError):
        C()  # type: ignore[abstract,misc]


def test_subclass_missing_dedupe_key_raises() -> None:
    class C(BaseIngestClient):
        source_name = "x"

        def discover(self, query: dict[str, Any]) -> list[RawHit]:
            return []

        def enrich(self, hit: RawHit) -> EnrichedHit:
            return EnrichedHit(raw_hit=hit)

        def to_entity_payload(self, hit: EnrichedHit) -> EntityPayload:
            return EntityPayload(name="", entity_type="commercial")

    with pytest.raises(TypeError):
        C()  # type: ignore[abstract,misc]


def test_subclass_missing_to_entity_payload_raises() -> None:
    class C(BaseIngestClient):
        source_name = "x"

        def discover(self, query: dict[str, Any]) -> list[RawHit]:
            return []

        def enrich(self, hit: RawHit) -> EnrichedHit:
            return EnrichedHit(raw_hit=hit)

        def dedupe_key(self, hit: RawHit) -> str:
            return ""

    with pytest.raises(TypeError):
        C()  # type: ignore[abstract,misc]


def test_google_places_client_is_base_subclass() -> None:
    assert issubclass(GooglePlacesClient, BaseIngestClient)


def test_google_places_client_source_name() -> None:
    assert GooglePlacesClient().source_name == "google_places"


def test_google_places_dedupe_key_is_place_id() -> None:
    c = GooglePlacesClient()
    hit = RawHit(
        source="google_places",
        source_stable_id="places/ChIJabc",
        name="Test",
        raw={},
    )
    assert c.dedupe_key(hit) == "places/ChIJabc"


def test_map_types_restaurant() -> None:
    assert map_google_types_to_slug_and_place_type(["restaurant"]) == (
        "eat-drink",
        "commercial",
    )


def test_map_types_dog_park_primary_wins() -> None:
    assert map_google_types_to_slug_and_place_type(["dog_park", "park"]) == (
        "outdoors-parks-trails",
        "place",
    )


def test_map_types_unknown() -> None:
    assert map_google_types_to_slug_and_place_type(["unknown_type_xyz"]) == (None, None)


# -----------------------------------------------------------------------------
# Phase 5 expansion (2026-05-13) — per-category coverage tests for the new
# types[] entries added per outputs/cursor_brief_phase_5_tier_1_data.md
# §3.1-§3.6. Each test picks one representative entry per category that
# wasn't in the pre-Phase-5 mapping; the existing tests above (`restaurant`,
# `dog_park`) cover the unchanged entries.
# -----------------------------------------------------------------------------


def test_map_types_phase5_eat_drink_expansion() -> None:
    """§3.1 — verify a new Eat & Drink type maps to eat-drink/commercial."""
    assert map_google_types_to_slug_and_place_type(["pizza_restaurant"]) == (
        "eat-drink",
        "commercial",
    )
    assert map_google_types_to_slug_and_place_type(["coffee_shop"]) == (
        "eat-drink",
        "commercial",
    )


def test_map_types_phase5_on_the_water_expansion() -> None:
    """§3.2 — boat_dealer is commercial; marina (existing) stays as place."""
    assert map_google_types_to_slug_and_place_type(["boat_dealer"]) == (
        "on-the-water",
        "commercial",
    )
    assert map_google_types_to_slug_and_place_type(["harbor"]) == (
        "on-the-water",
        "place",
    )


def test_map_types_phase5_home_property_expansion() -> None:
    """§3.3 — verify a new Home & Property type maps to home-property-services."""
    assert map_google_types_to_slug_and_place_type(["roofing_contractor"]) == (
        "home-property-services",
        "commercial",
    )
    assert map_google_types_to_slug_and_place_type(["pest_control_service"]) == (
        "home-property-services",
        "commercial",
    )


def test_map_types_phase5_health_expansion() -> None:
    """§3.4 — verify a new Health & Wellness type maps to health-wellness-care."""
    assert map_google_types_to_slug_and_place_type(["chiropractor"]) == (
        "health-wellness-care",
        "commercial",
    )
    assert map_google_types_to_slug_and_place_type(["medical_lab"]) == (
        "health-wellness-care",
        "commercial",
    )


def test_map_types_phase5_auto_rv_fuel_expansion() -> None:
    """§3.5 — verify a new Auto/RV/Fuel type maps to auto-rv-fuel.

    Also asserts the prereq §3.1.b lock: rv_park stays in
    lodging-vacation-rentals (where-you-stay framing) even though
    Phase 5's auto-rv-fuel umbrella includes RV-related services.
    """
    assert map_google_types_to_slug_and_place_type(["tire_shop"]) == (
        "auto-rv-fuel",
        "commercial",
    )
    assert map_google_types_to_slug_and_place_type(["rv_repair"]) == (
        "auto-rv-fuel",
        "commercial",
    )
    # rv_park stays in lodging-vacation-rentals per prereq §3.1.b lock
    assert map_google_types_to_slug_and_place_type(["rv_park"]) == (
        "lodging-vacation-rentals",
        "commercial",
    )


def test_map_types_phase5_shopping_expansion() -> None:
    """§3.6 — verify a new Shopping type maps to shopping-essentials."""
    assert map_google_types_to_slug_and_place_type(["hardware_store"]) == (
        "shopping-essentials",
        "commercial",
    )
    assert map_google_types_to_slug_and_place_type(["clothing_store"]) == (
        "shopping-essentials",
        "commercial",
    )


def test_map_types_phase5_beauty_skip_lock() -> None:
    """§3.1.a operator decision-lock — beauty types route to operator queue.

    `hair_salon`, `beauty_salon`, `nail_salon` explicitly map to
    `(None, None)` so the Phase 5 reconciler surfaces them to the
    operator-queue rather than silently routing them into eat-drink or
    shopping-essentials. Final category home is V1.5 territory.
    """
    assert map_google_types_to_slug_and_place_type(["hair_salon"]) == (None, None)
    assert map_google_types_to_slug_and_place_type(["beauty_salon"]) == (None, None)
    assert map_google_types_to_slug_and_place_type(["nail_salon"]) == (None, None)


def test_map_types_phase5_primary_wins_through_expansion() -> None:
    """Existing primary-type-wins behavior carries through the §3 expansion.

    If a venue's types[] has `["pizza_restaurant", "restaurant", "food"]`,
    primary (`pizza_restaurant`) should win and produce eat-drink/commercial.
    Verifies the iteration order in `map_google_types_to_slug_and_place_type`
    still respects the input list order after the table expanded.
    """
    assert map_google_types_to_slug_and_place_type(
        ["pizza_restaurant", "restaurant", "food"]
    ) == ("eat-drink", "commercial")


def test_google_places_to_entity_payload_shape() -> None:
    c = GooglePlacesClient()
    raw_hit = RawHit(
        source="google_places",
        source_stable_id="places/abc",
        name="Slice House",
        lat=34.5,
        lng=-114.4,
        raw={
            "formattedAddress": "123 Main",
            "types": ["restaurant"],
        },
    )
    enriched = EnrichedHit(
        raw_hit=raw_hit,
        enriched={
            "types": ["restaurant"],
            "nationalPhoneNumber": "555-0100",
            "websiteUri": "https://example.com",
            "displayName": {"text": "Slice House"},
            "location": {"latitude": 34.5, "longitude": -114.4},
        },
    )
    payload = c.to_entity_payload(enriched)
    assert isinstance(payload, EntityPayload)
    assert payload.source == "google_places"
    assert payload.category_slug == "eat-drink"
    assert payload.entity_type == "commercial"
    assert payload.extension_payloads.get("place_type") == "commercial"
    assert payload.google_place_id == "places/abc"


def test_google_places_client_uses_google_places_limiter_for_discovery() -> None:
    c = GooglePlacesClient()
    assert c._discovery_limiter is GOOGLE_PLACES_LIMITER


def test_discovery_path_invokes_rate_limiter_acquire(monkeypatch: pytest.MonkeyPatch) -> None:
    acquires: list[int] = []
    orig_acquire = GOOGLE_PLACES_LIMITER.acquire

    def counting_acquire() -> None:
        acquires.append(1)
        return orig_acquire()

    monkeypatch.setattr(GOOGLE_PLACES_LIMITER, "acquire", counting_acquire)

    class _Resp:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return {"places": [], "nextPageToken": None}

    def _fake_post(_self: httpx.Client, *_a: Any, **_kw: Any) -> _Resp:
        return _Resp()

    monkeypatch.setattr(httpx.Client, "post", _fake_post)

    c = GooglePlacesClient()
    c.discover(
        {
            "api_key": "fake",
            "textQuery": "pizza in Lake Havasu City, AZ",
            "category_label": "pizza",
            "category_domain": "food_drink",
        }
    )
    assert len(acquires) >= 1


def test_google_places_scraper_import_chain_no_models_at_top() -> None:
    """Gotcha #17 — importing the scraper must not force-load ORM models."""
    repo_root = Path(__file__).resolve().parents[1]
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(repo_root)!r})\n"
        "from app.contrib.google_places_scraper import GooglePlacesClient  # noqa: F401\n"
        "import json\n"
        "print(json.dumps({\n"
        '  "models_loaded": "app.db.models" in sys.modules,\n'
        "}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=60,
        env={**os.environ, "AUTH_DEV_MODE": "1"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data["models_loaded"] is False


@pytest.mark.skip(
    reason="Deferred to operator: discovery --dry-run log parity vs pre-refactor "
    "(requires GOOGLE_PLACES_API_KEY + live API or golden log fixture)."
)
def test_places_discovery_dry_run_log_regression() -> None:
    assert False


def test_run_method_chains_discover_enrich_payload() -> None:
    class Mini(GooglePlacesClient):
        def discover(self, query: dict[str, Any]) -> list[RawHit]:
            return [
                RawHit(
                    source="google_places",
                    source_stable_id="p1",
                    name="A",
                    raw={"types": ["cafe"], "formattedAddress": "1 Rd"},
                )
            ]

        def enrich(self, hit: RawHit) -> EnrichedHit:
            return EnrichedHit(
                raw_hit=hit,
                enriched={"types": ["cafe"], "nationalPhoneNumber": "555"},
            )

    m = Mini()
    payloads = m.run({"unused": True})
    assert len(payloads) == 1
    assert payloads[0].category_slug == "eat-drink"
