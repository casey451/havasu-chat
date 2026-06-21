"""Phase 2 (regrouped) — the home unified "Today in Lake Havasu" feed builder.

Verifies the five-group remap (Events / Things to do / Fitness & sports /
Classes / At the movies), the Adult/Youth fitness split, the tightened Kids tag
(Item 5), the distinct-film movie count (Item 6), the free-movie cross-post, the
cross-source de-dup (one row per real-world occurrence), and the per-film movie
grouping. Seeding mirrors tests/test_events_ui_views.py: far-future dates + uuid
suffixes + targeted cleanup, and an explicit ``now`` so the same-day expiry
never trims the rows.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Entity, Event, MovieShowtime
from app.home.today_feed import _home_group, today_feed

_LHC = ZoneInfo("America/Phoenix")
# 2099-07-13 is a Monday (see tests/test_events_ui_views.py).
_DAY = date(2099, 7, 13)
_NOW = datetime(2099, 7, 13, 6, 0, tzinfo=_LHC)  # early, so evening rows live


def _add_event(
    db, *, title, on=_DAY, start, loc, tags=None, recurring=False, source="test-today-feed"
) -> str:
    ev = Event(
        title=title,
        normalized_title=title.lower(),
        date=on,
        start_time=start,
        end_time=None,
        location_name=loc,
        location_normalized=loc.lower(),
        description="x",
        event_url="https://example.com/e",
        tags=tags or [],
        status="live",
        source=source,
        verified=True,
        is_recurring=recurring,
    )
    db.add(ev)
    db.flush()
    return ev.entity_id


def _add_movie(db, *, film, sid, theater_slug="star-cinemas", theater_name="Star Cinemas",
               at=time(18, 30), is_free=False) -> str:
    row = MovieShowtime(
        source="test-today-feed",
        source_stable_id=sid,
        theater_slug=theater_slug,
        theater_name=theater_name,
        film_title=film,
        show_date=_DAY,
        show_time=at,
        booking_url="https://example.com/book",
        is_free=is_free,
    )
    db.add(row)
    db.flush()
    return row.id


def _cleanup(eids: list[str], mids: list[str]) -> None:
    with SessionLocal() as db:
        if eids:
            db.execute(delete(Event).where(Event.entity_id.in_(eids)))
            db.execute(delete(Entity).where(Entity.id.in_(eids)))
        if mids:
            db.execute(delete(MovieShowtime).where(MovieShowtime.id.in_(mids)))
        db.commit()


def _group(feed: dict, key: str) -> dict | None:
    return next((g for g in feed["groups"] if g["key"] == key), None)


def _titles(group: dict | None) -> list[str]:
    return [r["title"] for r in group["rows"]] if group else []


def _subgroup(group: dict | None, label: str) -> dict | None:
    if not group:
        return None
    return next((s for s in group.get("subgroups", []) if s["label"] == label), None)


def test_feed_classifies_into_five_groups() -> None:
    s = uuid.uuid4().hex[:6]
    fest = f"ZZ London Bridge Days Festival {s}"  # special -> events
    market = f"ZZ Farmers Market {s}"             # community -> things_to_do
    yoga = f"ZZ Sunrise Yoga Flow {s}"            # physical class -> fitness
    cooking = f"ZZ Cooking Class {s}"             # non-physical class -> classes
    pickle = f"ZZ Pickleball Open Play {s}"       # all-day drop-in -> things_to_do
    film = f"ZZ Robin Hood {s}"                   # movie -> movies
    eids: list[str] = []
    mids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=fest, start=time(12, 0), loc="The Bridge"))
        eids.append(_add_event(db, title=market, start=time(8, 0), loc="Visitor Center"))
        eids.append(_add_event(db, title=yoga, start=time(18, 0), loc="Eight Lotus"))
        eids.append(_add_event(db, title=cooking, start=time(17, 0), loc="The Kitchen"))
        # All-day drop-in convention: midnight start + no end reads as "all day".
        eids.append(_add_event(db, title=pickle, start=time(0, 0), loc="Ark Center"))
        mids.append(_add_movie(db, film=film, sid=f"m-{s}"))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        assert fest in _titles(_group(feed, "events"))
        assert market in _titles(_group(feed, "things_to_do"))
        assert yoga in _titles(_group(feed, "fitness"))
        assert cooking in _titles(_group(feed, "classes"))
        assert pickle in _titles(_group(feed, "things_to_do"))
        movies = _group(feed, "movies")
        assert movies and any(f["title"] == film for f in movies["films"])
        # The summary line names each non-empty group.
        assert "things to do" in feed["summary"]
        # Group display order: events, things_to_do, fitness, classes, movies.
        order = ["events", "things_to_do", "fitness", "classes", "movies"]
        keys = [g["key"] for g in feed["groups"]]
        assert keys == sorted(keys, key=order.index)
        # Events opens by default; nothing else does.
        assert _group(feed, "events")["open"] is True
        assert _group(feed, "things_to_do")["open"] is False
        assert _group(feed, "fitness")["open"] is False
    finally:
        _cleanup(eids, mids)


def test_things_to_do_opens_when_no_events() -> None:
    """With no special/festival events today, Things to do leads and opens."""
    s = uuid.uuid4().hex[:6]
    market = f"ZZ Farmers Market {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=market, start=time(8, 0), loc="Visitor Center"))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        assert _group(feed, "events") is None
        ttd = _group(feed, "things_to_do")
        assert ttd and ttd["open"] is True
    finally:
        _cleanup(eids, [])


def test_fitness_splits_adult_and_youth_bmx_is_youth() -> None:
    s = uuid.uuid4().hex[:6]
    adult = f"ZZ Adult Wrestling {s}"
    youth = f"ZZ Youth Wrestling {s}"
    bmx = f"ZZ BMX Race Night {s}"  # BMX -> Youth even without a youth word
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=adult, start=time(10, 0), loc="The Tap Room", recurring=True))
        eids.append(_add_event(db, title=youth, start=time(9, 0), loc="The Tap Room", recurring=True))
        eids.append(_add_event(db, title=bmx, start=time(18, 0), loc="Havasu BMX", recurring=True))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        fitness = _group(feed, "fitness")
        assert fitness is not None
        assert adult in _titles(_subgroup(fitness, "Adult"))
        assert youth in _titles(_subgroup(fitness, "Youth"))
        assert bmx in _titles(_subgroup(fitness, "Youth"))
        # Subgroups appear in Adult-then-Youth order.
        assert [s["label"] for s in fitness["subgroups"]] == ["Adult", "Youth"]
    finally:
        _cleanup(eids, [])


def test_feed_dedupes_cross_source_twin() -> None:
    """Two scrapers carrying one real-world event (same title+date+time) collapse
    to a single feed row — the de-dup the redesign requires, in the data layer."""
    s = uuid.uuid4().hex[:6]
    title = f"ZZ Lake Cleanup {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=title, start=time(9, 0), loc="Beach", source="src-a"))
        eids.append(_add_event(db, title=title, start=time(9, 0), loc="Beach", source="src-b"))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        ttd = _group(feed, "things_to_do")
        assert _titles(ttd).count(title) == 1
    finally:
        _cleanup(eids, [])


def test_feed_audience_tags() -> None:
    s = uuid.uuid4().hex[:6]
    kids = f"ZZ Kids Craft Hour {s}"
    senior = f"ZZ Senior Bingo {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=kids, start=time(10, 0), loc="Library"))
        eids.append(_add_event(db, title=senior, start=time(11, 0), loc="Senior Center"))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        rows = {r["title"]: r for g in feed["groups"] if g["key"] != "movies" for r in g["rows"]}
        assert "Kids" in rows[kids]["tags"]
        assert "Seniors" in rows[senior]["tags"]
    finally:
        _cleanup(eids, [])


def test_kids_tag_not_applied_to_all_ages() -> None:
    """Item 5: all-ages / open-swim / bare-family rows must NOT get the Kids tag."""
    s = uuid.uuid4().hex[:6]
    allages = f"ZZ Glow in the Park All Ages {s}"
    openswim = f"ZZ Open Swim {s}"
    family = f"ZZ Family Night Golf {s}"
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=allages, start=time(19, 0), loc="Rotary Park"))
        eids.append(_add_event(db, title=openswim, start=time(0, 0), loc="Aquatic Center"))
        eids.append(_add_event(db, title=family, start=time(17, 0), loc="Bridgewater"))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        rows = {r["title"]: r for g in feed["groups"] if g["key"] != "movies" for r in g["rows"]}
        assert "Kids" not in rows[allages]["tags"]
        assert "Kids" not in rows[openswim]["tags"]
        assert "Kids" not in rows[family]["tags"]
    finally:
        _cleanup(eids, [])


def test_feed_shows_full_day_keeping_past_items_muted() -> None:
    """Item 1: the home reflects the WHOLE day. A morning yoga + morning cooking
    class are already over by an afternoon ``now``, yet their groups (Fitness &
    sports, Classes) still render and the rows are flagged ``is_past`` (muted, not
    dropped) — the regression that emptied those groups by afternoon."""
    s = uuid.uuid4().hex[:6]
    yoga = f"ZZ Sunrise Yoga Flow {s}"      # 8 AM physical class -> fitness
    cooking = f"ZZ Cooking Class {s}"        # 9 AM non-physical class -> classes
    evening = f"ZZ Evening Street Market {s}"  # 7 PM -> things_to_do (still upcoming)
    afternoon = datetime(2099, 7, 13, 15, 0, tzinfo=_LHC)  # 3 PM — past the morning
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=yoga, start=time(8, 0), loc="Eight Lotus", recurring=True))
        eids.append(_add_event(db, title=cooking, start=time(9, 0), loc="The Kitchen"))
        eids.append(_add_event(db, title=evening, start=time(19, 0), loc="Main St"))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=afternoon)
        # Morning-only groups still render in the afternoon.
        fitness = _group(feed, "fitness")
        classes = _group(feed, "classes")
        assert fitness is not None and yoga in _titles(fitness)
        assert classes is not None and cooking in _titles(classes)
        # Past rows kept but flagged; the upcoming evening row is not.
        rows = {r["title"]: r for g in feed["groups"] if g["key"] != "movies" for r in g["rows"]}
        assert rows[yoga]["is_past"] is True
        assert rows[cooking]["is_past"] is True
        assert rows[evening]["is_past"] is False
        # Counts reflect the whole day (past items still counted).
        assert feed["counts"]["fitness"] == 1
        assert feed["counts"]["classes"] == 1
    finally:
        _cleanup(eids, [])


def test_cooking_party_lands_in_classes_but_sale_stays_things_to_do() -> None:
    """Item 2: an instructional cooking session titled "Party" routes to Classes
    even though the shared classifier keys off "Party"; a "Pottery Sale" carries
    an instructional word but reads as a market, so the guard keeps it in Things
    to do."""
    s = uuid.uuid4().hex[:6]
    party = f"ZZ Tacos A Family Cooking Party {s}"  # instructional -> classes
    sale = f"ZZ Holiday Pottery Sale {s}"           # market -> things_to_do
    eids: list[str] = []
    with SessionLocal() as db:
        eids.append(_add_event(db, title=party, start=time(17, 0), loc="The Kitchen"))
        eids.append(_add_event(db, title=sale, start=time(10, 0), loc="Art Center"))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        assert party in _titles(_group(feed, "classes"))
        assert party not in _titles(_group(feed, "things_to_do"))
        assert sale in _titles(_group(feed, "things_to_do"))
        assert sale not in _titles(_group(feed, "classes"))
    finally:
        _cleanup(eids, [])


def test_kids_tag_vetoed_for_family_all_ages_even_with_youth_data_tag() -> None:
    """Item 3 (the live leak): the ingest loaders tag "family"/"all ages" rows
    with a ``youth`` data tag, which over-applied the Kids tag. An all-ages /
    family title now vetoes it — but a neutrally-titled row the loader marked
    ``youth`` is still genuinely kid-targeted and keeps the tag."""
    s = uuid.uuid4().hex[:6]
    fam_golf = f"ZZ Family Night Golf {s}"
    fam_bowl = f"ZZ Family Glow Bowling {s}"
    allages = f"ZZ Glow in the Park All Ages {s}"
    real_youth = f"ZZ Pickleball Clinic {s}"  # neutral title, youth tag in data
    eids: list[str] = []
    with SessionLocal() as db:
        # These three carry the loader's ``youth`` tag yet are everyone-welcome.
        eids.append(_add_event(db, title=fam_golf, start=time(17, 0), loc="Bridgewater", tags=["youth"]))
        eids.append(_add_event(db, title=fam_bowl, start=time(18, 0), loc="Havasu Lanes", tags=["youth"]))
        eids.append(_add_event(db, title=allages, start=time(19, 0), loc="Rotary Park", tags=["youth"]))
        eids.append(_add_event(db, title=real_youth, start=time(16, 0), loc="Ark Center", tags=["youth"], recurring=True))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        rows = {r["title"]: r for g in feed["groups"] if g["key"] != "movies" for r in g["rows"]}
        assert "Kids" not in rows[fam_golf]["tags"]
        assert "Kids" not in rows[fam_bowl]["tags"]
        assert "Kids" not in rows[allages]["tags"]
        # A youth-tagged row with no all-ages/family marker stays kid-targeted.
        assert "Kids" in rows[real_youth]["tags"]
    finally:
        _cleanup(eids, [])


def test_feed_movie_groups_theaters_per_film() -> None:
    """One film at two theaters collapses to a single film row with both theaters
    in its expand."""
    s = uuid.uuid4().hex[:6]
    film = f"ZZ Two-Theater Flick {s}"
    mids: list[str] = []
    with SessionLocal() as db:
        mids.append(_add_movie(db, film=film, sid=f"sc-{s}",
                               theater_slug="star-cinemas", theater_name="Star Cinemas",
                               at=time(12, 40)))
        mids.append(_add_movie(db, film=film, sid=f"mh-{s}",
                               theater_slug="movies-havasu", theater_name="Movies Havasu",
                               at=time(13, 0)))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        movies = _group(feed, "movies")
        card = next(f for f in movies["films"] if f["title"] == film)
        assert len(card["theaters"]) == 2
        assert "2 theaters" in card["summary"]
    finally:
        _cleanup([], mids)


def test_movie_count_is_distinct_films_not_film_times_theater() -> None:
    """Item 6: one film at two theaters counts as ONE film, and the summary noun
    is 'films', never 'movies'."""
    s = uuid.uuid4().hex[:6]
    film = f"ZZ Counting Film {s}"
    mids: list[str] = []
    with SessionLocal() as db:
        mids.append(_add_movie(db, film=film, sid=f"a-{s}", theater_slug="star-cinemas",
                               theater_name="Star Cinemas", at=time(12, 0)))
        mids.append(_add_movie(db, film=film, sid=f"b-{s}", theater_slug="movies-havasu",
                               theater_name="Movies Havasu", at=time(13, 0)))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        movies = _group(feed, "movies")
        assert movies["count"] == 1            # distinct films, not 2 film×theater
        assert feed["counts"]["movies"] == 1
        assert "1 film" in feed["summary"] and "movie" not in feed["summary"]
    finally:
        _cleanup([], mids)


def test_free_movie_cross_posts_to_things_to_do_and_tags_kids() -> None:
    """A free community screening appears in BOTH At the movies and Things to do,
    and is tagged Kids (the summer kids series) even without a kid word."""
    s = uuid.uuid4().hex[:6]
    film = f"ZZ Toy Story {s}"  # no kid keyword in the title
    mids: list[str] = []
    with SessionLocal() as db:
        mids.append(_add_movie(db, film=film, sid=f"free-{s}", at=time(10, 0), is_free=True))
        db.commit()
    try:
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        movies = _group(feed, "movies")
        card = next(f for f in movies["films"] if f["title"] == film)
        assert card["is_free"] is True
        assert "Kids" in card["tags"]
        assert "Free" in card["summary"]
        # Cross-posted into Things to do as well.
        ttd = _group(feed, "things_to_do")
        cross = next((r for r in ttd["rows"] if r["title"] == film), None)
        assert cross is not None
        assert "Kids" in cross["tags"]
    finally:
        _cleanup([], mids)


def test_feed_empty_day_has_no_groups() -> None:
    with SessionLocal() as db:
        feed = today_feed(db, day=date(2099, 7, 14), now=datetime(2099, 7, 14, 6, 0, tzinfo=_LHC))
    # A far-future Tuesday with nothing seeded: no event groups. (Venue "open
    # today" rows are weekday-driven and may exist, but the seeded-data groups
    # above are what we assert on; here we assert no events/classes/movies.)
    assert _group(feed, "events") is None
    assert _group(feed, "classes") is None
    assert _group(feed, "movies") is None


def test_open_venue_rows_have_no_open_prefix() -> None:
    """FIX_DAYPICKER item 5: open-all-day venue rows read as a bare hours range
    ("12–10 PM"), not "Open 12–10 PM" — uniform with every other feed row."""
    sat = date(2099, 7, 18)  # Saturday — the drop-in family venues publish hours.
    with SessionLocal() as db:
        feed = today_feed(db, day=sat, now=datetime(2099, 7, 18, 6, 0, tzinfo=_LHC))
    ttd = _group(feed, "things_to_do")
    assert ttd is not None, "Saturday should surface open-venue rows under Things to do"
    # No row carries the dropped verb, and at least one bare hours range is present.
    for row in ttd["rows"]:
        assert not row["time_label"].startswith("Open "), row["time_label"]
    assert any("–" in row["time_label"] for row in ttd["rows"])


def test_markets_route_to_things_to_do_over_class_typing() -> None:
    """Item 4: markets / art walks / swap meets group under Things to do even when
    the source typed them as a recurring class (the live Farmers Market arrives
    flagged recurring and otherwise lands in Classes)."""
    recurring_class = (True, time(8, 0), None)  # source-typed as a recurring class
    for title in (
        "Lake Havasu Farmers Market",
        "First Friday Vendor Night",
        "Downtown Art Walk",
        "Havasu Swap Meet",
        "Spring Craft Fair",
        "Riverfront Night Market",
    ):
        assert (
            _home_group(title, None, False, recurring_class[0], recurring_class[1], recurring_class[2])
            == "things_to_do"
        ), title
    # A genuine instructional class is NOT swept in by the market rule.
    assert (
        _home_group("Arts & Crafts", None, False, True, time(15, 0), None) == "classes"
    )


def test_farmers_market_shows_under_things_to_do_in_feed() -> None:
    """End-to-end: a recurring, class-typed Farmers Market event lands in the
    Things to do group of the rendered feed, not Classes."""
    suffix = uuid.uuid4().hex[:6]
    title = f"ZZ Lake Havasu Farmers Market {suffix}"
    eids: list[str] = []
    try:
        with SessionLocal() as db:
            eids.append(
                _add_event(db, title=title, start=time(8, 0), loc="Main St", recurring=True)
            )
            db.commit()
        with SessionLocal() as db:
            feed = today_feed(db, day=_DAY, now=_NOW)
        assert title in _titles(_group(feed, "things_to_do"))
        assert title not in _titles(_group(feed, "classes"))
    finally:
        _cleanup(eids, [])
