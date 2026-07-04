"""Group D conditions/outdoors scrapers (source-expansion #14-18). No live HTTP."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.conditions import az511, nws_extras, rise_water_temp, wildfire
from app.contrib import azgfd_fishing

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ----- nws_extras (#14) ----------------------------------------------------


def test_nws_extras_parse_gridpoint() -> None:
    payload = json.loads((FIXTURES / "nws_extras" / "gridpoint.json").read_text(encoding="utf-8"))
    now = datetime(2026, 6, 4, 4, 0)  # after both windGust windows -> picks the 45 km/h entry
    out = nws_extras.parse_gridpoint(payload, now=now)
    assert out["wind_gust_mph"] == pytest.approx(28.0, abs=0.2)
    assert out["twenty_foot_wind_mph"] == pytest.approx(14.9, abs=0.2)
    assert out["wet_bulb_globe_temp_f"] == pytest.approx(86.0, abs=0.2)
    assert "heat_risk" not in out  # absent field omitted


def test_nws_extras_azz036_coverage() -> None:
    assert nws_extras.lake_wind_advisory_zone_covered("AZZ002") is False
    assert nws_extras.lake_wind_advisory_zone_covered("AZZ002,AZZ036") is True


# ----- rise_water_temp (#15) -----------------------------------------------


def test_rise_parse_picks_latest() -> None:
    payload = json.loads((FIXTURES / "rise" / "result.json").read_text(encoding="utf-8"))
    out = rise_water_temp.parse_result(payload)
    assert out["water_temp_f"] == 73.8  # most recent (2026-06-03)
    assert out["water_temp_c"] == pytest.approx(23.2, abs=0.2)
    assert out["feature_enabled"] is True


def test_rise_flag_default_on_when_env_absent(monkeypatch) -> None:
    """v4.6: the code default is ON — no operator env var needed."""
    monkeypatch.delenv("FEATURE_FLAG_WATER_TEMP_RISE_6127", raising=False)
    assert rise_water_temp.feature_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off", ""])
def test_rise_flag_explicit_falsy_disables(monkeypatch, value: str) -> None:
    """An explicit falsy env var still turns the fetcher off (no HTTP, empty)."""
    monkeypatch.setenv("FEATURE_FLAG_WATER_TEMP_RISE_6127", value)
    assert rise_water_temp.feature_enabled() is False
    out = rise_water_temp.fetch_rise_water_temp()
    assert out["feature_enabled"] is False
    assert out["water_temp_f"] is None


# ----- wildfire (#16) ------------------------------------------------------


def test_wildfire_radius_filter() -> None:
    payload = json.loads((FIXTURES / "wildfire" / "incidents.json").read_text(encoding="utf-8"))
    incidents = wildfire.parse_incidents(payload, radius_mi=100)
    names = [i.name for i in incidents]
    assert "Standard Wash Fire" in names
    assert "Faraway Rim Fire" not in names  # ~190 mi away, filtered
    assert "" not in names  # nameless skipped
    assert incidents[0].size_acres == 320.5
    assert incidents[0].distance_mi is not None and incidents[0].distance_mi < 100


# ----- az511 (#17) ---------------------------------------------------------


def test_az511_events_filter() -> None:
    payload = json.loads((FIXTURES / "az511" / "events.json").read_text(encoding="utf-8"))
    events = az511.parse_events(payload)
    roads = [e.roadway for e in events]
    assert "SR-95" in roads
    assert "I-40" in roads  # Mohave county
    assert "I-10" not in roads  # Maricopa, irrelevant


def test_az511_wzdx_filter() -> None:
    payload = json.loads((FIXTURES / "az511" / "wzdx.json").read_text(encoding="utf-8"))
    events = az511.parse_wzdx(payload)
    assert len(events) == 1
    assert "US-95" in (events[0].roadway or "")
    assert events[0].feed == "wzdx"


def test_az511_no_key_skips_events(monkeypatch) -> None:
    monkeypatch.delenv("AZ511_API_KEY", raising=False)
    assert az511.fetch_events() == []


# ----- azgfd_fishing (#18) -------------------------------------------------


def test_azgfd_discover_bulletins() -> None:
    html = (FIXTURES / "azgfd" / "archive.html").read_text(encoding="utf-8")
    links = azgfd_fishing.discover_bulletin_links(html)
    assert len(links) == 2
    assert all("govdelivery.com" in link for link in links)


def test_azgfd_extract_lake_havasu_section() -> None:
    html = (FIXTURES / "azgfd" / "bulletin.html").read_text(encoding="utf-8")
    section = azgfd_fishing.extract_lake_havasu_section(html)
    assert section is not None
    assert "smallmouth bass" in section
    assert "Redear sunfish" in section
    # Did not bleed into the next water body.
    assert "Trout stocking" not in section
    # Did not include the prior Lake Mohave section.
    assert "Striped bass" not in section


# ----- CLI -----------------------------------------------------------------


def test_conditions_cli_apply_guarded() -> None:
    import scripts.conditions_extras_pull as cli

    with pytest.raises(SystemExit) as exc:
        cli.main(["--source", "wildfire", "--apply"])
    assert exc.value.code == 2
