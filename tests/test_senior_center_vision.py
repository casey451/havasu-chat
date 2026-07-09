"""Tests for the Senior Center flyer vision adapter (Task B).

Discovery + row->EventRecord mapping + orchestration are exercised with injected
page HTML and recorded model JSON (no live HTTP/LLM).
"""

from __future__ import annotations

import json
from datetime import date, time

from app.contrib import senior_center_vision as scv
from app.contrib.vision_calendar import VisionEventRow
from app.events.senior_center import CALENDAR_IMAGES, SENIOR_TAGS, VENUE_NAME

_FLYER_A = (
    "https://images.leadconnectorhq.com/image/f_webp/q_80/r_1200/"
    "u_https://assets.cdn.filesafe.space/abc/media/flyerA.png"
)
_FLYER_B = (
    "https://images.leadconnectorhq.com/image/f_webp/q_80/r_1200/"
    "u_https://storage.googleapis.com/msgsndr/flyerB.png"
)

_PAGE_HTML = f"""
<html><body>
  <img src="data:image/gif;base64,AAAA" alt="" />
  <img src="{_FLYER_A}" alt="" />
  <img src="{_FLYER_B}" alt="" />
  <img src="/local/theme/decor.png" alt="decor" />
</body></html>
"""


def test_discover_flyer_images_keeps_only_cdn() -> None:
    urls = scv.discover_flyer_images(_PAGE_HTML)
    assert urls == [_FLYER_A, _FLYER_B]  # data: + local theme image excluded


def test_senior_image_urls_appends_calendar_grids() -> None:
    urls = scv.senior_image_urls(_PAGE_HTML)
    assert _FLYER_A in urls
    for grid in CALENDAR_IMAGES.values():
        assert grid in urls


def _row(**kw) -> VisionEventRow:
    base = dict(
        title="Christmas in July",
        event_date=date(2026, 7, 8),
        start_time=time(9, 0),
        end_time=time(13, 0),
        location=None,
        cost="Free",
        audience="seniors",
        notes="Proceeds benefit Meals on Wheels",
        confidence=0.95,
        source_cell="July 8 Christmas in July 9a-1p",
        should_hide=False,
    )
    base.update(kw)
    return VisionEventRow(**base)


def test_row_to_event_record_is_senior_tagged() -> None:
    rec = scv.row_to_event_record(_row(), _FLYER_A)
    assert rec.source == scv.SOURCE
    assert rec.venue_name == VENUE_NAME
    assert SENIOR_TAGS[0] in rec.tags
    assert rec.tags[0] == SENIOR_TAGS[0]  # senior leads
    assert rec.image_url == _FLYER_A
    assert rec.url.startswith("https://lakehavasuseniorcenter.com/current-events#flyer|2026-07-08|")
    assert "senior center flyer" in rec.description


def test_pull_senior_flyers_maps_and_drops_decorative() -> None:
    # Flyer A is a real dated special; Flyer B is a decorative photo -> the model
    # returns no dated rows -> dropped by the guards.
    raw_by_url = {
        _FLYER_A: json.dumps(
            {
                "events": [
                    {
                        "title": "Christmas in July",
                        "date": "2026-07-08",
                        "start_time": "09:00",
                        "end_time": "13:00",
                        "cost": "Free",
                        "audience": "seniors",
                        "source_cell": "July 8 Christmas in July",
                        "confidence": 0.95,
                    }
                ]
            }
        ),
        _FLYER_B: json.dumps({"events": []}),
    }
    # Stub the two monthly grids so they need no network either.
    for grid in CALENDAR_IMAGES.values():
        raw_by_url[grid] = json.dumps({"events": []})

    result = scv.pull_senior_flyers(
        html=_PAGE_HTML, max_flyers=12, raw_text_by_url=raw_by_url
    )
    titles = [r.title for r in result.records]
    assert titles == ["Christmas in July"]
    assert result.records[0].source == scv.SOURCE
    assert result.images_extracted == 1


def test_pull_senior_flyers_respects_cap() -> None:
    result = scv.pull_senior_flyers(
        html=_PAGE_HTML,
        max_flyers=1,
        raw_text_by_url={_FLYER_A: json.dumps({"events": []})},
    )
    assert result.images_considered == 1
