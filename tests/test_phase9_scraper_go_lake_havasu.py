"""Phase 9b — Go Lake Havasu JSON-LD scraper."""

from __future__ import annotations

from app.events.scrapers.go_lake_havasu import GoLakeHavasuClient

LIST_FIXTURE = """
<a href="/events/ami-trivia-tournament/">AMI Trivia</a>
"""

DETAIL_FIXTURE = """
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"Event","name":"AMI Trivia Tournament",
 "startDate":"2026-05-20T17:00:00-07:00","endDate":"2026-05-20T19:00:00-07:00",
 "location":{"@type":"Place","name":"AMI Trivia Tournament"},
 "url":"https://www.golakehavasu.com/events/ami-trivia-tournament/"}
</script>
"""


def test_go_lake_havasu_json_ld(monkeypatch) -> None:
    client = GoLakeHavasuClient()

    def fake_fetch(url, **kwargs):
        if url.endswith("/events/"):
            return LIST_FIXTURE
        return DETAIL_FIXTURE

    monkeypatch.setattr(client, "fetch_text", fake_fetch)
    payloads = client.run({})
    assert payloads
    assert payloads[0].name == "AMI Trivia Tournament"


# ED-1: location.name holds description prose; the real venue is on a LOCATION: line.
CORRUPT_LIST_FIXTURE = '<a href="/events/moonshot-pitch/">Moonshot</a>'
CORRUPT_DETAIL_FIXTURE = """
<script type="application/ld+json">
{"@context":"http://schema.org","@type":"Event","name":"Moonshot Pitch Competition",
 "startDate":"2026-06-03T09:00:00-07:00","endDate":"2026-06-03T15:30:00-07:00",
 "location":{"@type":"Place","name":"Do you have a moonshot business idea or an existing business you'd like to expand? Tell us more about it!"},
 "description":"Date: June 03, 2026\\nTime: 09:00 - 15:30\\n\\nHey entrepreneurs!\\n\\nLOCATION: Mohave College, Building 200, 1977 W Acoma Blvd, Lake Havasu City, AZ 86403\\n\\nClick here to sign up!\\n\\nStay Connected",
 "url":"https://www.golakehavasu.com/events/moonshot-pitch/"}
</script>
"""


def test_go_lake_havasu_recovers_corrupted_venue(monkeypatch) -> None:
    client = GoLakeHavasuClient()

    def fake_fetch(url, **kwargs):
        if url.endswith("/events/"):
            return CORRUPT_LIST_FIXTURE
        return CORRUPT_DETAIL_FIXTURE

    monkeypatch.setattr(client, "fetch_text", fake_fetch)
    payloads = client.run({})
    assert payloads
    p = payloads[0]
    # Venue recovered from the LOCATION: line, not the prose in location.name.
    assert p.venue_name == "Mohave College, Building 200"
    assert p.address == "1977 W Acoma Blvd, Lake Havasu City, AZ 86403"
    # Description de-noised.
    assert "LOCATION:" not in p.description
    assert "Click here to sign up" not in p.description
    assert "Stay Connected" not in p.description
    assert "Hey entrepreneurs!" in p.description
