"""Unit tests for the dry-run description/url/venue backfill planner."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "clean_event_descriptions.py"
_spec = importlib.util.spec_from_file_location("clean_event_descriptions", _PATH)
ced = importlib.util.module_from_spec(_spec)
sys.modules["clean_event_descriptions"] = ced  # needed so @dataclass can resolve module
_spec.loader.exec_module(ced)


def test_metadata_description_cleared_url_and_loc_fixed() -> None:
    r = ced.plan_event_repair(
        title="Motor Madness",
        description="Venue: 2144 McCulloch Blvd N\nCategories: car show",
        event_url="https://info@ijsba.com/",
        location_name="2144 McCulloch Blvd NLake Havasu City, AZ",
        start_date=date(2026, 6, 21),
    )
    assert r.new_description == ""
    assert r.new_event_url == "https://askhava.com/events-ui"
    assert r.new_location_name == "2144 McCulloch Blvd N Lake Havasu City, AZ"
    assert r.desc_changed and r.url_changed and r.loc_changed


def test_synthetic_placeholder_cleared() -> None:
    r = ced.plan_event_repair(
        title="Roadwork",
        description="Roadwork at Lake Havasu City on Jun 06, 2026.",
        event_url="https://allevents.in/x/roadwork",
        location_name="Lake Havasu City",
        start_date=date(2026, 6, 6),
    )
    assert r.new_description == ""
    assert r.desc_changed


def test_real_event_untouched() -> None:
    real = "A-Z is a high-energy local cover band playing rock and country favorites all night."
    r = ced.plan_event_repair(
        title="A-Z",
        description=real,
        event_url="https://www.facebook.com/azband",
        location_name="Flying X Saloon",
        start_date=date(2026, 6, 18),
    )
    assert r.new_description == real
    assert not r.any_change
