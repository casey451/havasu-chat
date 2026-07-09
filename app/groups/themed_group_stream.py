"""Themed-group card stream with event interleaving (Phase 9b)."""

from __future__ import annotations

import os
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import category_pages as cat_pages
from app.core.conditions_temperature import read_current_temperature_f
from app.core.ranking import _cap_event_share, compute_event_card_rank
from app.db.models import Category, Entity, EntityCategory, Event
from app.events.queries import event_window_for_chip, events_in_window
from app.groups import themed_groups as tg
from app.providers import queries as provider_queries
from app.providers.view_models import HavaCardViewModel


def _event_in_category_bundle(event: Event, cat_slugs: set[str], db: Session) -> bool:
    ent = db.get(Entity, event.entity_id)
    if ent is None:
        return False
    slugs = {ec.category.slug for ec in ent.categories if ec.category is not None}
    if slugs & cat_slugs:
        return True
    rows = db.scalars(
        select(Category.slug)
        .join(EntityCategory, EntityCategory.category_id == Category.id)
        .where(EntityCategory.entity_id == event.entity_id)
    ).all()
    return bool(set(rows) & cat_slugs)


_KNOWN_WHEN_CHIPS = frozenset({"today", "this-weekend", "this-week", "next-month"})


def _when_window(when: str | None, today: date) -> tuple[date, date] | None:
    """Date window for the events 'when' chips, or ``None`` for no/unknown filter.

    Shares :func:`event_window_for_chip`'s semantics (this-weekend =
    Friday-through-Sunday) so the same chip means the same dates everywhere.
    """
    if not when or when not in _KNOWN_WHEN_CHIPS:
        return None
    # Delegate to event_window_for_chip so the same chip means the same dates
    # on every surface — this module used to keep its own copy with strict
    # Sat–Sun weekend semantics, so a Friday-night concert showed under "this
    # weekend" on the events pages but not on a themed-group page.
    return event_window_for_chip(when, today=today)


def get_themed_group_card_stream(
    db: Session,
    group_slug: str,
    *,
    limit: int = 30,
    ref_lat: float,
    ref_lng: float,
    now,
    boat_only: bool = False,
    when: str | None = None,
) -> list[HavaCardViewModel]:
    """Interleaved entity + event cards for a themed group landing page."""
    cat_slugs = tg.get_categories_for_group(group_slug)
    if not cat_slugs:
        return []

    cat_set = set(cat_slugs)
    entities = cat_pages.select_entities_for_categories(
        db,
        category_slugs=cat_slugs,
        district_slug=None,
        boat_only=boat_only,
    )
    sort_slug = cat_slugs[0]
    entities = cat_pages._sort_entity_ids(
        entities,
        sort_key="closest_now",
        ref_lat=ref_lat,
        ref_lng=ref_lng,
        db=db,
        category_slug=sort_slug,
        now=now,
    )

    # Honesty gate (§7.2): provider ids holding an active paid category placement
    # on this surface — so the cards `_sort_entity_ids` just pinned to the top
    # render the Sponsored label. Empty (dormant) until a placement is sold.
    from app.monetization.serving import active_category_tiers

    sponsored_ids = set(active_category_tiers(db, sort_slug).values())

    today = now.date() if hasattr(now, "date") else date.today()
    # A 'when' chip (today / this-weekend / this-week / next-month) narrows the
    # event window and switches the stream to events-only (see below).
    win = _when_window(when, today)
    events_only = win is not None
    window_start, window_end = win if events_only else (today, today + timedelta(days=30))
    upcoming = events_in_window(
        db,
        window_start=window_start,
        window_end=window_end,
        category_slug=None,
        limit=limit * 4,
    )

    scored: list[tuple[HavaCardViewModel, float]] = []
    seen_entity: set[str] = set()

    temp_f = read_current_temperature_f(db)
    boat_mode = boat_only

    # Place (entity) cards are skipped when a date filter is active: a venue has no
    # date, so "Today" / "This weekend" should surface only events in that window.
    for ent in (entities if not events_only else []):
        if ent.id in seen_entity:
            continue
        seen_entity.add(ent.id)
        vm = provider_queries.build_card_view_model(
            db, ent.id, now=now, sponsored_provider_ids=sponsored_ids
        )
        if vm is None:
            continue
        inp = cat_pages.rank_inputs_for_category(
            [ent],
            category_slug=sort_slug,
            ref_lat=ref_lat,
            ref_lng=ref_lng,
            prov_by_eid={},
            now=now,
        ).get(ent.id)
        from app.core.ranking import compute_card_rank

        score = compute_card_rank(inp, now=now, temperature_f=temp_f) if inp else 0.5
        scored.append((vm, score))

    for event, occ_date in upcoming:
        if not _event_in_category_bundle(event, cat_set, db):
            continue
        if event.entity_id in seen_entity:
            continue
        vm = provider_queries.build_card_view_model_for_event_occurrence(
            db, event.id, occ_date, now=now
        )
        if vm is None:
            continue
        dist = None
        ent = db.get(Entity, event.entity_id)
        if ent and ent.location:
            dist = cat_pages._distance_km_for_entity(ent, ref_lat, ref_lng)
        score = compute_event_card_rank(
            event=event,
            occurrence_date=occ_date,
            now_temp_f=temp_f,
            distance_mi=(dist * 0.621371) if dist is not None else None,
            user_in_boat_mode=boat_mode,
            venue_heat_exposure=ent.heat_exposure if ent else None,
            venue_boat_access=ent.boat_access is not None if ent else False,
        )
        scored.append((vm, score))

    if events_only:
        # No event-share cap when a date filter is active — events ARE the result
        # here, not an interleaved minority. Highest-scored first, page-limited.
        scored.sort(key=lambda it: it[1], reverse=True)
        return [vm for vm, _ in scored[:limit]]
    cap_pct = float(os.environ.get("THEMED_GROUP_EVENT_CAP_PCT", "0.40"))
    capped = _cap_event_share(scored, max_event_pct=cap_pct, limit=limit)
    return [vm for vm, _ in capped]
