"""Phase 9b — Chamber GrowthZone scraper."""

from __future__ import annotations

from app.events.scrapers.chamber import ChamberClient, parse_chamber_list_card_html

CHAMBER_LIST_FIXTURE = """
<div class="card-body gz-events-card-body">
  <h5 class="card-title" itemprop="name">
    <a href="https://business.havasuchamber.com/community-event-calendar/Details/ami-trivia-1?sourceTypeId=Website"
       class="gz-card-title gz-event-card-title" itemprop="url">AMI Trivia</a>
  </h5>
  <meta itemprop="startDate" content="5/19/2026 4:00:00 PM">
</div>
"""

CHAMBER_DETAIL_FIXTURE = """
<html><head>
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"Event","name":"Taste of Havasu",
 "startDate":"2026-10-22T08:00:00-07:00","endDate":"2026-10-22T17:00:00-07:00",
 "url":"https://business.havasuchamber.com/community-event-calendar/Details/taste-1",
 "location":{"@type":"Place","name":"Aquatic Park"}}
</script></head>
<body><h1 class="gz-pagetitle" itemprop="name">Taste of Havasu</h1></body></html>
"""


def test_parse_chamber_list_microdata() -> None:
    cards = parse_chamber_list_card_html(CHAMBER_LIST_FIXTURE)
    assert len(cards) == 1
    assert cards[0]["title"] == "AMI Trivia"
    assert "Details/ami-trivia" in cards[0]["url"]


def test_chamber_to_event_payload_from_json_ld(monkeypatch) -> None:
    client = ChamberClient()

    def fake_fetch(url, **kwargs):
        if "Search" in url:
            return CHAMBER_LIST_FIXTURE
        return CHAMBER_DETAIL_FIXTURE

    monkeypatch.setattr(client, "fetch_text", fake_fetch)
    payloads = client.run({})
    assert len(payloads) >= 1
    p = payloads[0]
    assert "Taste" in p.name or "AMI" in p.name
    assert p.start_date.year == 2026
