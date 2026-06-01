"""Canonical entity_type values for the unified ENTITY schema.

Stored as plain string in entities.entity_type — Postgres ENUM types are
avoided here so adding a new type in code doesn't require an Alembic
migration (matches the AdSlot/SponsorStatus pattern in models.py).

Validation happens in app-layer code, not at the DB level.
"""

from __future__ import annotations

ENTITY_TYPE_COMMERCIAL = "commercial"
ENTITY_TYPE_PLACE = "place"
ENTITY_TYPE_EVENT = "event"
ENTITY_TYPE_PROGRAM = "program"

ENTITY_TYPES: frozenset[str] = frozenset(
    {
        ENTITY_TYPE_COMMERCIAL,
        ENTITY_TYPE_PLACE,
        ENTITY_TYPE_EVENT,
        ENTITY_TYPE_PROGRAM,
    }
)


def is_valid_entity_type(value: str) -> bool:
    return value in ENTITY_TYPES
