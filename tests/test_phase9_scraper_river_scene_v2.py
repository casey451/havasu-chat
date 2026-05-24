"""Phase 9b — RiverScene V2 adapter."""

from __future__ import annotations

from datetime import date, time
from unittest.mock import MagicMock

from app.contrib.river_scene import RiverSceneEvent
from app.events.scrapers.river_scene_v2 import RiverSceneV2Client


def test_river_scene_v2_delegates_without_changing_shape(monkeypatch) -> None:
    rse = RiverSceneEvent(
        title="The Substitutes",
        url="https://riverscenemagazine.com/events/the-substitutes/",
        start_date=date(2026, 5, 20),
        end_date=date(2026, 5, 20),
        start_time=time(19, 0),
        end_time=time(22, 0),
        description_html="Live music",
        venue_name="Bar",
        venue_address=None,
        organizer=None,
        category_slugs=["music"],
    )
    monkeypatch.setattr(
        "app.events.scrapers.river_scene_v2.fetch_sitemap_urls",
        lambda **kw: ["https://riverscenemagazine.com/events/the-substitutes/"],
    )
    monkeypatch.setattr(
        "app.events.scrapers.river_scene_v2.fetch_and_parse_event",
        lambda url, **kw: rse,
    )
    client = RiverSceneV2Client(http_client=MagicMock())
    payloads = client.run({})
    assert len(payloads) == 1
    assert payloads[0].name == "The Substitutes"
    assert payloads[0].source == "river_scene"
