"""2026-06-30 search-bar audit fixes (ASKHAVA_SEARCH_AUDIT_2026-06-30).

Covers Phase 1 code fixes:

* 1A — a "<activity> lessons" query the catalog doesn't teach (golf / wake surf /
  wakeboard) must NOT dump the full Parks & Rec after-school roster; it returns
  nothing so the honest gap template answers. A real topic (swim) still lists,
  and a topic-less browse ("what classes are offered") still lists everything.
* 1B — live-music event queries return only real live music (not a paint-and-sip
  at a brewery); generic "things to do" excludes civic/government meetings; the
  resolver sets the live-music slot for the "live bands" phrasings too.
* 1C — the missing routing variants (paddleboard rentals, wake surfing, escape
  room, drum lessons, helicopter tour...) reach their leaf.
* 1D — the single-listing leaf intro reads in the singular.
"""

from __future__ import annotations

import uuid
from datetime import date
from datetime import time as time_of_day

import pytest

from app.categories.leaf_query import (
    _QUERY_TO_LEAF,
    _QUERY_TO_LEAF_SEARCH_ADD_2026_06_30,
    _normalize,
)
from app.chat.intents import queries as q
from app.chat.intents.resolver import _event_intent_for, resolve
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Program, Provider
from app.db.seed_helpers import derive_provider_slug
from app.events.event_type_tags import is_civic_meeting

_LAT, _LNG = 34.4839, -114.3225


# ===========================================================================
# 1C — routing dictionary additions (DB-free)
# ===========================================================================
_ROUTING_CASES = {
    "paddleboard rentals": "kayak-and-paddle",
    "paddle board rental": "kayak-and-paddle",
    "wake surfing": "jet-ski-and-watersports",
    "wakesurf": "jet-ski-and-watersports",
    "wakesurfing": "jet-ski-and-watersports",
    "wakeboarding": "jet-ski-and-watersports",
    "flyboard": "jet-ski-and-watersports",
    "fishing trip": "fishing-charters-and-guides",
    "bass fishing guide": "fishing-charters-and-guides",
    "drum lessons": "music-lessons",
    "escape room": "family-fun-and-arcades",
    "axe throwing": "family-fun-and-arcades",
    "miniature golf": "family-fun-and-arcades",
    "trampoline park": "family-fun-and-arcades",
    "helicopter tour": "tours-and-sightseeing",
    "helicopter tours": "tours-and-sightseeing",
}


def test_new_variants_route_to_expected_leaf():
    for raw, slug in _ROUTING_CASES.items():
        norm = _normalize(raw)
        assert norm in _QUERY_TO_LEAF, (raw, norm)
        assert _QUERY_TO_LEAF[norm] == slug, (raw, norm, _QUERY_TO_LEAF[norm])


def test_new_keys_normalize_to_themselves():
    # Every key must be the OUTPUT of _normalize, else it can never be hit.
    for terms in _QUERY_TO_LEAF_SEARCH_ADD_2026_06_30.values():
        for term in terms:
            assert _normalize(term) == term, (term, _normalize(term))


def test_new_terms_do_not_corrupt_common_words_via_spell_correct():
    # The routing keys feed normalizer._spell_vocab; a new token one edit from a
    # common word would silently "correct" real queries (e.g. "scenic flight"
    # made "light" -> "flight"). Guard the words the new terms sit near.
    from app.chat.normalizer import spell_correct

    for phrase in (
        "light switch not working",
        "check engine light",
        "fight gym",
        "board game store",
        "guitar room",
        "escape the room",
    ):
        assert spell_correct(phrase) == phrase, (phrase, spell_correct(phrase))


def test_expansion_did_not_override_prior_entries():
    # setdefault must preserve pre-existing mappings the audit relies on.
    assert _QUERY_TO_LEAF["water sports"] == "jet-ski-and-watersports"
    assert _QUERY_TO_LEAF["watersports"] == "jet-ski-and-watersports"
    assert _QUERY_TO_LEAF["mini golf"] == "family-fun-and-arcades"
    assert _QUERY_TO_LEAF["kayak rentals"] == "kayak-and-paddle"


