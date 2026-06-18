"""Reusable event ingestion: EventRecord -> contribution queue -> Event.

The source-expansion event scrapers (allevents, legistar, lhusd, senior_center,
movies, …) all normalise to :class:`app.contrib.event_record.EventRecord`. This
module turns a batch of those records into catalog events through the *same*
path the wired sources use, so behaviour (dedup, provenance, categorisation,
trust-tiered approval) is identical across every source:

    EventRecord -> EventPayload -> reconcile_event(db, payload):
        insert     -> create_contribution -> (auto-approve if the source is in
                      the auto-approve registry AND the payload is complete,
                      else leave PENDING for human review)
        update/dup -> merge mergeable fields onto the existing event
        ambiguous  -> create contribution, leave PENDING, log

Trust tier is NOT decided here — it is the ``should_auto_approve_event`` registry
in ``approval_service`` (civic/official feeds auto-approve; aggregators land
pending). This keeps one source of truth for the go/no-go policy.

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
    should_auto_approve_event,
)
from app.contrib.event_reconciler import log_ambiguous_reconcile, reconcile_event
from app.contrib.event_record import EventRecord
from app.db import contribution_store as cs
from app.db.database import SessionLocal
from app.db.models import Event
from app.events.description_clean import (
    clean_event_description,
    normalize_location_text,
    valid_event_url,
)
from app.events.scrapers.base import EventPayload
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
    skipped_blocked: int = 0
    skipped_existing_pending: int = 0
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
            "skipped_blocked": self.skipped_blocked,
            "skipped_existing_pending": self.skipped_existing_pending,
            "errors": self.errors,
        }


def _http_url_or_none(url: str | None) -> str | None:
    # Validates http(s) and rejects email-as-URL (``https://info@ijsba.com/``) and
    # known-dead placeholder hosts, so a bad click-through never reaches an event.
    return valid_event_url(url)


def _location_name(rec: EventRecord) -> str:
    name = normalize_location_text(rec.venue_name)
    # EventApprovalFields requires location_name >= 3 chars.
    return name if len(name) >= 3 else "Lake Havasu City"


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
    (("art walk", "paint ", "pottery", "art class", "craft"), ("arts",)),
    (("farmers market", "swap meet", "craft fair"), ("market",)),
    (("city council", "planning and zoning", "board of", "commission"), ("civic",)),
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
_MUSIC_TEXT_RE = re.compile(
    r"\b(live music|live band|band|bands|concert|dj|deejay|karaoke|open mic|"
    r"acoustic|setlist|set list|tribute|singer[- ]songwriter|performing live|"
    r"plays live|live at|on stage|jam session|dance party|cover band|duo|trio)\b",
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
    if _MUSIC_TEXT_RE.search(blob) or _MUSIC_VENUE_RE.search(blob):
        return ["music"]
    return []


def _tags(rec: EventRecord) -> list[str]:
    base = _normalize_tags(list(rec.tags or []))
    derived = _keyword_tags(f"{rec.title} {' '.join(base)}")
    music = _live_music_tags(rec)
    merged: list[str] = []
    seen: set[str] = set()
    for t in (*base, *derived, *music):
        if t not in seen:
            seen.add(t)
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
        blocked = _blocked_organizer(rec)
        if blocked is not None:
            counts.skipped_blocked += 1
            if verbose:
                print(f"info: skipped blocked organizer {blocked!r}: {rec.title!r}")
            continue
        try:
            payload = _to_event_payload(rec, source=source)
            with SessionLocal() as db:
                result = reconcile_event(db, payload, today=today)

                if result.action in ("update", "duplicate"):
                    if not dry_run and result.existing_id:
                        _apply_event_merge(db, result.existing_id, result.merge_fields)
                    counts.merged_duplicate += 1
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
                    counts.inserted_pending += 1
                    if result.action == "ambiguous":
                        log_ambiguous_reconcile(result, context=rec.url or rec.title)
                        counts.flagged_ambiguous += 1
                    continue

                created = cs.create_contribution(db, contribution)

                if result.action == "ambiguous":
                    log_ambiguous_reconcile(result, context=rec.url or rec.title)
                    counts.flagged_ambiguous += 1
                    counts.inserted_pending += 1
                    continue

                if should_auto_approve_event(created):
                    try:
                        approve_fields = EventApprovalFields(
                            title=rec.title.strip(),
                            description=_description(rec),
                            date=rec.start_date,
                            end_date=payload.end_date,
                            start_time=rec.start_time or time(0, 0),
                            end_time=rec.end_time,
                            location_name=_location_name(rec),
                            event_url=_http_url_or_none(rec.url)
                            or "https://askhava.com/events-ui",
                            source_url=rec.url,
                        )
                        ev = approve_contribution_as_event(
                            db, created.id, approve_fields, _tags(rec)
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
