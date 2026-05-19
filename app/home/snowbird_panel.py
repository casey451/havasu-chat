"""Homepage snowbird-return panel context (Phase 7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat import snowbird_query
from app.core.timezone import now_lake_havasu
from app.db.models import Entity, Provider, User
from app.providers.queries import effective_seasonal_hours


@dataclass(frozen=True)
class SnowbirdPanelEntity:
    name: str
    profile_url: str
    status_copy: str | None = None


@dataclass(frozen=True)
class SnowbirdPanelContext:
    entities: tuple[SnowbirdPanelEntity, ...]


def _profile_url(ent: Entity, provider: Provider | None) -> str:
    if provider and provider.slug:
        return f"/provider/{provider.slug}"
    if ent.slug:
        return f"/provider/{ent.slug}"
    return "/home"


def build_snowbird_panel_context(
    db: Session,
    *,
    current_user: User | None,
    now=None,
) -> SnowbirdPanelContext | None:
    """Return panel data for logged-in snowbird users in-season, else None."""
    if current_user is None:
        return None
    now_dt = now or now_lake_havasu()
    if not snowbird_query.is_snowbird_calendar_window(now_dt.date()):
        return None
    if not snowbird_query.user_has_snowbird_activity_pattern(
        current_user.last_active_at, now=now_dt
    ):
        return None

    reopened = snowbird_query.get_snowbird_reopened_entities(db, now=now_dt)
    if not reopened:
        return None

    eids = [e.id for e in reopened]
    prov_map = {
        p.entity_id: p
        for p in db.scalars(select(Provider).where(Provider.entity_id.in_(eids))).all()
    }
    items: list[SnowbirdPanelEntity] = []
    for ent in reopened:
        prov = prov_map.get(ent.id)
        _season, _hours, copy = effective_seasonal_hours(ent, now=now_dt)
        items.append(
            SnowbirdPanelEntity(
                name=ent.name or "",
                profile_url=_profile_url(ent, prov),
                status_copy=copy,
            )
        )
    return SnowbirdPanelContext(entities=tuple(items))


def snowbird_panel_template_dict(
    ctx: SnowbirdPanelContext | None,
) -> dict[str, Any] | None:
    if ctx is None or not ctx.entities:
        return None
    return {
        "entities": [
            {"name": e.name, "profile_url": e.profile_url, "status_copy": e.status_copy}
            for e in ctx.entities
        ]
    }
