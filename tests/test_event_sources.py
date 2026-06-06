"""Event-source scrapers (source-expansion #9-13 + marquee verify). No live HTTP."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from app.contrib import allevents, bandsintown, eventbrite_orgs, movies, senior_center
from app.contrib.event_record import parse_jsonld_events

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ----- allevents (#9) JSON-LD + dedupe ------------------------------------


def test_allevents_jsonld_and_dedupe() -> None:
    html = (FIXTURES / "allevents" / "city.html").read_text(encoding="utf-8")
    from app.contrib.event_record import dedupe_within

    records = dedupe_within(parse_jsonld_events(html, source=allevents.SOURCE))
    titles = [r.title for r in records]
    # Flying X appears twice (ItemList + standalone) -> deduped to one.
    assert titles.count("Live Music at Flying X Saloon") == 1
    assert "Sunset Cruise" in titles
    flying = next(r for r in records if r.title.startswith("Live Music"))
    assert flying.venue_name == "Flying X Saloon"
    assert flying.start_date == date(2026, 6, 6)
    assert flying.start_time is not None and flying.start_time.hour == 20


# ----- bandsintown (#10) ---------------------------------------------------


def test_bandsintown_parse_tags_regional() -> None:
    payload = json.loads((FIXTURES / "bandsintown" / "events.json").read_text(encoding="utf-8"))
    records = bandsintown.parse_events(payload)
    # The datetime-less third event is dropped.
    assert len(records) == 2
    assert all("regional" in r.tags for r in records)
    assert records[0].venue_name == "BlueWater Resort & Casino"
    assert "Parker" in (records[0].venue_address or "")


def test_bandsintown_no_app_id_skips(monkeypatch) -> None:
    monkeypatch.delenv("BANDSINTOWN_APP_ID", raising=False)
    assert bandsintown.fetch_events() == []


# ----- eventbrite_orgs (#12) worship exclusion -----------------------------


def test_eventbrite_excludes_worship() -> None:
    payload = json.loads((FIXTURES / "eventbrite" / "org_events.json").read_text(encoding="utf-8"))
    records = eventbrite_orgs.parse_events(payload, org_id="40584556073")
    titles = [r.title for r in records]
    assert "Havasu Health Foundation 5K Run" in titles
    assert "Sunday Worship Service" not in titles  # excluded
    assert len(records) == 1
    assert "org:40584556073" in records[0].tags


def test_eventbrite_no_token_skips(monkeypatch) -> None:
    monkeypatch.delenv("EVENTBRITE_API_TOKEN", raising=False)
    assert eventbrite_orgs.fetch_events() == []


# ----- senior_center (#13) -------------------------------------------------


def test_senior_center_parse() -> None:
    html = (FIXTURES / "senior_center" / "current_events.html").read_text(encoding="utf-8")
    records = senior_center.parse_activities(html)
    titles = [r.title for r in records]
    assert "Chair Yoga" in titles
    assert "Bingo" in titles
    # The heading-less decorative block is skipped.
    assert len(records) == 2
    yoga = next(r for r in records if r.title == "Chair Yoga")
    assert yoga.start_date is None  # recurring, no fixed date
    assert "Fitness Room" in (yoga.description or "")


# ----- movies (#11) webedia + family tagging -------------------------------


def test_movies_parse_and_family_tag() -> None:
    payload = json.loads((FIXTURES / "movies" / "webedia_showtimes.json").read_text(encoding="utf-8"))
    records = movies.parse_webedia_showtimes(payload, theater_name="Movies Havasu")
    by_title = {r.title: r for r in records}
    # Galactic Frontier shows on two distinct days -> two records.
    gf = [r for r in records if r.title == "Galactic Frontier"]
    assert len(gf) == 2
    assert all(r.venue_name == "Movies Havasu" for r in gf)
    assert "Showtimes:" in (gf[0].description or "")
    # Kids summer movie is family-tagged.
    kids = by_title["Free Summer Kids Movie: Cartoon Quest"]
    assert "family" in kids.tags
    assert "free-summer-movie" in kids.tags


# ----- CLI -----------------------------------------------------------------


def test_events_cli_dry_run(monkeypatch, capsys) -> None:
    import scripts.events_pull as cli

    html = (FIXTURES / "allevents" / "city.html").read_text(encoding="utf-8")

    def _fixture_fetch(**_kwargs):
        return parse_jsonld_events(html, source="allevents")

    # cli._SOURCES captured allevents.fetch_events at import time, so patching
    # the module attribute (the old approach) left the dict holding the REAL
    # fetcher and this "dry run" hit allevents.in live on every test run —
    # slow and flaky under parallel test load (T2.4).
    name, _real_fetch, sample_fn, notes = cli._SOURCES["allevents"]
    monkeypatch.setitem(cli._SOURCES, "allevents", (name, _fixture_fetch, sample_fn, notes))
    assert cli.main(["--source", "allevents"]) == 0
    out = capsys.readouterr().out
    assert "allevents — DRY RUN" in out


def test_events_cli_apply_ingests_aggregator_as_pending(monkeypatch, capsys) -> None:
    """`--apply` now routes through event_ingest instead of refusing to write.

    allevents is an aggregator (NOT in the auto-approve registry), so applied rows
    must land PENDING in the review queue — never auto-approved live. We patch the
    source fetch to fixture records (no live HTTP) and assert the ingest report
    shows pending inserts and zero auto-approvals.
    """
    import scripts.events_pull as cli

    html = (FIXTURES / "allevents" / "city.html").read_text(encoding="utf-8")

    def _fixture_fetch(**_kwargs):
        return parse_jsonld_events(html, source=allevents.SOURCE)

    name, _real_fetch, sample_fn, notes = cli._SOURCES["allevents"]
    monkeypatch.setitem(cli._SOURCES, "allevents", (name, _fixture_fetch, sample_fn, notes))

    assert cli.main(["--source", "allevents", "--apply"]) == 0
    out = capsys.readouterr().out
    assert "allevents ingest complete" in out
    # Aggregator trust tier: rows land pending, none auto-approved.
    assert re.search(r"^\s*auto_approved\s+0\s*$", out, re.MULTILINE)
    assert re.search(r"^\s*inserted_pending\s+[1-9]", out, re.MULTILINE)


# ----- marquee coverage verifier (#13 note) --------------------------------


def test_marquee_match_rows() -> None:
    import scripts.verify_marquee_event_coverage as v

    rows = [
        ("Desert Storm Poker Run", "desert storm poker run", date(2026, 4, 25)),
        ("Havasu Balloon Festival", "havasu balloon festival", date(2026, 1, 16)),
        ("Random Trivia Night", "random trivia night", date(2026, 6, 1)),
    ]
    found = v.match_rows(rows)
    assert found["Desert Storm"]
    assert found["Balloon Festival"]
    assert found["Boat Show"] == []  # gap
    assert found["Havasu 95 Speedway"] == []  # gap
