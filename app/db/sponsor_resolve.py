"""Resolve ``Sponsor.business_id`` using ``Sponsor.entity_type`` (Phase 1D).

``business_id`` remains an Integer column without a DB FK; Phase 11 monetization
may unify typing with ``Entity.id``. Commercial sponsors reference Provider rows
by storing the Provider primary key as decimal digits (string-safe lookup).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.entity_types import ENTITY_TYPE_COMMERCIAL, ENTITY_TYPE_PLACE
from app.db.models import Provider, Sponsor


def resolve_sponsor_linked_provider(db: Session, sponsor: Sponsor) -> Provider | None:
    """Return the Provider row for a commercial sponsor, else ``None``."""
    if sponsor.business_id is None:
        return None
    et = (sponsor.entity_type or ENTITY_TYPE_COMMERCIAL).strip().lower()
    if et == ENTITY_TYPE_COMMERCIAL:
        key = str(sponsor.business_id)
        return db.get(Provider, key)
    if et == ENTITY_TYPE_PLACE:
        return None
    return None