# ===========================================================================
# 1A — classes_find topical guard
# ===========================================================================
def test_class_activity_terms_extraction():
    # Specific activity nouns are surfaced; a generic browse yields nothing.
    assert q._class_activity_terms("golf lessons") == ["golf"]
    assert q._class_activity_terms("wake surf lessons") == ["wake", "surf"]
    assert q._class_activity_terms("wakeboard lessons") == ["wakeboard"]
    assert q._class_activity_terms("what classes are offered") == []
    assert q._class_activity_terms("classes and programs around town") == []


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def _seed_provider(session, name):
    prov = Provider(
        provider_name=name,
        category="programs",
        subcategory="classes",
        slug=derive_provider_slug(session, name),
        source="test",
        lat=_LAT,
        lng=_LNG,
        draft=False,
        is_active=True,
    )
    session.add(prov)
    create_provider_and_entity(session, prov)
    session.commit()
    return prov


def _seed_program(session, provider, *, title, activity_category):
    prog = Program(
        title=title,
        description="Test program.",
        activity_category=activity_category,
        age_min=5,
        age_max=13,
        schedule_days=["Monday"],
        schedule_start_time=time_of_day(15, 30),
        schedule_end_time=time_of_day(17, 0),
        location_name="Lake Havasu City",
        provider_name=provider.provider_name,
        provider_id=provider.id,
        source="test",
        is_active=True,
    )
    session.add(prog)
    session.commit()
    return prog


def _cleanup(db, *provs):
    from sqlalchemy import delete

    from app.db.models import Entity, EntityCategory, Location

    for p in provs:
        eid = p.entity_id
        db.execute(delete(Program).where(Program.provider_id == p.id))
        db.execute(delete(Provider).where(Provider.id == p.id))
        if eid:
            db.execute(delete(Location).where(Location.entity_id == eid))
            db.execute(delete(EntityCategory).where(EntityCategory.entity_id == eid))
            db.execute(delete(Entity).where(Entity.id == eid))
    db.commit()


def _run(db, query):
    resolved = resolve(query)
    assert resolved is not None, f"{query!r} did not resolve"
    return resolved, q.run_query(resolved, db, raw_query=query)


@pytest.mark.parametrize("query", ["golf lessons", "wake surf lessons", "wakeboard lessons"])
def test_activity_lessons_never_dump_after_school_programs(db, query):
    suf = uuid.uuid4().hex[:8]
    host = _seed_provider(db, f"Havasu Parks Co {suf}")
    asp = _seed_program(db, host, title=f"ASP Oro Grande {suf}", activity_category="kids")
    try:
        resolved, result = _run(db, query)
        assert resolved.intent_key == "classes_find"
        names = {r["name"] for r in result.rows}
        assert asp.title not in names, (query, names)
    finally:
        _cleanup(db, host)


def test_swim_lessons_still_returns_real_swim_program(db):
    suf = uuid.uuid4().hex[:8]
    host = _seed_provider(db, f"Havasu Aquatics {suf}")
    swim = _seed_program(
        db, host, title=f"Aqua Beginnings {suf}", activity_category="aquatics"
    )
    try:
        _resolved, result = _run(db, "swim lessons")
        names = {r["name"] for r in result.rows}
        assert swim.title in names, names
    finally:
        _cleanup(db, host)


def test_generic_class_browse_still_lists_all_programs(db):
    suf = uuid.uuid4().hex[:8]
    host = _seed_provider(db, f"Havasu Parks Co {suf}")
    asp = _seed_program(db, host, title=f"ASP Oro Grande {suf}", activity_category="kids")
    try:
        resolved, result = _run(db, "what classes are offered")
        assert resolved.intent_key == "classes_find"
        names = {r["name"] for r in result.rows}
        assert asp.title in names, names
    finally:
        _cleanup(db, host)


