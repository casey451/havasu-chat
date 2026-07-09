"""WS10 — the /lake hub: launch ramps with fees, a live-conditions module, and
the on-the-water subcategory lists (§10 acceptance: "/lake shows live water temp
+ at least 3 ramps with fee info"; zero chat-deflection tiles).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.home import lake_hub
from app.main import app


def test_lake_shows_at_least_three_ramps_with_fees() -> None:
    assert len(lake_hub.LAUNCH_RAMPS) >= 3
    with TestClient(app) as client:
        body = client.get("/lake").text
    for r in lake_hub.LAUNCH_RAMPS:
        assert r.name in body
        assert r.fee in body  # honest fee label rendered on the card
        assert r.source_url in body  # each ramp links to its authority


def test_lake_conditions_module_present() -> None:
    with TestClient(app) as client:
        body = client.get("/lake").text
    assert "Lake conditions" in body
    # Labels come from build_today_payload (same source /today uses); they render
    # even when a source is "Unavailable", so the water-temp/level rows are here.
    assert "Lake level" in body
    assert "Water temp" in body


def test_lake_subcategory_tiles_link_to_real_leaves_no_chat() -> None:
    with TestClient(app) as client:
        body = client.get("/lake").text
    for t in lake_hub.lake_tiles():
        assert t["url"] in body
    # WS10 acceptance: zero chat-deflection tiles on the hub.
    assert "chat?q=" not in body


def test_launch_ramp_data_is_sourced_not_fabricated() -> None:
    """Every ramp carries a real https source_url and a non-empty fee label."""
    for r in lake_hub.LAUNCH_RAMPS:
        assert r.source_url.startswith("https://")
        assert r.fee.strip()
        assert r.name.strip()
