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
