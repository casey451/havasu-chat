"""
Snapshot → catalog loader for the parks-and-rec scrapers.

Reads the latest snapshot produced by ``app.contrib.scrape_runner`` for
each source and routes records through the existing contribution
queue + auto-approval flow:

  WebTrac single-day section          → Contribution(entity_type="event")    → Event
  WebTrac multi-day / recurring       → Contribution(entity_type="program")  → Program
  Aquatic Center class slot           → Contribution(entity_type="event")    → Event

Only sections that are publicly bookable land in the catalog
(``available_for_signup=True`` for WebTrac, ``is_public=True`` for the
aquatic schedule). The full snapshot — including unavailable / full
sections and pool-closed / private rows — remains on disk under
``data/scrapes/`` so the chat layer can read those for direct-ask
carve-outs without polluting the catalog.

Dedup
-----
WebTrac records carry a stable per-section ID (``FMID``) embedded in
``info_url``; we use that as the contribution ``source_url`` and skip
re-imports.

Aquatic slots have no native unique ID. We synthesize a deterministic
URL per occurrence:

    https://www.lhcaz.gov/parks-recreation/open-swim-schedule#YYYY-MM-DD|<title-slug>|HH-MM

The same dedup helper used by the existing ``river_scene_pull`` then
catches re-imports.

This module intentionally has no scraping logic of its own — it depends
only on the snapshot files. That keeps it stable across schema churn
in the scrapers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contrib import scrape_runner
from app.contrib.approval_service import (
    approve_contribution_as_event,
    approve_contribution_as_program,
)
from app.db import contribution_store as cs
from app.db.database import SessionLocal
from app.db.models import Contribution, Event
from app.schemas.contribution import (
    ContributionCreate,
    EventApprovalFields,
    ProgramApprovalFields,
)
from app.utils.slug import slugify as _slug

WEBTRAC_SOURCE = "webtrac"
AQUATIC_SOURCE = "lhcaz_aquatic"

DEFAULT_PROVIDER_WEBTRAC = "Lake Havasu City Parks & Recreation"
DEFAULT_PROVIDER_AQUATIC = "Lake Havasu City Aquatic Center"
AQUATIC_SCHEDULE_URL = "https://www.lhcaz.gov/parks-recreation/open-swim-schedule"

# Identifier for aquatic-source Event rows. The aquatic loader synthesizes
# `{AQUATIC_SCHEDULE_URL}#YYYY-MM-DD|<slug>|HH-MM` per occurrence; live
# Event rows do NOT carry source="lhcaz_aquatic" because
# approve_contribution_as_event drops the contribution's source unless
# it's "river_scene_import". The source_url substring is the canonical
# identifier — same predicate parks_rec_reset_and_reload.py uses.
AQUATIC_SOURCE_URL_LIKE = "%lhcaz.gov/parks-recreation/open-swim-schedule%"

# Grace window (days) before today that aquatic events are kept around.
# Covers timezone slop, late-day chat queries, and recovery if a prune
# runs early or against the wrong DB. Chat already date-filters past
# events, so this only affects the row-count drift the pruner exists
# to fix.
AQUATIC_PRUNE_GRACE_DAYS = 7

# Day-letter codes from WebTrac → ProgramApprovalFields.schedule_days entries.
DAY_CODE_MAP: dict[str, str] = {
    "M": "Monday",
    "Tu": "Tuesday",
    "W": "Wednesday",
    "Th": "Thursday",
    "F": "Friday",
    "Sa": "Saturday",
    "Su": "Sunday",
}

CONTENT_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("aquatics", ("kayak", "paddle", "swim", "aqua", "water")),
    ("arts", ("art", "craft", "paint", "glass", "windchime", "pottery", "draw")),
    ("food", ("cook", "baking", "cuisine", "kitchen")),
    ("sports", (
        "dodgeball", "basketball", "soccer", "volleyball", "softball", "baseball",
        "pickleball", "tennis", "football", "lacrosse", "hockey", "league", "tournament",
    )),
    ("fitness", ("yoga", "exercise", "fit ", "fit-", "aerobic", "wellness", "tai chi", "mobility", "strong")),
]

AUDIENCE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("youth", (
        "youth", "kids", "kid ", "kid-", "junior", "teen", "child",
        "summer camp", "after school", "asp ", "iwannago",
    )),
    ("adult", ("adult",)),
]


# ---------------------------------------------------------------------------
# Stats / result containers
# ---------------------------------------------------------------------------

@dataclass
class LoaderStats:
    source: str
    considered: int = 0
    skipped_not_public: int = 0
    skipped_duplicate: int = 0
    skipped_invalid: int = 0
    imported_event: int = 0
    imported_program: int = 0
    auto_approval_failed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def imported(self) -> int:
        return self.imported_event + self.imported_program


# ---------------------------------------------------------------------------
# Common helpers
# ---------------------------------------------------------------------------

def _content_category(text: str) -> str:
    """Return a single content category (arts, sports, etc.). Used as the
    canonical ``Program.activity_category`` value."""
    low = (text or "").lower()
    for category, keywords in CONTENT_CATEGORY_KEYWORDS:
        if any(k in low for k in keywords):
            return category
    return "recreation"


def _audience_tags(text: str) -> list[str]:
    """Return audience tags (e.g. ``adult``, ``youth``) found in ``text``.

    Multiple tags are possible (a "Youth Adult Hybrid Class" would tag
    both — degenerate but parsed). Empty list when no audience keyword
    matches; the chat layer can treat that as "general/all ages".
    """
    low = (text or "").lower()
    out: list[str] = []
    for tag, keywords in AUDIENCE_KEYWORDS:
        if any(k in low for k in keywords):
            out.append(tag)
    return out


def _all_tags(text: str) -> list[str]:
    """Combined content-category + audience tags for the Event/Program
    ``tags`` field. The first entry is always the content category so
    callers using ``tags[0]`` as a primary classification still work."""
    return [_content_category(text), *_audience_tags(text)]


def _has_existing_source_url(db: Session, normalized_url: str | None) -> bool:
    """Return True if any contribution OR event already has this source_url."""
    if not normalized_url:
        return False
    if db.scalar(select(Contribution.id).where(Contribution.source_url == normalized_url).limit(1)) is not None:
        return True
    if db.scalar(select(Event.id).where(Event.source_url == normalized_url).limit(1)) is not None:
        return True
    return False


def _parse_date(s: Any) -> date | None:
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    if not isinstance(s, str):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _parse_time(s: Any) -> time | None:
    if isinstance(s, time):
        return s
    if not isinstance(s, str):
        return None
    try:
        return time.fromisoformat(s)
    except ValueError:
        return None


def _fmt_hhmm(t: time | None) -> str | None:
    return f"{t.hour:02d}:{t.minute:02d}" if t else None


# ---------------------------------------------------------------------------
# WebTrac
# ---------------------------------------------------------------------------

def _webtrac_is_recurring(record: dict[str, Any]) -> bool:
    sd = _parse_date(record.get("start_date"))
    ed = _parse_date(record.get("end_date"))
    days = record.get("days") or []
    if sd and ed and sd != ed:
        return True
    if isinstance(days, list) and len(days) > 1:
        return True
    return False


def _webtrac_event_description(record: dict[str, Any]) -> str:
    title = record.get("section_name") or record.get("program_name") or "Activity"
    sd = record.get("start_date") or "TBD"
    days = record.get("days") or []
    days_str = ", ".join(days) if days else "varies"
    cost_r = record.get("cost_resident")
    cost_n = record.get("cost_nonresident")
    if cost_r == 0 and cost_n == 0:
        cost = "Free"
    elif cost_r is not None and cost_n is not None:
        cost = f"${cost_r:.0f} resident / ${cost_n:.0f} non-resident"
    else:
        cost = "see registration page"
    age_min = record.get("age_min")
    age_max = record.get("age_max")
    ages = f"Ages {age_min:.0f}+" if age_min is not None else "All ages"
    if age_max is not None and age_max < 99:
        ages = f"Ages {age_min:.0f}-{age_max:.0f}"
    location = record.get("location") or "Lake Havasu"
    return (
        f"{title}. {sd} ({days_str}) at {location}. "
        f"{ages}. {cost}. "
        f"Register through Lake Havasu City Parks & Recreation."
    )


def _webtrac_event_payload(record: dict[str, Any]) -> tuple[ContributionCreate, EventApprovalFields, list[str]] | None:
    sd = _parse_date(record.get("start_date"))
    st = _parse_time(record.get("start_time"))
    if sd is None or st is None:
        return None
    title = (record.get("section_name") or record.get("program_name") or "").strip()
    if not title:
        return None
    info_url = (record.get("info_url") or "").strip()
    if not info_url:
        return None
    normalized = cs.normalize_submission_url(info_url)
    notes = _webtrac_event_description(record)
    payload = ContributionCreate(
        entity_type="event",
        submission_name=title,
        submission_url=info_url,
        source_url=normalized,
        submission_category_hint="parks_rec_webtrac",
        submission_notes=notes,
        event_date=sd,
        event_end_date=_parse_date(record.get("end_date")),
        event_time_start=st,
        event_time_end=_parse_time(record.get("end_time")),
        source="operator_backfill",
    )
    approve = EventApprovalFields(
        title=title,
        description=notes,
        date=sd,
        end_date=_parse_date(record.get("end_date")),
        start_time=st,
        end_time=_parse_time(record.get("end_time")),
        location_name=record.get("location") or "Lake Havasu",
        event_url=info_url,
        source_url=normalized,
    )
    tags = _all_tags(f"{record.get('program_name','')} {title}")
    return payload, approve, tags


def _webtrac_program_payload(record: dict[str, Any]) -> tuple[ContributionCreate, ProgramApprovalFields, str] | None:
    title = (record.get("program_name") or record.get("section_name") or "").strip()
    if not title:
        return None
    st = _parse_time(record.get("start_time"))
    et = _parse_time(record.get("end_time"))
    if st is None or et is None:
        return None
    info_url = (record.get("info_url") or "").strip()
    if not info_url:
        return None
    normalized = cs.normalize_submission_url(info_url)
    days = [DAY_CODE_MAP.get(d, d) for d in (record.get("days") or [])]
    notes = _webtrac_event_description(record)

    age_min = record.get("age_min")
    age_max = record.get("age_max")
    cost_r = record.get("cost_resident")
    cost_n = record.get("cost_nonresident")
    if cost_r == 0 and cost_n == 0:
        cost_str = "Free"
    elif cost_r is not None and cost_n is not None:
        cost_str = f"${cost_r:.2f} resident / ${cost_n:.2f} non-resident"
    else:
        cost_str = None

    payload = ContributionCreate(
        entity_type="program",
        submission_name=title,
        submission_url=info_url,
        source_url=normalized,
        submission_category_hint="parks_rec_webtrac",
        submission_notes=notes,
        source="operator_backfill",
    )
    approve = ProgramApprovalFields(
        title=title,
        description=notes,
        age_min=int(age_min) if age_min is not None else None,
        age_max=int(age_max) if (age_max is not None and age_max < 99) else None,
        schedule_days=days,
        schedule_start_time=_fmt_hhmm(st) or "00:00",
        schedule_end_time=_fmt_hhmm(et) or "00:00",
        location_name=record.get("location") or "Lake Havasu",
        location_address=None,
        cost=cost_str,
        provider_name=DEFAULT_PROVIDER_WEBTRAC,
        contact_phone=None,
        contact_email=None,
        contact_url=info_url,
        tags=_all_tags(f"{title} {record.get('section_name','')}"),
    )
    return payload, approve, _content_category(f"{title} {record.get('section_name','')}")


def load_webtrac_records(
    records: Iterable[dict[str, Any]],
    *,
    db: Session,
    dry_run: bool = False,
) -> LoaderStats:
    stats = LoaderStats(source=WEBTRAC_SOURCE)
    for rec in records:
        stats.considered += 1
        if not rec.get("available_for_signup", False):
            stats.skipped_not_public += 1
            continue
        normalized = cs.normalize_submission_url((rec.get("info_url") or "").strip() or None)
        if _has_existing_source_url(db, normalized):
            stats.skipped_duplicate += 1
            continue

        try:
            if _webtrac_is_recurring(rec):
                built = _webtrac_program_payload(rec)
                if built is None:
                    stats.skipped_invalid += 1
                    continue
                payload, approve, category = built
                if dry_run:
                    stats.imported_program += 1
                    continue
                created = cs.create_contribution(db, payload)
                try:
                    approve_contribution_as_program(db, created.id, approve, category)
                    stats.imported_program += 1
                except Exception as e:  # noqa: BLE001
                    stats.auto_approval_failed += 1
                    stats.errors.append(f"approve program {created.id}: {e}")
            else:
                built = _webtrac_event_payload(rec)
                if built is None:
                    stats.skipped_invalid += 1
                    continue
                payload, approve, tags = built
                if dry_run:
                    stats.imported_event += 1
                    continue
                created = cs.create_contribution(db, payload)
                try:
                    approve_contribution_as_event(db, created.id, approve, tags)
                    stats.imported_event += 1
                except Exception as e:  # noqa: BLE001
                    stats.auto_approval_failed += 1
                    stats.errors.append(f"approve event {created.id}: {e}")
        except Exception as e:  # noqa: BLE001
            stats.skipped_invalid += 1
            stats.errors.append(f"record {rec.get('fmid')}: {e}")
    return stats


# ---------------------------------------------------------------------------
# Aquatic Center
# ---------------------------------------------------------------------------

def _aquatic_synthetic_url(record: dict[str, Any]) -> str | None:
    sd = record.get("slot_date")
    title = record.get("title") or ""
    st = record.get("start_time") or "00-00"
    if not sd or not title:
        return None
    return f"{AQUATIC_SCHEDULE_URL}#{sd}|{_slug(title)}|{(st or '').replace(':', '-')}"


def _aquatic_event_payload(
    record: dict[str, Any],
) -> tuple[ContributionCreate, EventApprovalFields, list[str]] | None:
    sd = _parse_date(record.get("slot_date"))
    if sd is None:
        return None
    if record.get("all_day"):
        # All-day rows on this page are pool-closed entries; we don't import those.
        return None
    st = _parse_time(record.get("start_time"))
    if st is None:
        return None
    title = (record.get("title") or "").strip()
    if not title:
        return None
    synth = _aquatic_synthetic_url(record)
    if synth is None:
        return None
    notes = (
        f"{title} on {sd.isoformat()} at {st.strftime('%I:%M %p').lstrip('0')} "
        f"at the Lake Havasu City Aquatic Center. "
        f"See full schedule and current pricing at {AQUATIC_SCHEDULE_URL}."
    )
    payload = ContributionCreate(
        entity_type="event",
        submission_name=title,
        submission_url=AQUATIC_SCHEDULE_URL,
        source_url=synth,
        submission_category_hint="parks_rec_aquatic",
        submission_notes=notes,
        event_date=sd,
        event_end_date=sd,
        event_time_start=st,
        event_time_end=_parse_time(record.get("end_time")),
        source="operator_backfill",
    )
    approve = EventApprovalFields(
        title=title,
        description=notes,
        date=sd,
        end_date=sd,
        start_time=st,
        end_time=_parse_time(record.get("end_time")),
        location_name=DEFAULT_PROVIDER_AQUATIC,
        event_url=AQUATIC_SCHEDULE_URL,
        source_url=synth,
    )
    tags = _all_tags(f"{title} aquatic")
    return payload, approve, tags


def load_aquatic_records(
    records: Iterable[dict[str, Any]],
    *,
    db: Session,
    dry_run: bool = False,
) -> LoaderStats:
    stats = LoaderStats(source=AQUATIC_SOURCE)
    for rec in records:
        stats.considered += 1
        if not rec.get("is_public", False):
            stats.skipped_not_public += 1
            continue
        synth = _aquatic_synthetic_url(rec)
        if _has_existing_source_url(db, synth):
            stats.skipped_duplicate += 1
            continue

        built = _aquatic_event_payload(rec)
        if built is None:
            stats.skipped_invalid += 1
            continue
        payload, approve, tags = built
        if dry_run:
            stats.imported_event += 1
            continue
        try:
            created = cs.create_contribution(db, payload)
            try:
                approve_contribution_as_event(db, created.id, approve, tags)
                stats.imported_event += 1
            except Exception as e:  # noqa: BLE001
                stats.auto_approval_failed += 1
                stats.errors.append(f"approve event {created.id}: {e}")
        except Exception as e:  # noqa: BLE001
            stats.skipped_invalid += 1
            stats.errors.append(f"contribution: {e}")
    return stats


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

def load_latest_snapshots(*, dry_run: bool = False) -> list[LoaderStats]:
    """Load the newest snapshot from each source into the catalog.

    Idempotent: re-running over an unchanged snapshot results in 0
    imports because every source URL is already in the catalog.
    """
    results: list[LoaderStats] = []

    webtrac_records = scrape_runner.load_latest_records(WEBTRAC_SOURCE)
    aquatic_records = scrape_runner.load_latest_records(AQUATIC_SOURCE)

    with SessionLocal() as db:
        if webtrac_records:
            results.append(load_webtrac_records(webtrac_records, db=db, dry_run=dry_run))
        else:
            results.append(LoaderStats(source=WEBTRAC_SOURCE, errors=["no snapshot found"]))

        if aquatic_records:
            results.append(load_aquatic_records(aquatic_records, db=db, dry_run=dry_run))
        # DISABLED 2026-05-22: the lhcaz_aquatic source is currently disabled
        # in scripts/run_scrapes.py::SOURCES (city moved schedule to PDF —
        # see outputs/lhcaz_aquatic_pdf_rewrite_carry.md). When no aquatic
        # snapshot exists on disk, omit the source from results rather than
        # emitting a "no snapshot found" error. Restore the else-branch (or
        # replace with the new PDF flow) when re-enabling the scraper.

    return results


# ---------------------------------------------------------------------------
# Pruner — stale aquatic events
# ---------------------------------------------------------------------------

@dataclass
class PruneStats:
    """Result of a single ``prune_stale_aquatic`` run."""

    source: str
    cutoff: date
    matched: int = 0  # rows that satisfied the prune predicate
    deleted: int = 0  # rows actually removed from the DB (0 if dry_run)
    dry_run: bool = False
    errors: list[str] = field(default_factory=list)


def prune_stale_aquatic(
    *,
    db: Session,
    today: date | None = None,
    grace_days: int = AQUATIC_PRUNE_GRACE_DAYS,
    dry_run: bool = False,
) -> PruneStats:
    """Hard-delete aquatic Event rows whose ``date`` is older than the
    cutoff (``today - grace_days``).

    The aquatic schedule scraper republishes ~25 days at a time. Old
    occurrences stay in ``events`` forever; chat date-filters them but
    row count drifts up. This is the periodic fix.

    Scope: ONLY rows whose ``source_url`` matches the aquatic schedule
    URL substring. WebTrac registrations carry stable ``FMID``s and a
    different host; they are intentionally untouched.

    Identifier note: live aquatic Events carry ``source='admin'`` (see
    ``approve_contribution_as_event`` — only ``river_scene_import``
    survives onto the Event row). ``source_url`` is the canonical
    aquatic identifier.

    Args:
        db: Session to operate on.
        today: Reference date. Defaults to ``date.today()`` (caller's
            local clock — adequate; cutoff has 7-day grace).
        grace_days: Keep events whose ``date`` is within this many days
            before ``today``. Defaults to ``AQUATIC_PRUNE_GRACE_DAYS``.
        dry_run: When True, count without deleting.

    Returns:
        ``PruneStats`` with ``matched`` (predicate hits) and ``deleted``
        (0 for dry runs).
    """
    today = today or date.today()
    cutoff = today - timedelta(days=max(0, int(grace_days)))
    stats = PruneStats(source=AQUATIC_SOURCE, cutoff=cutoff, dry_run=bool(dry_run))

    try:
        from app.db.models import Event  # local import — keeps loader importable in tests

        q = db.query(Event).filter(
            Event.source_url.like(AQUATIC_SOURCE_URL_LIKE),
            Event.date < cutoff,
        )
        stats.matched = q.count()
        if dry_run or stats.matched == 0:
            return stats

        deleted = q.delete(synchronize_session=False)
        db.commit()
        stats.deleted = int(deleted or 0)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        stats.errors.append(str(e))
    return stats


def prune_latest(
    *,
    grace_days: int = AQUATIC_PRUNE_GRACE_DAYS,
    dry_run: bool = False,
) -> PruneStats:
    """Convenience wrapper opening a ``SessionLocal`` for the CLI.

    Mirrors ``load_latest_snapshots`` so the script layer doesn't have
    to know about session plumbing.
    """
    with SessionLocal() as db:
        return prune_stale_aquatic(db=db, grace_days=grace_days, dry_run=dry_run)
