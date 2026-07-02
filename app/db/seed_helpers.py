"""Shared helpers for catalog ingest / seeding."""

from __future__ import annotations

from sqlalchemy import event, or_, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper, Session, object_session

from app.utils.slug import make_unique_slug, slugify

_PROVIDER_SLUG_HOOKS_REGISTERED = False


def derive_provider_slug(session: Session, provider_name: str) -> str:
    """Return a slug for ``provider_name`` unique among persisted rows and pending ``Provider`` instances."""
    from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
    from app.db.models import Entity, Provider

    # Probe only slugs that could collide with this base (audit 2026-07-01:
    # this used to pull EVERY provider + commercial-entity slug per new
    # Provider — O(n^2) across a bulk load). slugify() output is [a-z0-9-],
    # so the prefix LIKE needs no wildcard escaping.
    base = slugify(provider_name)
    used: set[str] = set()
    for s in session.scalars(
        select(Provider.slug).where(
            Provider.slug.is_not(None),
            or_(Provider.slug == base, Provider.slug.like(f"{base}-%")),
        )
    ):
        if s:
            used.add(s)
    for s in session.scalars(
        select(Entity.slug).where(
            Entity.entity_type == ENTITY_TYPE_COMMERCIAL,
            or_(Entity.slug == base, Entity.slug.like(f"{base}-%")),
        )
    ):
        used.add(s)
    for obj in session.new:
        if isinstance(obj, Provider) and obj.slug:
            used.add(obj.slug)
        if isinstance(obj, Entity) and obj.slug:
            used.add(obj.slug)
    return make_unique_slug(base, used)


def register_provider_slug_hooks() -> None:
    """Wire SQLAlchemy listeners so ``Provider.slug`` is filled when omitted."""
    global _PROVIDER_SLUG_HOOKS_REGISTERED
    if _PROVIDER_SLUG_HOOKS_REGISTERED:
        return
    _PROVIDER_SLUG_HOOKS_REGISTERED = True

    from app.db.models import Provider

    @event.listens_for(Provider, "before_insert")
    def _provider_assign_slug(
        mapper: Mapper[Provider], connection: Connection, target: Provider
    ) -> None:
        if target.slug is not None:
            return
        sess = object_session(target)
        if sess is None:
            target.slug = slugify(target.provider_name)
            return
        target.slug = derive_provider_slug(sess, target.provider_name)
