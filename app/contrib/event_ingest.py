"""Reusable event ingestion: EventRecord -> contribution queue -> Event.

The source-expansion event scrapers (allevents, legistar, lhusd, senior_center,
movies, …) all normalise to :class:`app.contrib.event_record.EventRecord`. This
module turns a batch of those records into catalog events through the *same*
path the wired sources use, so behaviour (dedup, provenance, categorisation,
trust-tiered approval) is identical across every source:

    EventRecord -> EventPayload -> reconcile_event(db, payload):
        insert     -> create_contribution -> (auto-approve if the source is in
                      the auto-approve registry AND the payload is complete AND,
                      for vision sources, the per-row guards pass; else leave
                      PENDING for human review)
        update/dup -> merge mergeable fields onto the existing event
        ambiguous  -> create contribution, leave PENDING, log

Trust tier is NOT decided here — it is the ``should_auto_approve_event`` registry
in ``approval_service`` (civic/official feeds auto-approve; aggregators land
pending). This keeps one source of truth for the go/no-go policy.

Vision sources (parks_rec_calendar / parks_rec_flyers / senior_center_flyers) are
in that registry but auto-publish only their CLEAN rows: ``_vision_auto_approve_blocked``
keeps a row the vision engine HELD (confidence below the §6 threshold or a
self-check demotion, stamped on ``raw['should_hide']``) or whose listed weekday
contradicts its body PENDING for /admin review (ambiguous + cross-source dups are
already held upstream).

No network here: callers pass already-fetched records. ``dry_run=True`` performs
no writes (mirrors the inert dry-run drivers).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date, time
from typing import Any

from sqlalchemy.orm import Session

from app.contrib.approval_service import (
    approve_contribution_as_event,
    auto_approve_event_sources,
    should_auto_approve_event,
)
from app.contrib.event_min_info import event_missing_info
from app.contrib.event_reconciler import log_ambiguous_reconcile, reconcile_event
from app.contrib.event_record import (
    EventRecord,
    canonicalize_venue,
    extract_cost_from_text,
)
from app.db import contribution_store as cs
from app.db.database import SessionLocal
from app.db.models import Contribution, Event
from app.events.activity_taxonomy import event_activity_tags
from app.events.description_clean import (
    clean_event_description,
    normalize_location_text,
    valid_event_url,
)
from app.events.event_type_tags import classify_event_type
from app.events.scrapers.base import EventPayload, normalize_event_title
from app.events.title_clean import INSTRUCTOR_NAMES
from app.schemas.contribution import ContributionCreate, EventApprovalFields

# Event columns the reconciler is allowed to merge onto an existing row (mirror
# of golakehavasu_pull._MERGEABLE_EVENT_FIELDS).
_MERGEABLE_EVENT_FIELDS = frozenset(
    {
        "source",
        "title",
        "normalized_title",
        "description",
        "location_name",
        "location_normalized",
        "event_url",
        "source_url",
        "end_time",
        "end_date",
    }
)


@dataclass
class IngestCounts:
    fetched: int = 0
    inserted_pending: int = 0
    auto_approved: int = 0
    auto_approval_failed: int = 0
    merged_duplicate: int = 0
    flagged_ambiguous: int = 0
    skipped_incomplete: int = 0
    # 2026-06-23 minimum-info bar: a record missing a real venue / source link /
    # description (the owner "core + description" rule) is not ingested.
    skipped_no_info: int = 0
    skipped_blocked: int = 0
    skipped_existing_pending: int = 0
    # Fix 4.4 — a candidate that matched an already-persisted Event on the
    # (normalized_title, start_date, venue) guard and so was NOT inserted.
    skipped_duplicate_persisted: int = 0
    # Fix 2.7 — listed weekday contradicted a schedule stated in the body; flagged
    # (logged), not dropped.
    flagged_weekday_mismatch: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "fetched": self.fetched,
            "inserted_pending": self.inserted_pending,
            "auto_approved": self.auto_approved,
            "auto_approval_failed": self.auto_approval_failed,
            "merged_duplicate": self.merged_duplicate,
            "flagged_ambiguous": self.flagged_ambiguous,
            "skipped_incomplete": self.skipped_incomplete,
            "skipped_no_info": self.skipped_no_info,
            "skipped_blocked": self.skipped_blocked,
            "skipped_existing_pending": self.skipped_existing_pending,
            "skipped_duplicate_persisted": self.skipped_duplicate_persisted,
            "flagged_weekday_mismatch": self.flagged_weekday_mismatch,
            "errors": self.errors,
        }


def _http_url_or_none(url: str | None) -> str | None:
    # Validates http(s) and rejects email-as-URL (``https://info@ijsba.com/``) and
    # known-dead placeholder hosts, so a bad click-through never reaches an event.
    return valid_event_url(url)


def _location_name(rec: EventRecord) -> str:
    # Fix 2.7 — canonicalize first (collapse "Lake Havasu City, Lake Havasu City,
    # AZ" doubling and adjacent repeats), then the existing glued-city / tail tidy.
    name = normalize_location_text(canonicalize_venue(rec.venue_name) or rec.venue_name)
    # P1: title-as-venue artifact — some feeds put the event TITLE in the venue
    # field, producing rows whose "Where" repeats the event name. Drop it (fall
    # back to the city) rather than show "Sunset Paddle @ Sunset Paddle".
    norm_name = normalize_event_title(name)
    if norm_name and norm_name == normalize_event_title(rec.title or ""):
        return "Lake Havasu City"
    # EventApprovalFields requires location_name >= 3 chars.
    return name if len(name) >= 3 else "Lake Havasu City"


# --------------------------------------------------------------------------- #
# Fix 4.3 — extract the instructor/host name from a raw class title.
# --------------------------------------------------------------------------- #
def _host_from_title(title: str | None) -> str | None:
    """Return a trailing instructor first name from a class title, or ``None``.

    Mirrors the trailing-name strip in ``app.events.title_clean.clean_event_title``
    (same shared ``INSTRUCTOR_NAMES`` set) but instead of dropping the name it
    CAPTURES it into ``Event.host`` so the structured field survives after the
    display title is cleaned. Only an exact trailing token match with at least one
    other word remaining counts (so a real title word is never mistaken for a host).
    """
    if not title:
        return None
    parts = str(title).split()
    if len(parts) >= 2:
        last = parts[-1].lower().strip(".,")
        if last in INSTRUCTOR_NAMES:
            return parts[-1].strip(".,").title()
    return None


# --------------------------------------------------------------------------- #
# Fix 2.2 — pick a human-readable cost from the record (source then prose).
# --------------------------------------------------------------------------- #
def _cost_for_record(rec: EventRecord) -> str | None:
    """Best human-readable price for the event, or ``None``.

    Prefers a structured price the source JSON-LD ``offers`` left in ``rec.raw``
    (``offers_price`` / ``is_free``); falls back to parsing the title+description
    prose ("$20", "Free", "$10-$25")."""
    raw = rec.raw or {}
    price = raw.get("offers_price")
    if isinstance(price, str) and price.strip():
        return price.strip()
    if raw.get("is_free") is True:
        return "Free"
    return extract_cost_from_text(f"{rec.title or ''}\n{rec.description or ''}")


# --------------------------------------------------------------------------- #
# Fix 2.7 — flag (never crash) events whose listed weekday contradicts a
# schedule stated in the body (e.g. listed on a Friday but body says Tue/Thu).
# --------------------------------------------------------------------------- #
_WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2, "weds": 2, "thursday": 3, "thu": 3, "thur": 3,
    "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}
_WEEKDAY_TOKEN_RE = re.compile(
    r"\b(mondays?|tuesdays?|tues|wednesdays?|weds?|thursdays?|thurs?|thur|"
    r"fridays?|saturdays?|sundays?|mon|tue|wed|thu|fri|sat|sun)\b",
    re.IGNORECASE,
)


def _body_weekdays(text: str | None) -> set[int]:
    """Set of weekday indexes (Mon=0) named in prose, e.g. 'Tue/Thu' -> {1, 3}."""
    if not text:
        return set()
    out: set[int] = set()
    for m in _WEEKDAY_TOKEN_RE.finditer(text):
        tok = m.group(1).lower().rstrip("s")
        if tok in _WEEKDAYS:
            out.add(_WEEKDAYS[tok])
    return out


def weekday_contradiction(rec: EventRecord) -> bool:
    """True when the record's start_date weekday contradicts weekdays in the body.

    Only flags when the body names one or more weekdays AND the event's own
    start-date weekday is not among them (e.g. a BMX Clinic dated a Friday whose
    body says "Tue/Thu"). Returns False when the body names no weekday (nothing to
    contradict). Pure + side-effect free; callers decide how to log/mark."""
    if rec.start_date is None:
        return False
    body_days = _body_weekdays(rec.description)
    if not body_days:
        return False
    return rec.start_date.weekday() not in body_days


def _description(rec: EventRecord) -> str:
    """Real user-facing prose for the event, or "" when the source gave none.

    We never fabricate a sentence: a metadata/placeholder body is collapsed to ""
    by ``clean_event_description`` and the event detail template renders a
    structured sparse-event card (When/Where + organizer link) instead.
    EventApprovalFields permits an empty description for exactly this reason."""
    return clean_event_description(rec.description)


# Junk-drawer / placeholder tag values upstream forms leak (Cowork saw a literal
# "Select Category" tag). Dropped on ingest so events never carry them.
_PLACEHOLDER_TAGS = frozenset(
    {"select category", "uncategorized", "category", "categories", "none", "n/a", "na", "tbd", "other"}
)

# Title/tag keyword -> canonical tags. A class/sport hit also gets the
# "classes-sports-recreation" routing tag: the Event model has no category column
# (events are tag-driven), so this tag is how the calendar/search surfaces treat a
# fitness/martial-arts/sport event as a class rather than a generic "events" row,
# per the build brief's "route class items to classes-sports-recreation" ask.
_CLASSES = "classes-sports-recreation"
_KEYWORD_TAGS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("jiu jitsu", "jiu-jitsu", "jiujitsu", "bjj", "karate", "judo", "taekwondo",
         "muay thai", "kickbox", "boxing", "martial art", "krav maga", "mma"),
        ("martial-arts", _CLASSES),
    ),
    (
        ("yoga", "pilates", "zumba", "aerobics", "crossfit", "bootcamp", "fitness",
         "workout", "spin class", "strength training", "gymnastics"),
        ("fitness", _CLASSES),
    ),
    (
        ("pickleball", "tennis", "disc golf", "volleyball", "basketball", "dodgeball",
         "softball", "league night"),
        ("sports", _CLASSES),
    ),
    (("aqua", "lap swim", "water aerobics", "swim lesson"), ("aquatics", _CLASSES)),
    (("ballroom", "ballet", "dance class", "line dancing"), ("dance", _CLASSES)),
    (("concert", "live music", "band", "karaoke", "open mic", " dj "), ("music",)),
    (("kids", "family", "youth", "children", "toddler", "story time", "story hour"), ("family",)),
    # Calendar reorg Phase 1: the canonical activity signal is the namespaced
    # ``activity:arts`` tag stamped by ``event_activity_tags``; this coarse "arts"
    # tag mirrors it for search and is inert to the bare-word tier classifier.
    (("art walk", "paint ", "paint &", "pottery", "art class", "craft", "stained glass",
      "polymer clay", "terrarium", "windchime", "wind chime"), ("arts",)),
    (("farmers market", "swap meet", "craft fair"), ("market",)),
    (("city council", "planning and zoning", "board of", "commission"), ("civic",)),
    # Fix 2.5 — automotive route so car shows / cruise-ins / "Motor Madness" land
    # under their own tag instead of MUSIC or the catch-all COMMUNITY bucket.
    (
        ("car show", "cruise-in", "cruise in", "motor madness", "motorcycle",
         "auto show", "classic car", "hot rod", "off-road", "off road", "jeep",
         "poker run", "show and shine", "show n shine"),
        ("automotive",),
    ),
    # Fix 2.5 — lake & boating route (Havasu's signature category) so on-water
    # events get a real tag instead of COMMUNITY.
    (
        ("boat parade", "boating", "poker run", "regatta", "kayak", "paddle",
         "fishing tournament", "wakeboard", "jet ski", "sandbar", "lake clean"),
        ("lake-boating",),
    ),
    # Fix 2.5 — widen keyword coverage to reduce over-reliance on COMMUNITY.
    (("food truck", "wine tasting", "beer fest", "brunch", "tasting", "happy hour"),
     ("food-drink",)),
    (("5k", "10k", "fun run", "marathon", "color run", "race"), ("sports", _CLASSES)),
    (("festival", "fair", "parade", "fireworks", "celebration"), ("festival",)),
    (("rummage", "yard sale", "garage sale", "vendor"), ("market",)),
    (("workshop", "seminar", "lecture", "class ", "training"), (_CLASSES,)),
    (("fundraiser", "charity", "benefit", "gala"), ("community",)),
)

# Fix 2.5 — automotive events that merely mention a "band"/"dj" at the show must
# NOT be routed to Music & nightlife. This guard fires only when the event is
# automotive-dominant AND lacks a STRONG live-music signal (a real concert/band
# headliner). "Motor Madness Car Show" -> automotive, never music.
_AUTOMOTIVE_RE = re.compile(
    r"\b(car show|cruise[- ]?in|motor madness|auto show|classic car|hot rod|"
    r"show\s*[&n]?\s*shine|poker run|motorcycle rally)\b",
    re.IGNORECASE,
)


def _normalize_tags(raw: list[Any]) -> list[str]:
    """Lowercase, strip, dedupe, and drop placeholder tags (fixes the
    'Events'/'events' case splits + the 'Select Category' junk tag)."""
    out: list[str] = []
    seen: set[str] = set()
    for t in raw:
        if not isinstance(t, str):
            continue
        norm = t.strip().lower()
        if not norm or norm in _PLACEHOLDER_TAGS or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def _keyword_tags(text: str) -> list[str]:
    hay = f" {text.lower()} "
    found: list[str] = []
    seen: set[str] = set()
    for needles, tags in _KEYWORD_TAGS:
        if any(n in hay for n in needles):
            for tag in tags:
                if tag not in seen:
                    seen.add(tag)
                    found.append(tag)
    return found



# Live-music / nightlife detection. The home/calendar lane classifier
# (app.home.sandstone._event_tier) routes an event to "Music & nightlife" when
# it carries the ``music`` tag, but it only inspects title + tags — never the
# body. Aggregator gigs (e.g. a band called "A-Z" at "Lighthouse Lounge") have
# no music word in the title, so without this they fall to "community". We
# derive the tag from the richer signals enrichment recovers: the description,
# the venue, and the organizer (the booking bar/lounge).
_MUSIC_VENUE_RE = re.compile(
    r"\b(lounge|saloon|tavern|pub|taproom|brewery|brewing|cantina|nightclub|"
    r"speakeasy|ale\s?house|wine bar|music hall|amphitheat(?:er|re)|beer garden)\b",
    re.IGNORECASE,
)
# Strong music signals -> always tag music (a real band/show/venue).
_MUSIC_STRONG_RE = re.compile(
    r"\b(live music|live band|band|bands|concert|karaoke|open mic|acoustic|"
    r"setlist|set list|tribute|singer[- ]songwriter|cover band|jam session)\b",
    re.IGNORECASE,
)
# Weak signals -> tag music ONLY when the event is not clearly kids/all-ages.
# (A kids "Glow in the Park - All Ages" party has a DJ and a dance but is not a
# Music & nightlife listing.)
_MUSIC_WEAK_RE = re.compile(
    r"\b(dj|deejay|dance party|duo|trio|live at|on stage|performing live|plays live)\b",
    re.IGNORECASE,
)
# Kids / all-ages context that downgrades a weak music signal.
_FAMILY_CONTEXT_RE = re.compile(
    r"\b(all ages|kid|kids|family|families|junior|toddler|youth|children|child)\b",
    re.IGNORECASE,
)
# Civic/government events are never music, even if their text trips a keyword
# (mirrors the sandstone civic guard so a "council" item can't be mistagged).
_CIVIC_GUARD_RE = re.compile(
    r"\b(city council|council|commission|board of|planning and zoning|"
    r"public hearing|city hall|town hall|government|civic)\b",
    re.IGNORECASE,
)


def _live_music_tags(rec: EventRecord) -> list[str]:
    organizer = ""
    raw = rec.raw or {}
    if isinstance(raw.get("organizer"), str):
        organizer = raw["organizer"]
    blob = " ".join(
        x for x in (rec.title, rec.description, rec.venue_name, organizer) if x
    )
    if _CIVIC_GUARD_RE.search(blob):
        return []
    # Fix 2.5 — automotive events (car show / cruise-in / "Motor Madness") are
    # not music. A live band at the show only makes it music if that's a STRONG
    # headliner signal; the weak (dj/dance) and venue-only paths are suppressed so
    # "Motor Madness Car Show" never lands in Music & nightlife.
    automotive = bool(_AUTOMOTIVE_RE.search(blob))
    # Strong signals (real band/concert/show) always count, even at a car show.
    if _MUSIC_STRONG_RE.search(blob):
        return ["music"]
    if automotive:
        return []
    # A music venue (lounge/brewery/etc.) is a strong-enough signal on its own.
    if _MUSIC_VENUE_RE.search(blob):
        return ["music"]
    # Weak signals (dj/dance/duo) only when it's not a kids/all-ages event.
    family_ctx = _FAMILY_CONTEXT_RE.search(f"{rec.title or ''} {rec.description or ''}")
    if _MUSIC_WEAK_RE.search(blob) and not family_ctx:
        return ["music"]
    return []


def _tags(rec: EventRecord) -> list[str]:
    base = _normalize_tags(list(rec.tags or []))
    # Fix 2.5 — keyword routing now also reads the body so cruise-in / car-show /
    # boating prose (not just the title) routes correctly.
    derived = _keyword_tags(f"{rec.title} {rec.description or ''} {' '.join(base)}")
    # Music is governed SOLELY by _live_music_tags, which applies the civic,
    # family/all-ages, and automotive guards. The crude keyword matcher must never
    # add `music` from body substrings (e.g. "band" inside "band-width", or a civic
    # agenda's "DJ adjustments") — that bypasses those guards and mistags civic
    # events. So strip any keyword-derived `music` here and let _live_music_tags own it.
    derived = [t for t in derived if t != "music"]
    music = _live_music_tags(rec)
    merged: list[str] = []
    seen: set[str] = set()
    for t in (*base, *derived, *music):
        if t not in seen:
            seen.add(t)
            merged.append(t)
    # Fix 2.5 — final guard: an automotive-dominant event with no STRONG live-music
    # headliner must never carry the `music` tag (drops a stray inherited/keyword
    # `music` from "Motor Madness", a car show with a DJ, etc.).
    blob = " ".join(x for x in (rec.title, rec.description, rec.venue_name) if x)
    if (
        "music" in merged
        and _AUTOMOTIVE_RE.search(blob)
        and not _MUSIC_STRONG_RE.search(blob)
    ):
        merged = [t for t in merged if t != "music"]
    # P2: stamp first-class event-TYPE tags (live_music / comedy / car_show)
    # alongside the coarse keyword/music tags, so a band's type is durable and a
    # future SQL filter can find it. Additive; the coarse ``music`` tag stays
    # (the tier classifier still routes on it). The classifier carries its own
    # civic/automotive/family guards.
    organizer = (rec.raw or {}).get("organizer") if isinstance(rec.raw, dict) else ""
    for t in sorted(
        classify_event_type(
            title=rec.title,
            tags=merged,
            venue=rec.venue_name,
            description=rec.description or "",
            organizer=organizer if isinstance(organizer, str) else "",
        )
    ):
        if t not in merged:
            merged.append(t)
    # Calendar reorg Phase 1 (Casey 2026-06-25): stamp the canonical, namespaced
    # activity/facet/audience tags ONCE at ingest, so every surface is a pure read
    # (Phase 2). ``activity:<slug>`` is the single source of truth for which bucket
    # a row belongs to; ``facet:special`` keeps a themed session (Cosmic Bowling,
    # Glow in the Park) from collapsing into a venue's hours line. These are inert
    # to the bare-word tier classifier, so they add no surface change here.
    for t in event_activity_tags(rec.title, rec.venue_name, merged):
        if t not in merged:
            merged.append(t)
    return merged or ["events"]


def _to_event_payload(rec: EventRecord, *, source: str) -> EventPayload:
    end_date = rec.end_date if (rec.end_date and rec.start_date and rec.end_date > rec.start_date) else None
    return EventPayload(
        name=rec.title.strip(),
        entity_type="event",
        source=source,
        start_date=rec.start_date,
        end_date=end_date,
        start_time=rec.start_time or time(0, 0),
        end_time=rec.end_time,
        venue_name=rec.venue_name,
        address=rec.venue_address,
        description=_description(rec),
        # Fallback must never point at the dead pre-rename domain (P0 #1):
        # askhava.com/events-ui is the canonical events surface.
        event_url=_http_url_or_none(rec.url) or "https://askhava.com/events-ui",
        source_stable_url=rec.url,
        lat=None,
        lng=None,
        tags=_tags(rec),
        category_slug="events",
        image_url=rec.image_url,
    )


def _apply_event_merge(db: Session, event_id: str, merge_fields: dict[str, Any] | None) -> bool:
    if not merge_fields:
        return False
    ev = db.get(Event, event_id)
    if ev is None:
        return False
    changed = False
    for key, value in merge_fields.items():
        if key not in _MERGEABLE_EVENT_FIELDS:
            continue
        if getattr(ev, key, None) != value:
            setattr(ev, key, value)
            changed = True
    if changed:
        db.commit()
    return changed


def _is_complete(rec: EventRecord) -> bool:
    """Minimum to place an event on the calendar + pass EventApprovalFields."""
    return bool(rec.start_date) and len((rec.title or "").strip()) >= 3


# Organizers whose listings are auto-generated national/broadcast spam, not
# genuine local events. Every one of the 2026-06-06 review-queue spam items
# (UFC / boxing / international-soccer "watch parties" attributed to a local
# Buffalo Wild Wings) came from this single organizer.
BLOCKED_ORGANIZERS = frozenset({
    "one stop entertainment",
})


def _blocked_organizer(rec: EventRecord) -> str | None:
    org = (rec.raw or {}).get("organizer")
    if isinstance(org, str) and org.strip().lower() in BLOCKED_ORGANIZERS:
        return org.strip()
    return None


# --------------------------------------------------------------------------- #
# Vision-source auto-approve gate (2026-06-24).
#
# The Parks & Rec calendar/flyer + senior-center flyer vision scrapers should
# auto-publish the CLEAN, guard-passing rows straight to the live calendar but
# keep the uncertain ones PENDING for /admin review. Registry membership (in
# ``approval_service``) makes a vision row *eligible*; these helpers add the
# per-row gate so a held / weekday-mismatched row is NOT auto-approved. Ambiguous
# reconciles and cross-source duplicates are already held earlier in the loop, so
# they never reach the auto-approve decision.
# --------------------------------------------------------------------------- #
VISION_EVENT_SOURCES = frozenset(
    {"parks_rec_calendar", "parks_rec_flyers", "senior_center_flyers"}
)


def _vision_row_held(rec: EventRecord) -> bool:
    """True when the vision engine marked this row to hold (confidence below the
    §6 threshold or a self-check demotion). The vision adapters stamp this onto
    ``EventRecord.raw['should_hide']``; non-vision records lack the key -> False."""
    raw = rec.raw if isinstance(rec.raw, dict) else {}
    return bool(raw.get("should_hide"))


def _vision_auto_approve_blocked(
    rec: EventRecord, *, source: str, weekday_mismatch: bool
) -> bool:
    """A vision-source row that tripped a hold guard must stay PENDING, not go live.

    Only vision sources are gated (every other source keeps its existing
    trust-tier behavior). The two guards added here are the engine's
    confidence/self-check hold and a listed-weekday-vs-body contradiction; the
    ambiguous and cross-source-duplicate cases are already held upstream."""
    if source not in VISION_EVENT_SOURCES:
        return False
    return _vision_row_held(rec) or weekday_mismatch


def _would_auto_approve_dry_run(
    rec: EventRecord, *, source: str, weekday_mismatch: bool
) -> bool:
    """Dry-run preview of the auto-approve decision (no Contribution row exists).

    Mirrors ``should_auto_approve_event``'s registry + completeness gate against
    the EventRecord and applies the same vision guard, so a dry run honestly
    reports ``auto_approved`` vs ``inserted_pending`` instead of marking every row
    pending. ``event_time_start`` is always set by ingest (start_time or 00:00),
    so it is not re-checked here."""
    if source not in auto_approve_event_sources():
        return False
    if not (rec.title or "").strip() or rec.start_date is None:
        return False
    return not _vision_auto_approve_blocked(
        rec, source=source, weekday_mismatch=weekday_mismatch
    )


def vision_record_should_hold(rec: EventRecord, *, source: str) -> bool:
    """The #514 auto-approve gate as a single predicate, for the one-time backfill.

    True when a vision row must stay PENDING: the engine held it
    (``raw['should_hide']`` — confidence below threshold / self-check demotion) OR
    its listed weekday contradicts its body. This is exactly
    ``_vision_auto_approve_blocked`` with the weekday signal computed here, so the
    backfill reuses the production gate rather than reimplementing it. (The
    ambiguous / cross-source-duplicate cases are the caller's reconcile step,
    mirroring ingest.)"""
    return _vision_auto_approve_blocked(
        rec, source=source, weekday_mismatch=weekday_contradiction(rec)
    )


# Original venue was not persisted on the contribution; fall back to each source's
# default — the same value the adapter uses when a row carries no explicit
# location (the common case). When the model DID read a specific location it is
# preserved inside the stored description, so no user-facing info is lost.
# (Mirrors lhc_parks_rec_calendar.DEFAULT_VENUE / senior_center.VENUE_NAME.)
_VISION_SOURCE_DEFAULT_VENUE: dict[str, str] = {
    "parks_rec_calendar": "Lake Havasu City Parks & Recreation",
    "parks_rec_flyers": "Lake Havasu City Parks & Recreation",
    "senior_center_flyers": "Lake Havasu Senior Center",
}


def _record_from_pending_contribution(c: Contribution) -> EventRecord:
    """Reconstruct the canonical EventRecord from a stored vision contribution.

    Fidelity: title / dates / times / description / url / source round-trip
    exactly. Three fields were never persisted on the contribution and so cannot
    be recovered — venue (-> source default; the specific location, when read,
    survives in the description), ``should_hide`` (-> the engine-hold guard is
    effectively off for the backfill; tonight's batch had no ingest-level
    confidence holds), and image_url (-> none). Tags are re-derived from the
    title+description by ``_tags`` (the adapter's tag list was not stored)."""
    venue = _VISION_SOURCE_DEFAULT_VENUE.get(c.source, "Lake Havasu City")
    return EventRecord(
        source=c.source,
        title=c.submission_name,
        start_date=c.event_date,
        start_time=c.event_time_start,
        end_date=c.event_end_date,
        end_time=c.event_time_end,
        venue_name=venue,
        venue_address=None,
        url=c.source_url or c.submission_url or "",
        description=c.submission_notes or "",
        tags=[],
        image_url=None,
        raw={},
    )


@dataclass
class VisionBackfillResult:
    """Outcome of evaluating one already-pending vision contribution."""

    action: str  # "approve" | "hold"
    reason: str
    contribution_id: int | None = None
    title: str | None = None
    event_id: str | None = None


def backfill_pending_vision_contribution(
    db: Session,
    c: Contribution,
    *,
    dry_run: bool,
    today: date | None = None,
) -> VisionBackfillResult:
    """Apply the #514 auto-approve gate to one ALREADY-PENDING vision contribution.

    Makes the same decision ingest would for a fresh row, but against the stored
    contribution: reconstruct the record, then HOLD if it now reconciles as a
    duplicate / ambiguous against live events, if the vision gate trips
    (weekday-mismatch — the confidence hold is unrecoverable post-hoc, see
    :func:`_record_from_pending_contribution`), or if it is not registry-eligible;
    otherwise APPROVE through :func:`approve_event_contribution` so the row is
    identical to one auto-published on ingest.

    Idempotent: a non-pending / non-vision contribution is a no-op hold. ``dry_run``
    performs reads only (reconcile is read-only) and returns the would-be action."""

    def _hold(reason: str) -> VisionBackfillResult:
        return VisionBackfillResult(
            action="hold", reason=reason, contribution_id=c.id, title=c.submission_name
        )

    if c.status != "pending":
        return _hold("not pending (idempotent skip)")
    if c.entity_type != "event" or c.source not in VISION_EVENT_SOURCES:
        return _hold("not a vision event")

    rec = _record_from_pending_contribution(c)
    payload = _to_event_payload(rec, source=c.source)
    result = reconcile_event(db, payload, today=today or date.today())
    if result.action != "insert":
        # ambiguous / duplicate / update -> ingest holds (or merges) these; the
        # backfill leaves them pending so it never publishes a possible double-book.
        return _hold(f"reconcile:{result.action}")

    if vision_record_should_hold(rec, source=c.source):
        return _hold("weekday_mismatch" if weekday_contradiction(rec) else "engine_hold")

    if not should_auto_approve_event(c):
        return _hold("not registry-eligible")

    if dry_run:
        return VisionBackfillResult(
            action="approve",
            reason="would_auto_approve",
            contribution_id=c.id,
            title=c.submission_name,
        )

    ev = approve_event_contribution(db, c.id, rec, end_date=payload.end_date)
    return VisionBackfillResult(
        action="approve",
        reason="approved",
        contribution_id=c.id,
        title=c.submission_name,
        event_id=ev.id,
    )


def _existing_open_contribution(db: Session, *, source: str, title: str, start_date: date | None) -> bool:
    """True when a pending/approved contribution for the same source+title+date
    already exists — re-running a scrape must not re-insert review-queue rows
    (the 2026-06-06 queue held 41 such duplicates from consecutive runs)."""
    if start_date is None:
        return False
    import html as html_mod
    want = html_mod.unescape(title or "").strip().lower()
    rows = (
        db.query(cs.Contribution)
        .filter(
            cs.Contribution.source == source,
            cs.Contribution.entity_type == "event",
            cs.Contribution.event_date == start_date,
            cs.Contribution.status.in_(("pending", "approved")),
        )
        .all()
    )
    return any(html_mod.unescape(r.submission_name or "").strip().lower() == want for r in rows)


def _persisted_duplicate_event(db: Session, rec: EventRecord) -> Event | None:
    """Fix 4.4 — same-day uniqueness guard on (normalized_title, start_date, venue).

    The reconciler dedupes within a batch and on source_url / fuzzy match, but a
    feed glitch that re-emits the SAME event with a fresh source_url and a slightly
    different time could still slip a true duplicate past it. This hard guard scans
    persisted (cross-batch) rows for an EXACT normalized (title, venue) match on the
    same calendar date and returns it so the caller skips the insert. Returns None
    when no such row exists.

    Venue match is lenient: it matches when the normalized venues are equal OR when
    either side's venue is the generic city default (a thin record whose venue we
    never recovered must not create a second row for an event we already have)."""
    if rec.start_date is None:
        return None
    want_title = normalize_event_title(rec.title or "")
    if not want_title:
        return None
    want_venue = normalize_event_title(
        canonicalize_venue(rec.venue_name) or rec.venue_name or ""
    )
    generic = {"", "lake havasu city", "lake havasu"}
    from sqlalchemy import select as _select

    for ev in db.scalars(_select(Event).where(Event.date == rec.start_date)).all():
        if normalize_event_title(ev.normalized_title or ev.title or "") != want_title:
            continue
        cand_venue = normalize_event_title(ev.location_name or "")
        if (
            cand_venue == want_venue
            or cand_venue in generic
            or want_venue in generic
        ):
            return ev
    return None


def _apply_structured_fields(db: Session, ev: Event, rec: EventRecord) -> None:
    """Populate the new structured Event fields (cost / host / image_url) at ingest.

    Only fills a field that is currently empty so an operator-set value is never
    clobbered. Commits when anything changed. Image rendering / cost rendering are
    other lanes' jobs; this only stores the values (field contract 2.2 / 3.2 / 4.3).
    """
    changed = False
    if not ev.cost:
        cost = _cost_for_record(rec)
        if cost:
            ev.cost = cost
            changed = True
    if not getattr(ev, "host", None):
        host = _host_from_title(rec.title)
        if host:
            ev.host = host
            changed = True
    if not ev.image_url and rec.image_url:
        ev.image_url = rec.image_url
        changed = True
    if changed:
        db.add(ev)
        db.commit()


def approve_event_contribution(
    db: Session,
    contribution_id: int,
    rec: EventRecord,
    *,
    end_date: date | None,
) -> Event:
    """Approve a pending event contribution via the canonical auto-approve path.

    Extracted so the ingest auto-approve flow and the one-time pending-vision
    backfill (``scripts/backfill_vision_auto_approve.py``) construct the
    EventApprovalFields, run ``approve_contribution_as_event``, and store the
    structured fields (cost/host/image_url) through the SAME code — a backfilled
    row is then byte-for-byte the row ingest would have auto-published."""
    approve_fields = EventApprovalFields(
        title=rec.title.strip(),
        description=_description(rec),
        date=rec.start_date,
        end_date=end_date,
        start_time=rec.start_time or time(0, 0),
        end_time=rec.end_time,
        location_name=_location_name(rec),
        event_url=_http_url_or_none(rec.url) or "https://askhava.com/events-ui",
        source_url=rec.url,
    )
    ev = approve_contribution_as_event(db, contribution_id, approve_fields, _tags(rec))
    # Fix 2.2 / 3.2 / 4.3 — store the new structured fields the approval schema
    # doesn't carry (cost / host / image_url).
    _apply_structured_fields(db, ev, rec)
    return ev


def ingest_event_records(
    records: list[EventRecord],
    *,
    source: str,
    dry_run: bool,
    today: date | None = None,
    verbose: bool = True,
) -> IngestCounts:
    """Ingest a batch of EventRecords. Returns counts; never raises per-record."""
    today = today or date.today()
    counts = IngestCounts(fetched=len(records))

    for rec in records:
        if not _is_complete(rec):
            counts.skipped_incomplete += 1
            continue
        # Minimum-info bar (2026-06-23): never ingest a record with no real
        # information — checked on the RESOLVED fields (the same venue/link/
        # description the event would store), so the bar matches what renders.
        info_missing = event_missing_info(
            title=rec.title,
            start_date=rec.start_date,
            location_name=_location_name(rec),
            source_url=_http_url_or_none(rec.url),
            description=_description(rec),
        )
        if info_missing:
            counts.skipped_no_info += 1
            if verbose:
                print(f"info: skipped no-info event {rec.title!r}: missing {info_missing}")
            continue
        blocked = _blocked_organizer(rec)
        if blocked is not None:
            counts.skipped_blocked += 1
            if verbose:
                print(f"info: skipped blocked organizer {blocked!r}: {rec.title!r}")
            continue
        # Fix 2.7 — flag (never drop) a record whose listed weekday contradicts a
        # schedule stated in its body (e.g. BMX Clinic dated Fri, body says Tue/Thu).
        # The flag also blocks auto-approve for vision sources (held pending).
        weekday_mismatch = weekday_contradiction(rec)
        if weekday_mismatch:
            counts.flagged_weekday_mismatch += 1
            if verbose:
                print(
                    f"warning: weekday mismatch — {rec.title!r} dated "
                    f"{rec.start_date} ({rec.start_date.strftime('%A') if rec.start_date else '?'}) "
                    f"contradicts weekdays in body",
                    file=sys.stderr,
                )
        try:
            payload = _to_event_payload(rec, source=source)
            with SessionLocal() as db:
                result = reconcile_event(db, payload, today=today)

                if result.action in ("update", "duplicate"):
                    if not dry_run and result.existing_id:
                        _apply_event_merge(db, result.existing_id, result.merge_fields)
                    counts.merged_duplicate += 1
                    continue

                # Fix 4.4 — hard same-day uniqueness guard against persisted rows
                # (covers a feed glitch the fuzzy reconciler might miss).
                persisted = _persisted_duplicate_event(db, rec)
                if persisted is not None:
                    counts.skipped_duplicate_persisted += 1
                    continue

                if _existing_open_contribution(
                    db, source=source, title=rec.title, start_date=rec.start_date
                ):
                    counts.skipped_existing_pending += 1
                    continue

                contribution = ContributionCreate(
                    entity_type="event",
                    submission_name=rec.title.strip()[:200],
                    submission_url=_http_url_or_none(rec.url),
                    source_url=rec.url,
                    submission_notes=_description(rec),
                    event_date=rec.start_date,
                    event_end_date=payload.end_date,
                    event_time_start=rec.start_time or time(0, 0),
                    event_time_end=rec.end_time,
                    source=source,  # type: ignore[arg-type]
                )

                if dry_run:
                    # Honest preview: report the decision --apply would make, so a
                    # clean vision/civic batch shows under auto_approved (not all
                    # pending). Ambiguous rows are always held for review.
                    if result.action == "ambiguous":
                        log_ambiguous_reconcile(result, context=rec.url or rec.title)
                        counts.flagged_ambiguous += 1
                        counts.inserted_pending += 1
                    elif _would_auto_approve_dry_run(
                        rec, source=source, weekday_mismatch=weekday_mismatch
                    ):
                        counts.auto_approved += 1
                    else:
                        counts.inserted_pending += 1
                    continue

                created = cs.create_contribution(db, contribution)

                if result.action == "ambiguous":
                    log_ambiguous_reconcile(result, context=rec.url or rec.title)
                    counts.flagged_ambiguous += 1
                    counts.inserted_pending += 1
                    continue

                if should_auto_approve_event(created) and not _vision_auto_approve_blocked(
                    rec, source=source, weekday_mismatch=weekday_mismatch
                ):
                    try:
                        ev = approve_event_contribution(
                            db, created.id, rec, end_date=payload.end_date
                        )
                        counts.auto_approved += 1
                        if verbose:
                            print(f"info: auto-approved {source} contribution "
                                  f"{created.id} -> event {ev.id}")
                    except Exception as e:  # keep going; land it as pending instead
                        counts.auto_approval_failed += 1
                        counts.inserted_pending += 1
                        print(f"warning: auto-approval failed for {source} "
                              f"contribution {created.id}: {e}", file=sys.stderr)
                else:
                    counts.inserted_pending += 1
        except Exception as e:
            counts.errors += 1
            print(f"error: {source} record {rec.title!r}: {e}", file=sys.stderr)

    return counts


def print_ingest_report(source: str, counts: IngestCounts, *, dry_run: bool) -> None:
    print(f"{source} ingest complete (EventRecord -> reconcile -> contribution/approve)")
    for k, v in counts.as_dict().items():
        print(f"  {k:<22} {v}")
    if dry_run:
        print("  (dry run -- no database writes)")
