"""P2 source-verification sweep: link validity + per-event bucket classification."""

from __future__ import annotations

from app.events.description_clean import valid_event_url
from scripts.verify_event_sources_2026_06 import (
    OK,
    RELABEL_SOURCE,
    REMOVE,
    RESOURCE,
    WEAK_OK,
    classify_event_source,
)


def test_valid_event_url_rejects_internal_and_self_links():
    # External real links pass.
    assert valid_event_url("https://riverscenemagazine.com/events/x")
    assert valid_event_url("https://starcinemashavasu.com/")
    # Our own host / relative paths / fragments / dead host are NOT a source.
    assert valid_event_url("https://askhava.com/events-ui") is None
    assert valid_event_url("/events-ui") is None
    assert valid_event_url("#program-pony-rides") is None
    assert valid_event_url("https://havasuchat.com/events") is None
    assert valid_event_url("") is None
    assert valid_event_url(None) is None


def test_classify_buckets():
    # Verifiable external primary.
    assert classify_event_source("https://riverscenemagazine.com/e", None) == OK
    # No source at all -> remove.
    assert classify_event_source("https://askhava.com/events-ui", None) == REMOVE
    assert classify_event_source("", "") == REMOVE
    # Self-link primary, real external in the other field -> re-source.
    assert classify_event_source(
        "https://askhava.com/events-ui",
        "https://riverscenemagazine.com/events/ijsba",
    ) == RESOURCE
    # Generic venue FB profile -> weak-ok (report only, never auto-removed).
    assert classify_event_source(
        "https://www.facebook.com/profile.php?id=61550826508124", None
    ) == WEAK_OK
    # Wrong-target byline: a Clifford row citing a Sonic URL -> relabel.
    assert classify_event_source(
        "https://starcinemashavasu.com/",
        "https://riverscenemagazine.com/events/summer-free-movies-sonic-the-hedgehog-3",
        title="Summer Free Movies Clifford the Big Red Dog",
    ) == RELABEL_SOURCE
    # A real Star Cinemas primary on a non-Clifford movie stays OK.
    assert classify_event_source(
        "https://starcinemashavasu.com/", None, title="Summer Free Movies Moana"
    ) == OK
