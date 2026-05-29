"""Deterministic ranking helpers for home-page picks (BUILD.md step 8 Option C).

Replaces ``featured.desc()`` as the PRIMARY sort with deterministic per-row
expressions; ``featured`` stays as the tiebreaker for psql-flip manual overrides.
"""

from __future__ import annotations

from app.db.models import Event, Program, Provider


def tonight_ranking():
    """Tonight row: start_time ascending; manual ``featured`` wins as tiebreaker."""
    return [Event.featured.desc(), Event.start_time.asc()]


def this_week_ranking():
    """This-week row: date then start_time; ``featured`` as tiebreaker."""
    return [Event.featured.desc(), Event.date.asc(), Event.start_time.asc()]


def new_on_hava_ranking():
    """New-on-Hava events: pure recency (no ``featured`` override in sort)."""
    return [Event.created_at.desc()]


def new_on_hava_program_ranking():
    """New-on-Hava programs: pure recency."""
    return [Program.created_at.desc()]


def new_on_hava_provider_ranking():
    """New-on-Hava providers: pure recency."""
    return [Provider.created_at.desc()]


def category_pick_index(rows: list) -> int | None:
    """Return index of the row that should get the 'Hava's pick' badge.

    First ``featured=True`` if any, else index 0. One pick per row.
    """
    for idx, row in enumerate(rows):
        if getattr(row, "featured", False):
            return idx
    return 0 if rows else None
