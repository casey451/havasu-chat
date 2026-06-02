"""Event-at-a-saved-venue surfacing for the weekend digest (Phase A3).

This is the "event at a saved venue" capability the lane brief calls for. It is
implemented HERE (and in the digest builder) as a self-contained query, NOT as
a new alert type in ``app.alerts.*`` — that boundary is owned by a sibling lane
and must not be touched.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.auth.favorites import followed_venue_entity_ids
from app.db.models import Event
from app.events.queries import events_for_favorite_entities


def saved_venue_events_for_user(
    db: Session,
    user_id: str,
    *,
    window_start: date,
    window_end: date,
    limit: int = 50,
) -> list[tuple[Event, date]]:
    """Events in the window happening at the user's saved/followed venues.

    Returns (event, occurrence_date) tuples sorted chronologically. Honest empty
    list when the user follows no venues or none of them have events in window.
    """
    venue_ids = followed_venue_entity_ids(db, user_id)
    if not venue_ids:
        return []
    return events_for_favorite_entities(
        db,
        venue_entity_ids=venue_ids,
        window_start=window_start,
        window_end=window_end,
        limit=limit,
    )
