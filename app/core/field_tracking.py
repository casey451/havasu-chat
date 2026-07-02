"""
Tracked fields for field_history baselines and Phase 5 corrections.

Handoff §5 lists event fields as date/time/location/cost. The Event ORM does not
have a single ``time`` column (use ``start_time`` / ``end_time``), does not have
``location`` (use ``location_name``), and has **no** ``cost`` column — so event
cost cannot be baselined until a future schema change. Provider and program tuples
match ``app/db/models.py`` column names verbatim.
"""

from __future__ import annotations

# Column names must match Provider / Program / Event mapped attributes exactly.


# See module docstring: differs from handoff shorthand ``time`` / ``location`` / ``cost``.
EVENT_TRACKED_FIELDS: tuple[str, ...] = (
    "date",
    "start_time",
    "end_time",
    "location_name",
)
