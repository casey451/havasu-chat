"""Phase 6.5 — homepage Browse section: 8 themed group + solo category tiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.api.routes import category_pages as cat_pages
from app.groups import themed_groups as tg

_COUNT_CAP = 200

# Order locked for Phase 6.5: 4 themed groups, then 4 solo categories.
_HOME_BROWSE_TILE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("group", "eat-drink-group", "Eat & Drink"),
    ("group", "health-fitness-group", "Health & Fitness"),
    ("group", "on-the-water-group", "On the Water"),
    ("group", "home-auto-group", "Home & Auto"),
    ("category", "events", "Events"),
    ("category", "outdoors-parks-trails", "Outdoors, Parks & Trails"),
    ("category", "lodging-vacation-rentals", "Lodging & Vacation Rentals"),
    ("category", "public-civic-resources", "Public & Civic Resources"),
)


@dataclass(frozen=True)
class BrowseTileSpec:
    kind: str
    slug: str
    title: str


def browse_tile_specs() -> tuple[BrowseTileSpec, ...]:
    return tuple(BrowseTileSpec(k, s, t) for k, s, t in _HOME_BROWSE_TILE_SPECS)


def count_entities_for_category_slugs(db: Session, category_slugs: list[str]) -> int:
    if not category_slugs:
        return 0
    return len(
        cat_pages.select_entities_for_categories(
            db,
            category_slugs=category_slugs,
            district_slug=None,
            boat_only=False,
        )
    )


def format_tile_count_label(raw_count: int) -> str:
    if raw_count >= _COUNT_CAP:
        return f"{_COUNT_CAP}+ businesses"
    if raw_count == 1:
        return "1 business"
    return f"{raw_count} businesses"


def _tile_url(spec: BrowseTileSpec) -> str:
    if spec.kind == "group":
        return f"/group/{spec.slug}"
    return f"/category/{spec.slug}"


def _tile_subtitle(spec: BrowseTileSpec) -> str:
    if spec.kind == "group":
        return tg.group_one_liner(spec.slug)
    return cat_pages._CATEGORY_ONE_LINERS.get(
        spec.slug,
        "Browse trusted local listings.",
    )


def build_browse_tiles(db: Session) -> list[dict[str, Any]]:
    """Return template context dicts for ``components/themed_tile.html``."""
    tiles: list[dict[str, Any]] = []
    for spec in browse_tile_specs():
        if spec.kind == "group":
            cats = tg.get_categories_for_group(spec.slug)
            raw = count_entities_for_category_slugs(db, cats)
        else:
            raw = count_entities_for_category_slugs(db, [spec.slug])
        tiles.append(
            {
                "tile_title": spec.title,
                "tile_url": _tile_url(spec),
                "tile_hero_image_url": None,
                "tile_subtitle": _tile_subtitle(spec),
                "tile_count": format_tile_count_label(raw),
                "tile_count_raw": raw,
                "tile_slug": spec.slug,
                "tile_kind": spec.kind,
            }
        )
    return tiles
