"""Minimum-information bar for calendar events and classes (2026-06-23).

Casey's rule: an event/class with no real information is removed and is NOT
ingested going forward. The bar (owner-chosen "core + description"):

* **Event** must have a title, a date, a REAL venue (not the title-as-venue
  artifact), a source link, AND a non-empty description.
* **Class** (recurring Schedule) must have a title, a venue, day(s), AND a start
  time. (A class row shows title/venue/when — that is its complete information;
  it has no separate description field on the calendar.)

The ingest guard (block future low-info rows) calls these; the description
backfill targets ``event_missing_info(..., 'description')`` rows.

DECISION (2026-06-23, after the dry-run): a dump showed the "core + description"
bar would flag 45 *real* events (the Farmers Market ×27, July-4th Fireworks, the
parade, Taste of Havasu) that simply lack a prose blurb — so the answer is to
**find** the missing descriptions (``scripts/backfill_event_descriptions_2026_06_23.py``
re-fetches them from each event's source page), NOT to drop the events. The
ingest guard therefore blocks only the genuinely-empty floor (no title / date /
real venue / source link); the description requirement stays OFF for blocking
(:data:`REQUIRE_DESCRIPTION` ``= False``) and is used only to *locate* rows the
backfill should enrich.
"""

from __future__ import annotations

from datetime import date, time

from app.events.scrapers.base import normalize_event_title

# OFF for blocking: a description-less event is enriched (descriptions backfilled
# from the source page), never dropped. Set True only to also *locate* rows that
# still need a description (the backfill script does this explicitly).
REQUIRE_DESCRIPTION = False

_MIN_TITLE = 3


def _blank(value: str | None) -> bool:
    return not (value and str(value).strip())


def event_missing_info(
    *,
    title: str | None,
    start_date: date | None,
    location_name: str | None,
    source_url: str | None,
    description: str | None,
) -> list[str]:
    """Return the list of missing core fields (empty list = meets the bar).

    ``location_name`` / ``source_url`` / ``description`` are the RESOLVED values
    (post-normalization for ingest, or the stored row values for removal)."""
    missing: list[str] = []
    if _blank(title) or len(title.strip()) < _MIN_TITLE:  # type: ignore[union-attr]
        missing.append("title")
    if start_date is None:
        missing.append("date")
    loc = (location_name or "").strip()
    if not loc:
        missing.append("venue")
    elif title and normalize_event_title(loc) == normalize_event_title(title):
        missing.append("venue(title-as-venue)")
    if _blank(source_url):
        missing.append("link")
    if REQUIRE_DESCRIPTION and _blank(description):
        missing.append("description")
    return missing


def event_meets_min_info(**kwargs: object) -> bool:
    return not event_missing_info(**kwargs)  # type: ignore[arg-type]


def class_missing_info(
    *,
    title: str | None,
    venue: str | None,
    days: list | None,
    start_time: time | None,
) -> list[str]:
    """Return the list of missing core fields for a recurring class Schedule."""
    missing: list[str] = []
    if _blank(title):
        missing.append("title")
    if _blank(venue):
        missing.append("venue")
    if not days:
        missing.append("days")
    if start_time is None:
        missing.append("time")
    return missing


def class_meets_min_info(**kwargs: object) -> bool:
    return not class_missing_info(**kwargs)  # type: ignore[arg-type]
