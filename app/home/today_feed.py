"""Home "Today in Lake Havasu" unified feed (Phase 2; regrouped polish pass).

The home feed is the heart of the page: one scannable list for today, grouped
into five collapsed sections — **Events**, **Things to do**, **Fitness &
sports**, **Classes**, **At the movies**. The Events group opens by default when
it has items today; otherwise **Things to do** opens. Every other group loads
collapsed, and every row is collapsed until tapped (nested ``<details>``).

This builder is a *presentation remap* over the SAME deduped pipeline the
``/events-ui`` accordion uses (:func:`app.home.events_views.day_groups`), so the
home feed and the full calendar can never disagree on what's on or double-count
a cross-source twin:

* ``_live_events_by_day`` expands rrule/rdate occurrences and collapses
  cross-source event twins (two scrapers, one real-world event).
* ``class_occurrences_in_window`` + ``drop_event_duplicates`` add venue Schedule
  classes and drop any class occurrence that also exists as an Event row by
  ``(title, date, start_time)`` — the EVENT/CLASS de-dup the redesign calls for
  (e.g. the Senior Center "Exercise Class" printed once, not twice).

The five-group mapping (regrouped 2026-06-20 from Casey's live review):

* **Events** — *actual events only*: festivals and one-time special happenings
  (London Bridge Days, boat/car shows, concerts, parades, grand openings,
  expos). The shared tier classifier's SPECIAL tier. Leads the feed.
* **Things to do** — the bulk of the day plus all drop-in / open-all-day venues
  and free community movie nights (markets, open swim, golf night, glow bowling,
  the trampoline park, arcade, indoor play). Absorbs the old "Open all day".
* **Fitness & sports** — recurring physical activity, split into **Adult** and
  **Youth** sub-sections (yoga, pilates, martial arts, wrestling, dance-fitness,
  gymnastics → Youth, **BMX racing → Youth**).
* **Classes** — non-physical instructional one-offs / registered things (the
  cooking class, art, crafts, lessons).
* **At the movies** — one row per *distinct film* with per-theater showtimes in
  the expand; free community screenings also cross-post into Things to do.

Small audience tags (Kids / Seniors) ride on rows where the data supports it.
The Kids tag is tightened (Item 5): only genuinely kid-targeted rows get it —
all-ages, open/family swim, and bare "family" rows do NOT — so it no longer
over-applies the way ``is_family_event`` (the /events-ui parent-filter) does.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any

from sqlalchemy.orm import Session

from app.events.class_occurrences import (
    class_occurrences_in_window,
    drop_event_duplicates,
)
from app.events.event_type_tags import event_type_label
from app.events.senior_filter import is_senior_event
from app.events.time_labels import short_time_label, time_sort_key
from app.events.title_clean import clean_event_title
from app.home.event_buckets import TIER_SPECIAL, is_dropin_rec
from app.home.events_views import _group_for, _occurrence_expired, _row_time_label
from app.home.family_venues import open_today_rows
from app.home.sandstone import _event_tier, _live_events_by_day
from app.movies.queries import normalize_film_title, showtimes_for_day

# Display order + labels for the home feed groups. ``key`` is the stable CSS/JSON
# hook (data-group, the swatch class); never user-visible.
FEED_GROUP_DEFS: tuple[tuple[str, str], ...] = (
    ("events", "Events"),
    ("things_to_do", "Things to do"),
    ("fitness", "Fitness & sports"),
    ("classes", "Classes"),
    ("movies", "At the movies"),
)

# Rollup nouns for the summary line. Movies count DISTINCT films (Item 6), so the
# noun is "film(s)", never "movie(s)".
_GROUP_NOUNS: dict[str, tuple[str, str]] = {
    "events": ("event", "events"),
    "things_to_do": ("thing to do", "things to do"),
    "fitness": ("fitness session", "fitness sessions"),
    "classes": ("class", "classes"),
    "movies": ("film", "films"),
}

# All-day drop-in titles whose 00:00/None start means "runs all day" rather than
# "time unknown" — these route to "Things to do". Mirrors
# :data:`app.home.events_views._ALL_DAY_TITLE_RE` (kept local to avoid importing a
# private name across modules).
_ALL_DAY_TITLE_RE = re.compile(r"\b(?:pickleball|open play)\b", re.IGNORECASE)

# Physical-activity signals → "Fitness & sports". Word-boundary matched (a plural
# or gerund tail allowed). A class-tier occurrence carrying any of these is a
# workout/sport, not a sit-down class.
_FITNESS_HINTS: tuple[str, ...] = (
    "yoga", "vinyasa", "pilates", "reformer", "barre",
    "martial", "karate", "jiu jitsu", "jiu-jitsu", "bjj", "taekwondo", "judo",
    "mma", "kickbox", "muay thai", "boxing", "wrestling", "grappling", "dojo",
    "gymnastics", "tumbling", "tumble", "tumbler", "gymtots", "cheer", "ninja",
    "dance", "ballet", "tap", "jazz", "hip hop", "hip-hop", "ballroom", "zumba",
    "aerobics", "aqua", "aquacise", "water aerobics", "water fitness", "lap swim",
    "spin", "spinning", "cycling", "crossfit", "cross fit", "bootcamp",
    "boot camp", "hiit", "cardio", "strength", "conditioning", "sculpt",
    "circuit", "fitness", "pickleball", "tennis", "racquetball", "basketball",
    "volleyball", "bmx", "tai chi", "dodgeball", "pump track", "motocross",
)
# Non-physical instructional signals → "Classes". Checked only inside the class
# tier, after the fitness check, so "yoga class" stays in Fitness and "cooking
# class" lands here.
_CLASS_NONPHYSICAL_HINTS: tuple[str, ...] = (
    "cooking", "cook", "bake", "baking", "culinary", "chef",
    "art", "painting", "paint", "drawing", "draw", "pottery", "ceramics",
    "craft", "crafting", "sewing", "quilting", "knitting", "crochet",
    "guitar", "piano", "ukulele", "language", "spanish", "writing",
    "book club", "lesson", "workshop", "class", "seminar", "course",
)


def _compile_word_hints(hints: tuple[str, ...]) -> "re.Pattern[str]":
    """Word-boundary alternation allowing a plural/gerund tail (e.g. ``class`` →
    ``classes``, ``tumble`` → ``tumbling``)."""
    return re.compile("|".join(r"\b" + re.escape(h) + r"(?:e?s|ing)?\b" for h in hints))


_FITNESS_RE = _compile_word_hints(_FITNESS_HINTS)
_CLASS_NONPHYSICAL_RE = _compile_word_hints(_CLASS_NONPHYSICAL_HINTS)

# Instructional FALLBACK route to "Classes" (Item 2). The shared classifier keys
# the 5 PM "Tacos — A family Cooking Party" off "Party" and files it under Things
# to do; this catches cooking/art/craft/lesson sessions the classifier missed
# even when they're titled "party", "social", or "workshop". Deliberately
# narrower than :data:`_CLASS_NONPHYSICAL_HINTS` — it drops broad nouns ("art",
# "craft", "class", "course") that also head non-instructional rows (art walk,
# craft fair, craft beer, golf course) so the fallback never pulls a
# market/social/festival into Classes; the :data:`_NOT_A_CLASS_RE` guard below
# is a second backstop.
_CLASS_FALLBACK_HINTS: tuple[str, ...] = (
    "cooking", "culinary", "painting", "pottery", "ceramics",
    "sewing", "quilting", "knitting", "crochet", "calligraphy", "watercolor",
    "paint and sip", "paint & sip", "sip and paint", "sip & paint",
    "wine and paint", "wine & paint", "workshop", "lesson",
)
_CLASS_FALLBACK_RE = _compile_word_hints(_CLASS_FALLBACK_HINTS)
# Non-instructional contexts that keep a row in Things to do even if an activity
# word appears (a "Craft Fair" / "Bake Sale" / "Wine Tasting" is not a class).
_NOT_A_CLASS_RE = re.compile(
    r"\b(fair|market|sale|tasting|festival|fest|expo|swap|fundraiser)\b",
    re.IGNORECASE,
)

# Community market / art-walk happenings that some sources ingest typed as a
# "class" (e.g. the recurring "Lake Havasu Farmers Market" arrives flagged
# recurring and routes to Classes). These are drop-in things to do, never
# classes, so a title match here OVERRIDES the inherited class typing and files
# the row under "Things to do" (Item 4). Word-boundary matched; "market"/"fair"
# require a qualifier (farmers/swap/flea/craft/vendor/street/night/art) so a
# generic "Arts & Crafts" class or a one-word "Market" in another context isn't
# swept in.
_MARKET_RE = re.compile(
    r"\b("
    r"farmers?\s*market|swap\s*meet|flea\s*market|night\s*market|"
    r"craft\s*(?:fair|market|show)|vendor\s*(?:fair|market|night|event)|"
    r"street\s*fair|art\s*walk|artwalk|bazaar|marketplace"
    r")\b",
    re.IGNORECASE,
)

# Pickleball is a sport → always Fitness & sports (Item 2), regardless of how the
# source typed it ("Pickleball Open Play" is an all-day drop-in that would
# otherwise route to Things to do). Matches "pickleball" / "pickle ball".
_PICKLEBALL_RE = re.compile(r"\bpickle\s?ball\b", re.IGNORECASE)

# Recreation / animal-rides / scenic cruises & guided tours are leisure *things
# to do*, not instructional "classes" — even when a venue's recurring Schedule
# typed them as a class (the live "Pony / Lead Line Rides" horseback row landed
# in Classes and, with no provider page, linked nowhere). Matched on the title;
# wins over the class-tier routing below. Physical *sports* are NOT here — they
# stay with the fitness hints so they route to Fitness & sports.
_RECREATION_RE = re.compile(
    r"\b("
    r"horse\s*back|trail\s+rides?|pony|lead[\s-]*line|"
    r"hay\s*rides?|wagon\s+rides?|carriage\s+rides?|"
    r"(?:scenic|sunset|dinner|lake|narrated|lunch|brunch|river|boat)\s+cruises?|"
    r"(?:kayak|paddle\s*board|paddleboard|canoe|sup)\s+tours?|"
    r"(?:jeep|atv|utv|off[\s-]*road|helicopter|sightseeing|boat|scenic)\s+tours?"
    r")\b",
    re.IGNORECASE,
)

# Genuinely kid-targeted signals (Item 5 — STRICTER than is_family_event). NO
# "all ages", NO bare "family"/"family swim"/"family night", NO bare "open swim":
# those are all-ages and must not read as kids-only on the home feed.
_KID_TAG_TAGS = frozenset(
    {"youth", "kids", "kid", "children", "child", "teen", "teens", "tween",
     "junior", "toddler", "toddlers"}
)
_KID_TAG_RE = re.compile(
    r"\b("
    r"kids?|child(?:ren)?|toddlers?|teens?|tweens?|youth|junior|jr|"
    r"story\s*times?|story\s+hour|"
    r"lego|minecraft|pok[eé]mon|"
    r"tumbl(?:e|es|er|ers|ing)?|gymtots?|"
    r"pee\s*-?\s*wee|"
    r"littles|little\s+(?:ninjas?|dragons?|tigers?|kickers?|stars?|movers?|hawks?|gym)|"
    r"tiny\s+(?:tots?|tumblers?|dancers?|ninjas?|hawks?)|"
    r"pre-?k|preschool|kinder(?:garten)?|"
    r"mommy\s*(?:&|and|n|\+)?\s*me|parent\s*(?:&|and|n|\+)?\s*tot|"
    r"swim\s+lessons?"
    r")\b",
    re.IGNORECASE,
)
# All-ages / "everyone welcome" title markers that VETO the Kids tag even when
# the ingest loaders tagged the row ``youth``/``family`` (parks_rec_loader tags
# "kids"/"junior" text ``youth``; event_ingest tags "family" text ``family``).
# Those are honest *family-mode* signals — the calendar's ?family=1 narrow is
# their home — but on the home feed the Kids *tag* must mean genuinely
# kid-targeted, so "Family Night Golf", "Family Glow Bowling", and "Glow in the
# Park — All Ages" must NOT carry it. A genuine kid-only title token
# (:data:`_KID_TAG_RE`) still wins over this veto (checked first).
_ALL_AGES_RE = re.compile(
    r"\ball[\s-]*ages\b|\bfamil(?:y|ies)\b|\bopen\s+swim\b",
    re.IGNORECASE,
)


def _kid_targeted(title: str | None, tags: list[str] | None) -> bool:
    """True only for genuinely kid-targeted rows (Item 5). Stricter than
    :func:`app.events.family_filter.is_family_event`: all-ages / open-swim /
    bare-"family" rows return False so the Kids tag stops over-applying.

    A clear kid-only *title* token wins outright. Otherwise an all-ages /
    family-as-everyone title marker vetoes the tag — even when the loaders wrote
    a ``youth``/``family`` data tag — so "Family Night Golf" reads as everyone,
    not kids. With no such marker, a ``youth``-class data tag still tags the row
    (a neutrally-titled "Wrestling" the loader marked youth stays kid-targeted).
    """
    t = (title or "").strip()
    if t and _KID_TAG_RE.search(t):
        return True
    if t and _ALL_AGES_RE.search(t):
        return False
    for tag in tags or []:
        if isinstance(tag, str) and tag.strip().lower() in _KID_TAG_TAGS:
            return True
    return False


def _audience_tags(
    title: str | None, tags: list[str] | None, venue: str | None = None
) -> list[str]:
    """Kids / Seniors row tags. Kids uses the tightened :func:`_kid_targeted`
    matcher (Item 5); Seniors uses the calendar's positive matcher (venue-aware,
    so a senior-center program tags Seniors even with a generic title). Empty when
    there is no signal — never an invented tag."""
    out: list[str] = []
    if _kid_targeted(title, tags):
        out.append("Kids")
    if is_senior_event(title or "", tags, venue):
        out.append("Seniors")
    return out


def _home_group(
    title: str,
    tags: list[str] | None,
    featured: bool,
    recurring: bool,
    start_time: time | None,
    end_time: time | None,
    activity: str | None = None,
) -> str:
    """Route one occurrence to a home-feed group key (never "movies").

    Order matters: special/festival → Events; drop-in & all-day rec → Things to
    do; class-tier splits physical (Fitness & sports) vs non-physical (Classes);
    a non-class sport (e.g. a one-off BMX race) still lands in Fitness; the rest
    of the day's happenings fall to Things to do.
    """
    low = (title + " " + " ".join(tags or [])).lower()
    # Item 4: markets / art walks / swap meets are drop-in things to do even when
    # the source typed them as a recurring "class" — this rule wins over the
    # class-type routing below (and over a stray SPECIAL mis-tier).
    if _MARKET_RE.search(low):
        return "things_to_do"
    # Pickleball is a sport: ALL of it (open play, round robins, leagues, clinics)
    # belongs in Fitness & sports, not Things to do. This wins over the drop-in /
    # all-day "open play" routing below; the Adult/Youth split is decided later by
    # _fitness_audience (Adult unless the title reads youth/junior/littles).
    if _PICKLEBALL_RE.search(low):
        return "fitness"
    if _event_tier(title=title, tags=tags, featured=featured, recurring=recurring) == TIER_SPECIAL:
        return "events"
    if is_dropin_rec(title):
        return "things_to_do"
    if short_time_label(start_time, end_time) is None and _ALL_DAY_TITLE_RE.search(title or ""):
        return "things_to_do"
    # Recreation / animal-rides / scenic cruises & guided tours are leisure things
    # to do, not instructional classes — wins over the class-tier routing below
    # (e.g. "Pony / Lead Line Rides" arrives as a recurring class but is an
    # activity). Physical sports are excluded here and still route to Fitness.
    if _RECREATION_RE.search(low):
        return "things_to_do"
    if _group_for(title=title, tags=tags, featured=featured, recurring=recurring) == "classes":
        # A provider-derived activity (Yoga/Dance/Gymnastics/… — only ever a
        # PHYSICAL discipline) types a generically-named class as Fitness, the
        # same way /events-ui drains it from "Other classes".
        if _FITNESS_RE.search(low) or activity:
            return "fitness"
        if _CLASS_NONPHYSICAL_RE.search(low):
            return "classes"
        return "classes"
    if _FITNESS_RE.search(low):
        return "fitness"
    # Item 2: instructional one-off the shared classifier missed (e.g. a cooking
    # "party"). Route to Classes unless the row reads as a fair/market/sale.
    if _CLASS_FALLBACK_RE.search(low) and not _NOT_A_CLASS_RE.search(low):
        return "classes"
    return "things_to_do"


def _fitness_audience(title: str | None, tags: list[str] | None) -> str:
    """Adult vs Youth sub-section for a Fitness & sports row. BMX racing is Youth
    (Casey's call); otherwise the youth signal in the title/tags decides."""
    if "bmx" in (title or "").lower():
        return "Youth"
    return "Youth" if _kid_targeted(title, tags) else "Adult"


def _summary(counts: dict[str, int]) -> str:
    """"3 events · 12 things to do · 6 films" — zero/empty groups omitted."""
    bits: list[str] = []
    for key, _label in FEED_GROUP_DEFS:
        n = counts.get(key, 0)
        if not n:
            continue
        singular, plural = _GROUP_NOUNS[key]
        bits.append(f"{n} {singular if n == 1 else plural}")
    return " · ".join(bits)


def _movie_films(
    db: Session, *, day: date, now: datetime | None = None
) -> list[dict[str, Any]]:
    """One row per film for the "At the movies" group, per-theater showtimes in
    the expand. A film at two theaters collapses to a single row; the summary
    reads "2 theaters · next 12:40 PM" (or "Star Cinemas · next 10:00 AM")."""
    films: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for tg in showtimes_for_day(db, day=day, now=now):
        for fc in tg.films:
            first = fc.showtimes[0]
            # Case/space-insensitive de-dup so the same film spelled differently
            # at two theaters ("...of/Of Robin Hood") collapses to one row.
            fkey = normalize_film_title(fc.title)
            f = films.get(fkey)
            if f is None:
                f = {
                    "title": fc.title,  # first-seen spelling is the display title
                    "tags": _audience_tags(fc.title, None),
                    "theaters": [],
                    "is_free": False,
                    "_sort": first.sort,
                    "next_label": first.label,
                    "url": first.url,
                }
                films[fkey] = f
                order.append(fkey)
            f["theaters"].append(
                {"name": tg.name, "times": [s.label for s in fc.showtimes]}
            )
            if fc.is_free:
                f["is_free"] = True
            if first.sort < f["_sort"]:
                f["_sort"] = first.sort
                f["next_label"] = first.label
                f["url"] = first.url

    out: list[dict[str, Any]] = []
    for title in order:
        f = films[title]
        n = len(f["theaters"])
        venue = f"{n} theaters" if n > 1 else f["theaters"][0]["name"]
        free_bit = "Free · " if f["is_free"] else ""
        f["summary"] = f"{free_bit}{venue} · next {f['next_label']}"
        # The free summer kids series is kid-targeted even when the title carries
        # no kid word (e.g. "Toy Story") — tag it Kids (Item 5).
        if f["is_free"] and "Kids" not in f["tags"]:
            f["tags"] = ["Kids", *f["tags"]]
        out.append(f)
    out.sort(key=lambda f: f["_sort"])
    return out


def _event_feed_row(
    *,
    title: str,
    venue: str | None,
    url: str | None,
    start_time: time | None,
    end_time: time | None,
    recurring: bool,
    tags: list[str] | None,
    is_past: bool = False,
) -> dict[str, Any]:
    return {
        "sort": time_sort_key(start_time, end_time),
        "time_label": _row_time_label(title or "", start_time, end_time),
        "title": clean_event_title(title, location_name=venue),
        "venue": venue,
        "url": url,
        "recurring": recurring,
        "type_label": event_type_label(title, tags, venue),
        "tags": tags if tags is not None else _audience_tags(title, None),
        # Rows that started >1h ago are dropped upstream, so survivors are never
        # past; ``is_past`` stays in the row shape (default False) for the
        # template's ``frow--past`` hook but is no longer set true in the feed.
        "is_past": is_past,
    }


def today_feed(
    db: Session, *, day: date, now: datetime | None = None
) -> dict[str, Any]:
    """Build the home five-group feed for ``day``.

    Returns ``{"groups": [...], "counts": {...}, "summary": str}``. Empty groups
    are omitted entirely (honest omission — never a labeled empty shell). The
    Events group opens by default; if the day has no events, **Things to do**
    opens instead so the feed never loads fully collapsed. The Fitness & sports
    group carries an ``Adult`` / ``Youth`` ``subgroups`` split; movies count
    DISTINCT films (Item 6) and free screenings cross-post into Things to do.
    """
    events = _live_events_by_day(db, window_start=day, window_end=day).get(day, [])
    # Calendar rule (2026-06-24): items + movies stop showing one hour after they
    # start, so the home reflects what's still worth heading out for *now* — the
    # same start-based cutoff ``/events-ui`` uses. (This replaces the older
    # "show the full day, mute past rows" behaviour: started items are now dropped
    # outright, so a group whose only sessions were this morning empties out by
    # afternoon — that is the intended effect.) No-op off the current day / when
    # ``now`` isn't supplied.
    event_keys = {
        ((ev.title or "").strip().lower(), day, ev.start_time) for ev in events
    }

    buckets: dict[str, list[dict[str, Any]]] = {
        "events": [],
        "things_to_do": [],
        "fitness": [],
        "classes": [],
    }

    for ev in events:
        if _occurrence_expired(day, ev.start_time, ev.end_time, now):
            continue
        bkey = _home_group(
            ev.title or "", ev.tags, bool(ev.featured), bool(ev.is_recurring),
            ev.start_time, ev.end_time,
        )
        buckets[bkey].append(
            _event_feed_row(
                title=ev.title or "",
                venue=ev.location_name,
                url=f"/events/{ev.id}",
                start_time=ev.start_time,
                end_time=ev.end_time,
                recurring=bool(ev.is_recurring),
                tags=_audience_tags(ev.title or "", ev.tags, ev.location_name),
            )
        )

    for occ in drop_event_duplicates(
        class_occurrences_in_window(db, window_start=day, window_end=day), event_keys
    ):
        # Drop class occurrences that started >1h ago (same cutoff as events).
        if _occurrence_expired(day, occ.start_time, occ.end_time, now):
            continue
        bkey = _home_group(
            occ.title, None, False, True, occ.start_time, occ.end_time,
            activity=occ.provider_activity,
        )
        buckets[bkey].append(
            _event_feed_row(
                title=occ.title,
                venue=occ.venue,
                # occ.url is the venue's provider page, or "" when the venue has
                # no published provider (e.g. "Havasu Horseback Rides"). A
                # permalink-less program has no real detail page, so leave the
                # url empty — the feed row renders without a "Details →" link
                # rather than fabricating a self-referential ``/events-ui#program-…``
                # anchor that just points back at this same bare row (no real
                # source). The expandable row still shows When/Where.
                url=occ.url,
                start_time=occ.start_time,
                end_time=occ.end_time,
                recurring=True,
                tags=_audience_tags(occ.title, None, occ.venue),
            )
        )

    # Drop-in venue hours (trampoline, arcade, indoor playground, dojo/gym class
    # blocks) — always all-day drop-ins, so they live under "Things to do".
    for vrow in open_today_rows(day):
        # Open-venue rows carry a bare hours range ("10 AM–9 PM") — no "Open"
        # verb — so they drop into Things to do uniform with every other row.
        buckets["things_to_do"].append(
            {
                "sort": vrow["sort"],
                "time_label": vrow["time_label"],
                "title": vrow["title"],
                "venue": vrow["venue"],
                "url": vrow["url"],
                "recurring": False,
                "tags": _audience_tags(vrow["title"], None),
                # Drop-in venue "Open H–H" rows describe today's open hours, not a
                # finished session — never muted as past.
                "is_past": False,
            }
        )

    films = _movie_films(db, day=day, now=now)
    # Free community screenings cross-post into Things to do (they also stay in
    # the movies group) — a free movie night is a thing to do today.
    for f in films:
        if not f["is_free"]:
            continue
        buckets["things_to_do"].append(
            {
                "sort": f["_sort"],
                "time_label": f["next_label"],
                "title": f["title"],
                "venue": f"Free screening · {f['theaters'][0]['name']}",
                "url": f["url"],
                "recurring": False,
                "tags": list(f["tags"]),
                # ``next_label`` is the next showtime still on (showtimes that
                # started >1h ago are already filtered out upstream).
                "is_past": False,
            }
        )

    counts: dict[str, int] = {}
    groups: list[dict[str, Any]] = []
    for key, label in FEED_GROUP_DEFS:
        if key == "movies":
            continue
        rows = sorted(buckets[key], key=lambda r: r["sort"])
        counts[key] = len(rows)
        if not rows:
            continue
        group: dict[str, Any] = {"key": key, "label": label, "count": len(rows), "rows": rows}
        if key == "fitness":
            # Adult / Youth sub-sections (Item 4); empty ones omitted, row order
            # preserved. BMX racing and youth-signal rows file under Youth.
            split: dict[str, list[dict[str, Any]]] = {"Adult": [], "Youth": []}
            for r in rows:
                split[_fitness_audience(r["title"], r.get("tags"))].append(r)
            group["subgroups"] = [
                {"label": lbl, "rows": split[lbl], "count": len(split[lbl])}
                for lbl in ("Adult", "Youth")
                if split[lbl]
            ]
        groups.append(group)

    counts["movies"] = len(films)
    if films:
        groups.append(
            {"key": "movies", "label": "At the movies", "count": len(films), "films": films}
        )

    # Default-open: Events when it has items today, else Things to do, else the
    # first present group. Everything else collapsed.
    present = {g["key"] for g in groups}
    if "events" in present:
        open_key = "events"
    elif "things_to_do" in present:
        open_key = "things_to_do"
    else:
        open_key = groups[0]["key"] if groups else None
    for g in groups:
        g["open"] = g["key"] == open_key

    return {"groups": groups, "counts": counts, "summary": _summary(counts)}