# ===========================================================================
# 1B — event topic filtering
# ===========================================================================
class _FakeEvent:
    def __init__(self, title, *, tags=(), location_name="", description=""):
        self.title = title
        self.tags = list(tags)
        self.location_name = location_name
        self.description = description
        self.end_date = None
        self.start_time = None
        self.end_time = None
        self.event_url = ""


def test_is_civic_meeting_signal():
    assert is_civic_meeting("City Council Meeting")
    assert is_civic_meeting("Planning and Zoning Commission")
    assert is_civic_meeting("Board of Adjustment Public Hearing")
    assert not is_civic_meeting("Live Band at Kokopelli")
    assert not is_civic_meeting("Canvas & Cocktails Paint Night")


def _fake_events(monkeypatch, events):
    import app.events.queries as eq

    def _fake_window(db, *, window_start, window_end, limit):
        return [(e, window_start) for e in events]

    monkeypatch.setattr(eq, "events_in_window", _fake_window)


def test_live_music_filter_keeps_only_real_music(monkeypatch):
    band = _FakeEvent("Live Band at Kokopelli", location_name="Kokopelli")
    paint = _FakeEvent(
        "Canvas & Cocktails", location_name="Barley Brothers Brewery",
        description="Paint and sip night",
    )
    bmx = _FakeEvent("BMX Local Race (Kids)", location_name="Havasu BMX")
    council = _FakeEvent("City Council Meeting", location_name="City Hall")
    _fake_events(monkeypatch, [band, paint, bmx, council])

    rows = q._query_events(None, "today", today=date(2026, 7, 1), activity="live_music")
    names = {r["name"] for r in rows}
    # 2026-07-23 day-query sweep: row names are display-cleaned now — the
    # " at Kokopelli" venue echo is stripped because the venue renders right
    # beside the title (title_clean §6). Filtering still runs on raw titles.
    assert names == {"Live Band"}, names


def test_generic_things_to_do_excludes_civic_meetings(monkeypatch):
    band = _FakeEvent("Live Band at Kokopelli", location_name="Kokopelli")
    bmx = _FakeEvent("BMX Local Race (Kids)", location_name="Havasu BMX")
    council = _FakeEvent("City Council Meeting", location_name="City Hall")
    pz = _FakeEvent("Planning & Zoning Commission", location_name="City Hall")
    _fake_events(monkeypatch, [band, bmx, council, pz])

    rows = q._query_events(None, "upcoming", today=date(2026, 7, 1), activity=None)
    names = {r["name"] for r in rows}
    assert "City Council Meeting" not in names
    assert "Planning & Zoning Commission" not in names
    # Venue-echo title stripped (see test_live_music_filter_keeps_only_real_music).
    assert {"Live Band", "BMX Local Race (Kids)"} <= names


def test_resolver_sets_live_music_slot_for_band_phrasings():
    # L1/L2 events branch (typed straight in).
    r1 = resolve("live music tonight")
    assert r1 is not None and r1.slots.get("activity") == "live_music"
    # The phrasings the fuzzy "_events" exemplars reach on.
    for text in ("live bands tonight", "live entertainment tonight", "concerts this weekend"):
        assert _event_intent_for(text).slots.get("activity") == "live_music", text
    # A generic browse carries no music slot.
    assert "activity" not in _event_intent_for("things to do").slots


# ===========================================================================
# 1D — singular-count copy
# ===========================================================================
def test_leaf_intro_is_singular_for_one_listing():
    from app.categories.router import _leaf_intro

    one = _leaf_intro(name="Handyman", n=1, department="Home & Property")
    assert "1 well-reviewed listings" not in one
    assert "listings below rotate daily" not in one
    assert "one listing" in one.lower()

    many = _leaf_intro(name="HVAC", n=25, department="Home & Property")
    assert "25 well-reviewed listings" in many
