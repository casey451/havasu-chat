"""Layered-scrape framework: abstract base + shared dataclasses.

Each scrape layer (Google Places, OSM, city open data, specialized APIs)
implements a subclass of :class:`BaseIngestClient`. Subclasses own the
source-specific HTTP layer, response parsing, dedupe-key derivation, and
entity-payload mapping; callers (scripts, future Railway jobs) own persistence
and reconciler hand-off.

Design: ``docs/maintainability/layered_scrape_strategy.md``. Phase 4.2 ships
this base plus the Google Places library; Phase 4.3 adds OSM + reconciler.

**Phase 1D dual-write seam.** Production ingest writes new catalog rows via
``session.add(Provider(...))`` (or Event/Program). The centralized
``before_flush`` hook registered in ``app/db/__init__.py`` auto-promotes to
``Entity`` + extension tables. Clients must not insert into ``entities`` or
extension tables directly.

This module stays ORM-free at import time: only dataclasses, ``typing``, and
``abc`` -- no ``app.db.models`` imports.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawHit:
    """Raw response data from a single source (one entity per hit)."""

    source: str
    source_stable_id: str
    name: str
    lat: float | None = None
    lng: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class EnrichedHit:
    """RawHit plus enrichment fetch (full detail beyond discovery)."""

    raw_hit: RawHit
    enriched: dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityPayload:
    """Source-agnostic payload describing one entity candidate for ingest."""

    name: str
    entity_type: str
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    description: str | None = None
    category_slug: str | None = None
    # Optional legacy free-text Provider.category string (e.g. "restaurant",
    # "lodging") for sources that need to populate BOTH the Tier-1 category_id
    # (via category_slug) AND the legacy Provider.category column that older
    # category-page queries still filter on. None => caller's default applies.
    legacy_category: str | None = None
    google_place_id: str | None = None
    source: str = "unknown"
    extension_payloads: dict[str, Any] = field(default_factory=dict)


class BaseIngestClient(ABC):
    """Abstract base for layered-scrape clients."""

    source_name: str = "unknown"

    @abstractmethod
    def discover(self, query: dict[str, Any]) -> list[RawHit]:
        """Source-specific discovery. *query* is source-defined (e.g. textQuery)."""

    @abstractmethod
    def enrich(self, hit: RawHit) -> EnrichedHit:
        """Source-specific enrichment (e.g. Place Details). No-op sources return
        ``EnrichedHit(raw_hit=hit)``."""

    @abstractmethod
    def dedupe_key(self, hit: RawHit) -> str:
        """Stable per-source dedupe identifier."""

    @abstractmethod
    def to_entity_payload(self, hit: EnrichedHit) -> EntityPayload:
        """Map an enriched hit into a source-agnostic payload."""

    def run(self, query: dict[str, Any]) -> list[EntityPayload]:
        """Discover → enrich → payloads (no DB writes)."""
        hits = self.discover(query)
        enriched = [self.enrich(h) for h in hits]
        return [self.to_entity_payload(e) for e in enriched]
