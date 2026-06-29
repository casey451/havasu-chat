"""Canary listings (A4): seeded decoy businesses that act as copy-tripwires.

Each canary is a *fake* local business with a unique name, address, phone, and —
most importantly — a unique editorial ``unique_phrase`` that appears in no real
listing and nowhere else on the web. If that phrase ever turns up on an external
site (havasu.info first), it's strong evidence the directory was scraped, and an
early-warning that a competitor is copying us.

Canaries carry ``source == CANARY_SOURCE`` so they are kept out of real data:
  * the provider sitemap (``app/main.py::_build_sitemap_providers_xml``), and
  * every "N listed" count + category listing
    (``app/categories/queries.py::primary_listing_filter``),
both via :func:`not_canary_clause`.

The off-site scanner (``app/monitoring/canary_scanner.py``) reads the phrases
from :data:`CANARIES` directly, so detection works *before* any DB seeding.
Seeding the canary rows into a live DB is a separate, gated step
(``scripts/seed_canaries.py`` — dry-run → counts → Casey approves), because it is
a production write and a product decision (how prominently, if at all, the canary
pages should surface so a site-cloning scraper picks them up).

Phone numbers use the 555-01xx range reserved for fiction (never assigned), and
the street addresses are invented, so a canary can never collide with a real
business or misdirect a visitor.
"""

from __future__ import annotations

from dataclasses import dataclass

# ``Provider.source`` marker stamped on every seeded canary row.
CANARY_SOURCE = "canary"


@dataclass(frozen=True)
class Canary:
    """One decoy listing. ``unique_phrase`` is the watermark hunted off-site."""

    slug: str
    name: str
    phone: str
    address: str
    website: str
    description: str
    unique_phrase: str


# A small, deliberately weird set — distinctive enough that the unique_phrase is
# effectively un-guessable and would only appear elsewhere via a copy of our data.
CANARIES: tuple[Canary, ...] = (
    Canary(
        slug="trailside-mapworks-of-havasu",
        name="Trailside Mapworks of Havasu",
        phone="(928) 555-0174",
        address="1147 Dragoon Wash Spur, Lake Havasu City, AZ 86403",
        website="https://trailside-mapworks-havasu.example",
        description=(
            "A two-person studio hand-inking desert trail maps of the Havasu "
            "backcountry."
        ),
        unique_phrase=(
            "Every Trailside Mapworks chart is hand-inked and stamped with our "
            "Dragoon Wash compass rose, a detail we have carried since 2019."
        ),
    ),
    Canary(
        slug="solstice-tinware-and-lantern-co",
        name="Solstice Tinware & Lantern Co.",
        phone="(928) 555-0192",
        address="88 Coppermoon Alley, Lake Havasu City, AZ 86404",
        website="https://solstice-tinware-havasu.example",
        description=(
            "Punched-tin lanterns and luminaria made to order from a small "
            "Coppermoon Alley workshop."
        ),
        unique_phrase=(
            "Each Solstice lantern carries our Coppermoon Alley solstice "
            "hallmark, punched by hand so that no two patterns are ever alike."
        ),
    ),
)


def canary_slugs() -> frozenset[str]:
    """The provider slugs reserved for canaries."""
    return frozenset(c.slug for c in CANARIES)


def canary_phrases() -> tuple[str, ...]:
    """The watermark phrases the off-site scanner hunts for."""
    return tuple(c.unique_phrase for c in CANARIES)


def not_canary_clause():
    """SQLAlchemy boolean clause: a Provider that is NOT a seeded canary.

    NULL-safe — a real row with ``source IS NULL`` must still pass — so callers
    can AND this into any provider query/count to drop canaries without changing
    behavior for genuine listings.
    """
    from sqlalchemy import or_

    from app.db.models import Provider

    return or_(Provider.source.is_(None), Provider.source != CANARY_SOURCE)
