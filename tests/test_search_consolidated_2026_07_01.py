"""2026-07-01 consolidated search fixes, Phase 1 (ASKHAVA_SEARCH_AUDIT
2026-07-01 CONSOLIDATED — honest fallback + calendar scope + quick routing).

* 1.1 — broad-bucket provider intents (shopping / lodging / on-the-water /
  fitness / generic eat) carry a topical gate: a query naming a topic no row in
  the bucket mentions ("gun store", "tubing", "golf cart rental") returns
  nothing, and the intent layer answers with the honest gap template instead of
  handing Tier 3 a chance to guess an off-catalog business.
* 1.2 — the Tier-3 system prompt ships the catalog-only / out-of-area guard.
* 1.3 — /calendar routing fires ONLY on explicit time/event intent; evergreen
  asks ("things to do", "nightlife", "happy hour", "state park", "party boat
  rental") get real directory destinations.
* 1.4 — civic/government meetings leave the /calendar default day columns (a
  collapsed Local Government section) and the month-grid cells.
* 1.5 — quick routing adds ("hair", the phone-repair variants, waverunner /
  sea-doo rentals) plus rent-words in the service-intent filler.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.categories.leaf_query import (
    _QUERY_TO_LEAF,
    _QUERY_TO_LEAF_SEARCH_ADD_2026_07_01,
    _QUERY_TO_URL_2026_07_01,
    _normalize,
    match_direct_destination,
)
from app.chat.intents import queries as q
from app.chat.intents import runtime
from app.chat.intents.resolver import ResolvedIntent, resolve
from app.db.database import SessionLocal
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Provider
from app.db.seed_helpers import derive_provider_slug
from app.home.calendar_view import is_discovery_query

_LAT, _LNG = 34.4839, -114.3225


# ===========================================================================
# 1.3 / 1.5 — routing dictionary additions (DB-free)
# ===========================================================================
_ROUTING_CASES = {
    "nightlife": "bars-and-breweries",
    "happy hour": "bars-and-breweries",
    "date night": "restaurants",
    "waterfront dining": "restaurants",
    "lake havasu state park": "beaches-and-swim-areas",
    "state park": "beaches-and-swim-areas",
    "party boat": "boat-and-watercraft-rentals",
    "party boat rental": "boat-and-watercraft-rentals",
    "boat rental with captain": "boat-tours-and-charters",
    "captained boat tour": "boat-tours-and-charters",
    "hair": "hair-salons-and-barbers",
    "cell phone repair": "computer-and-it-repair",
    "phone repair": "computer-and-it-repair",
    "iphone repair": "computer-and-it-repair",
    "phone screen repair": "computer-and-it-repair",
    "waverunner rental": "jet-ski-and-watersports",
    "sea doo rental": "jet-ski-and-watersports",
}


def test_new_terms_route_to_expected_leaf():
    for raw, slug in _ROUTING_CASES.items():
        norm = _normalize(raw)
        assert norm in _QUERY_TO_LEAF, (raw, norm)
        assert _QUERY_TO_LEAF[norm] == slug, (raw, norm, _QUERY_TO_LEAF[norm])


def test_new_keys_normalize_to_themselves():
    # Every key must be the OUTPUT of _normalize, else it can never be hit.
    for terms in _QUERY_TO_LEAF_SEARCH_ADD_2026_07_01.values():
        for term in terms:
            assert _normalize(term) == term, (term, _normalize(term))
    for term in _QUERY_TO_URL_2026_07_01:
        assert _normalize(term) == term, (term, _normalize(term))


def test_direct_destinations():
    assert match_direct_destination("things to do") == (
        "/categories/things-to-do-and-attractions"
    )
    assert match_direct_destination("free things to do in lake havasu") == (
        "/categories/things-to-do-and-attractions"
    )
    assert match_direct_destination("stuff to do") == (
        "/categories/things-to-do-and-attractions"
    )
    assert match_direct_destination("things to do with kids") == "/family"
    # Time-scoped asks are NOT evergreen — the calendar keeps them.
    assert match_direct_destination("things to do this weekend") is None
    assert match_direct_destination("plumbers") is None


def test_new_terms_do_not_corrupt_common_words_via_spell_correct():
    # Routing keys feed normalizer._spell_vocab; a new token one edit from a
    # common word would silently "correct" real queries. Guard the words the
    # new terms sit near ("hair", "phone", "party", "night"...).
    from app.chat.normalizer import spell_correct

    for phrase in (
        "chair repair",
        "fair grounds",
        "pair of shoes",
        "diving lessons",
        "flight school",
        "screen doors",
        "date shakes",
    ):
        assert spell_correct(phrase) == phrase, (phrase, spell_correct(phrase))


def test_expansion_did_not_override_prior_entries():
    # setdefault must preserve pre-existing mappings.
    assert _QUERY_TO_LEAF["hair salon"] == "hair-salons-and-barbers"
    assert _QUERY_TO_LEAF["computer repair"] == "computer-and-it-repair"
    assert _QUERY_TO_LEAF["boat rentals"] == "boat-and-watercraft-rentals"
    assert _QUERY_TO_LEAF["boat tours"] == "boat-tours-and-charters"


def test_rent_words_enable_service_intent_but_not_golf_cart():
    from app.categories.leaf_query import _service_intent_slug

    # "<mapped-category> rental" now routes via the span logic (the leftover
    # rent word is filler)...
    assert _service_intent_slug("jet skis rental") == "jet-ski-and-watersports"
    assert _service_intent_slug("need a pontoon rental") == "boat-and-watercraft-rentals"
    # ...and "golf cart rental" — unrouted in Phase 1 — got its real home in
    # Phase 4 (an exact key on the golf-carts leaf, Premier Golf Cars).
    assert _service_intent_slug("golf cart rental") == "golf-carts"


# ===========================================================================
# 1.3 — /calendar routing scope
# ===========================================================================
@pytest.mark.parametrize(
    "query",
    [
        "things to do",
        "date night",
        "nightlife",
        "waterfront dining",
        "happy hour",
        "lake havasu state park",
        "party boat rental",
        "hair",
        "gun store",
        "best tacos",
    ],
)
def test_evergreen_asks_are_not_discovery(query):
    assert not is_discovery_query(query), query


@pytest.mark.parametrize(
    "query",
    [
        "things to do this weekend",
        "events today",
        "events this week",
        "live music tonight",
        "taco festival",
        "what's happening",
        "concerts this weekend",
        "farmers market",
        "anything fun on saturday",
    ],
)
def test_time_and_event_intent_still_routes_to_calendar(query):
    assert is_discovery_query(query), query


# ===========================================================================
# 1.1 — provider topical gate
# ===========================================================================
def test_provider_activity_terms_extraction():
    # Topical nouns survive; bucket/filler words don't.
    assert q._provider_activity_terms("gun store") == ["gun"]
    assert q._provider_activity_terms("golf cart rental") == ["golf", "cart"]
    assert q._provider_activity_terms("snorkeling") == ["snorkeling"]
    assert q._provider_activity_terms("weight loss", "gym_fitness") == ["weight", "loss"]
    # Generic bucket browses extract nothing (no gate).
    assert q._provider_activity_terms("shopping in lake havasu") == []
    assert q._provider_activity_terms("places to stay") == []
    assert q._provider_activity_terms("boat rentals") == []
    assert q._provider_activity_terms("where should we eat", "eat_find") == []
    assert q._provider_activity_terms("any good gyms", "gym_fitness") == []
    assert q._provider_activity_terms("pickleball courts", "pickleball") == []


def test_topic_pattern_is_word_boundary():
    # Substring matching would false-pass "side" in "Riverside".
    assert not q._topic_pattern("side").search("riverside marina")
    assert q._topic_pattern("side").search("side by side adventures")
    # Singular/plural tolerance both ways.
    assert q._topic_pattern("gym").search("havasu gyms")
    assert q._topic_pattern("kayaks").search("kayak king")


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def _seed_provider(session, name, *, category, subcategory=None, google=None):
    prov = Provider(
        provider_name=name,
        category=category,
        subcategory=subcategory,
        google_primary_category=google,
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


def _cleanup(db, *provs):
    from sqlalchemy import delete

    from app.db.models import Entity, EntityCategory, Location

    for p in provs:
        eid = p.entity_id
        db.execute(delete(Provider).where(Provider.id == p.id))
        if eid:
            db.execute(delete(Location).where(Location.entity_id == eid))
            db.execute(delete(EntityCategory).where(EntityCategory.entity_id == eid))
            db.execute(delete(Entity).where(Entity.id == eid))
    db.commit()


def test_gun_store_never_returns_the_shopping_grab_bag(db):
    suf = uuid.uuid4().hex[:8]
    fabric = _seed_provider(
        db, f"Botero Fabrics {suf}", category="retail", subcategory="specialty"
    )
    carts = _seed_provider(
        db, f"3-T's Golf Cars {suf}", category="retail", subcategory="specialty"
    )
    try:
        resolved = resolve("gun store")
        assert resolved is not None and resolved.intent_key == "shopping_find"
        result = q.run_query(resolved, db, raw_query="gun store")
        assert result.rows == [], [r["name"] for r in result.rows]
        # ...and the empty is claimed honestly, never handed to Tier 3.
        answer = runtime._honest_empty_answer(resolved, result, "gun store")
        assert answer is not None
        assert "I don't see any gun listed" in answer.text
        assert "/contribute" in answer.text
    finally:
        _cleanup(db, fabric, carts)


@pytest.mark.parametrize("query", ["tubing", "snorkeling"])
def test_water_bucket_junk_is_gated(db, query):
    suf = uuid.uuid4().hex[:8]
    storage = _seed_provider(
        db, f"1595 Storage of Havasu {suf}", category="lake_recreation"
    )
    marine = _seed_provider(
        db, f"Above Water Marine Services {suf}", category="lake_recreation"
    )
    try:
        resolved = resolve(query) if query == "tubing" else ResolvedIntent(
            "on_the_water", {}, "L3"
        )
        if query == "tubing":
            assert resolved is not None and resolved.intent_key == "on_the_water"
        result = q.run_query(resolved, db, raw_query=query)
        assert result.rows == [], (query, [r["name"] for r in result.rows])
        answer = runtime._honest_empty_answer(resolved, result, query)
        assert answer is not None and f"I don't see any {query} listed" in answer.text
    finally:
        _cleanup(db, storage, marine)


@pytest.mark.parametrize(
    "query",
    ["golf cart rental", "bike rental", "e-bike rental", "side by side rental"],
)
def test_non_boat_rentals_never_return_boat_companies(db, query):
    suf = uuid.uuid4().hex[:8]
    boats = _seed_provider(
        db, f"Agua Azul Boat Rentals {suf}", category="boat_rental"
    )
    bridge = _seed_provider(
        db, f"At The Bridge Watercraft Rental {suf}", category="boat_rental"
    )
    try:
        # These reach boat_rental via L3 fuzzy in prod; pin the gate itself.
        resolved = ResolvedIntent("boat_rental", {}, "L3")
        result = q.run_query(resolved, db, raw_query=query)
        assert result.rows == [], (query, [r["name"] for r in result.rows])
        answer = runtime._honest_empty_answer(resolved, result, query)
        assert answer is not None, query
        assert "listed in the local directory yet" in answer.text
    finally:
        _cleanup(db, boats, bridge)


def test_weight_loss_never_returns_bmx_or_golf(db):
    suf = uuid.uuid4().hex[:8]
    bmx = _seed_provider(db, f"Tri-State BMX {suf}", category="fitness_sports")
    try:
        resolved = ResolvedIntent("gym_fitness", {}, "L1")
        result = q.run_query(resolved, db, raw_query="weight loss")
        assert result.rows == [], [r["name"] for r in result.rows]
        answer = runtime._honest_empty_answer(resolved, result, "weight loss")
        assert answer is not None and "weight loss" in answer.text
    finally:
        _cleanup(db, bmx)


def test_generic_bucket_browses_still_list(db):
    suf = uuid.uuid4().hex[:8]
    shop = _seed_provider(
        db, f"Main Street Boutique {suf}", category="retail", subcategory="boutiques"
    )
    hotel = _seed_provider(
        db, f"London Bridge Resort {suf}", category="lodging", subcategory="hotels"
    )
    boats = _seed_provider(
        db, f"Havasu Boat Rentals {suf}", category="boat_rental"
    )
    try:
        for query, name in (
            ("shopping in lake havasu", shop.provider_name),
            ("places to stay", hotel.provider_name),
            ("boat rentals", boats.provider_name),
        ):
            resolved = resolve(query)
            assert resolved is not None, query
            result = q.run_query(resolved, db, raw_query=query)
            names = {r["name"] for r in result.rows}
            assert name in names, (query, names)
    finally:
        _cleanup(db, shop, hotel, boats)


def test_topical_match_keeps_the_list(db):
    suf = uuid.uuid4().hex[:8]
    kayak = _seed_provider(db, f"Kayak King Rentals {suf}", category="boat_rental")
    other = _seed_provider(db, f"Sandbar Pontoons {suf}", category="boat_rental")
    try:
        resolved = resolve("where can i rent a kayak")
        assert resolved is not None and resolved.intent_key == "boat_rental"
        result = q.run_query(resolved, db, raw_query="where can i rent a kayak")
        names = {r["name"] for r in result.rows}
        # One row matches "kayak" → the whole (already relevance-ranked) list
        # survives; the gate is all-or-nothing.
        assert kayak.provider_name in names, names
    finally:
        _cleanup(db, kayak, other)


def test_pet_friendly_hotels_pinned_honest_or_matching(db):
    # Known behavior change (accepted until the attribute filter ships): with
    # no lodging row carrying a "pet" signal this flips to the honest template;
    # with one, the list survives. Never junk.
    suf = uuid.uuid4().hex[:8]
    hotel = _seed_provider(
        db, f"Windsor Inn {suf}", category="lodging", subcategory="hotels"
    )
    try:
        resolved = resolve("pet friendly hotels")
        assert resolved is not None and resolved.intent_key == "lodging_find"
        result = q.run_query(resolved, db, raw_query="pet friendly hotels")
        if result.rows:
            pat = q._topic_pattern("pet")
            assert any(
                pat.search(f"{r['name']} {r.get('category') or ''}".lower())
                for r in result.rows
            ), [r["name"] for r in result.rows]
        else:
            answer = runtime._honest_empty_answer(resolved, result, "pet friendly hotels")
            assert answer is not None and "pet friendly" in answer.text
    finally:
        _cleanup(db, hotel)


# ===========================================================================
# 1.2 — Tier 3 catalog-only / out-of-area guard
# ===========================================================================
def test_tier3_prompt_ships_out_of_area_guard():
    from app.chat.tier3_handler import _load_tier3_system_prompt

    prompt = _load_tier3_system_prompt()
    assert "Catalog-only recommendations" in prompt
    assert "Kingman" in prompt
    assert "Bullhead City" in prompt
    assert "Parker" in prompt
    assert "Needles" in prompt
    assert "Havasu Landing" in prompt
    assert "not present in the Context block" in prompt


# ===========================================================================
# 1.4 — civic meetings out of the /calendar default columns + month cells
# ===========================================================================
def _fake_day_groups(rows_events, rows_civic):
    def _groups(db, *, day, family=False, seniors=False, now=None, events_only=False):
        groups = []
        if rows_events:
            groups.append({"key": "events", "label": "Things to Do", "icon": "",
                           "count": len(rows_events), "rows": rows_events})
        if rows_civic:
            groups.append({"key": "civic", "label": "Local Government", "icon": "",
                           "count": len(rows_civic), "rows": rows_civic})
        return groups

    return _groups


def _row(title, venue="", time_label="9 AM"):
    return {"sort": (0, 0), "time_label": time_label, "title": title,
            "venue": venue, "url": None, "recurring": False, "tags": []}


def test_calendar_default_columns_exclude_civic(monkeypatch):
    from app.home import calendar_view, events_views

    market = _row("Farmers Market", venue="Main Street")
    board = _row("Board of Adjustment Meeting", venue="City Hall")
    monkeypatch.setattr(
        events_views, "day_groups", _fake_day_groups([market], [board])
    )
    cal = calendar_view.build_calendar(db=None, q="", today=date(2026, 7, 1))
    for col in cal["columns"]:
        titles = [e["title"] for e in col["entries"]]
        assert "Board of Adjustment Meeting" not in titles
        assert "Farmers Market" in titles
        civic_titles = [e["title"] for e in col["civic_entries"]]
        assert civic_titles == ["Board of Adjustment Meeting"]
        # The headline count answers "how many plans", not agenda items.
        assert col["count"] == 1
    assert cal["total"] == 7  # one leisure row per day of the 7-day window


def test_calendar_catches_civic_row_misfiled_into_events(monkeypatch):
    # A civic meeting that rode into a leisure bucket (venue-signal rows the
    # bucket heuristic misses) is still peeled out via is_civic_meeting.
    from app.home import calendar_view, events_views

    hearing = _row("Public Hearing: Zoning Variance", venue="City Hall")
    monkeypatch.setattr(
        events_views, "day_groups", _fake_day_groups([hearing], [])
    )
    cal = calendar_view.build_calendar(db=None, q="", today=date(2026, 7, 1))
    assert cal["total"] == 0
    for col in cal["columns"]:
        assert col["entries"] == []
        assert [e["title"] for e in col["civic_entries"]] == [
            "Public Hearing: Zoning Variance"
        ]


def test_civic_meetings_route_to_the_community_tier_not_the_headliners():
    # The legacy /calendar list (and its cal-civic <details>) was deleted with
    # the 2026-07-02 HOME_REDESIGN flag collapse — it was never served on prod
    # (v4 has been on since ~06-23). The surviving civic contract on the v4
    # surfaces: a Board of Adjustment meeting never ranks as a headline event
    # (sandstone._event_tier routes is_civic titles to the COMMUNITY tier) and
    # the month grid excludes it outright (test_month_grid_cells_exclude_civic).
    import app.home.sandstone as sandstone

    civic = sandstone._event_tier(
        title="Board of Adjustment Meeting", tags=[], featured=False, recurring=False
    )
    assert civic == sandstone._TIER_COMMUNITY
    # ...and never as the headline tier a Farmers Market special could take.
    assert civic != sandstone._TIER_SPECIAL


def test_month_grid_cells_exclude_civic(monkeypatch):
    import app.home.sandstone as sandstone

    class _Ev:
        def __init__(self, title, location_name=""):
            self.title = title
            self.location_name = location_name
            self.description = ""
            self.tags = []
            self.start_time = None
            self.end_time = None
            self.featured = False
            self.is_recurring = False

    board = _Ev("Board of Adjustment Meeting", "City Hall")
    market = _Ev("Farmers Market", "Main Street")
    monkeypatch.setattr(
        sandstone,
        "_live_events_by_day",
        lambda db, *, window_start, window_end: {date(2026, 7, 15): [board, market]},
    )
    monkeypatch.setattr(
        sandstone, "class_occurrences_in_window",
        lambda db, *, window_start, window_end, horizon_today=None: [],
    )
    month = sandstone.calendar_month(
        db=None, year=2026, month=7, today=date(2026, 7, 1)
    )
    titles = [
        p["title"]
        for week in month["weeks"]
        for cell in week
        if cell.get("in_month")
        for p in cell.get("events", []) or []
    ]
    assert "Farmers Market" in titles
    assert all("Board of Adjustment" not in t for t in titles)
