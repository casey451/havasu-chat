"""Cross-surface references (Phase 2 / IA v2 — Slice 2).

A department landing may *surface* leaves whose canonical home is a different
department, grouped under a labeled section — so a boater finds boat repair under
**Lake & Boating** and a parent finds youth classes under **For Kids & Families**
without the listing being duplicated. Each surfaced card links to the leaf's
canonical ``/categories/{dept}/{leaf}`` page.

Source of truth: ``docs/proposals/taxonomy_v2_build_spec.json`` (``cross_surface``).
Surfaced leaves respect the same thin-page gate as canonical leaf pages, so a
card never links to a leaf that would 404.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

# Host department slug -> ordered sections. Each leaf is (source_department_slug,
# leaf_slug); the leaf's canonical home stays the source department.
CROSS_SURFACE: dict[str, list[dict[str, Any]]] = {
    "on-the-water": [
        {
            "heading": "Boat services",
            "leaves": [
                ("auto-rv-and-marine", "boat-repair-and-service"),
                ("auto-rv-and-marine", "boat-sales"),
                ("auto-rv-and-marine", "auto-marine-detailing"),
                ("auto-rv-and-marine", "boat-and-rv-storage-service"),
            ],
        },
        {
            "heading": "Fuel & supplies",
            "leaves": [
                ("auto-rv-and-marine", "gas-stations"),
                ("shopping-and-retail", "sporting-goods"),
            ],
        },
    ],
    "family-and-education": [
        {
            "heading": "Classes & lessons",
            "leaves": [
                ("fitness-and-wellness", "martial-arts"),
                ("fitness-and-wellness", "dance-studios"),
                ("fitness-and-wellness", "gyms-and-fitness-centers"),
            ],
        },
        {
            "heading": "Fun for kids",
            "leaves": [
                ("things-to-do-and-attractions", "family-fun-and-arcades"),
                ("things-to-do-and-attractions", "parks-and-playgrounds"),
            ],
        },
    ],
    "health-and-medical": [
        {
            "heading": "Skin & aesthetics",
            "leaves": [
                ("beauty-and-personal-care", "med-spas-and-aesthetics"),
            ],
        },
    ],
}


def cross_surface_sections(db: Session, host_slug: str) -> list[dict[str, Any]]:
    """Sections of cross-surfaced leaf cards for ``host_slug``.

    Shape mirrors the canonical leaf cards: ``[{heading, leaves: [{name, count,
    url}]}]``. A leaf is skipped if it can't be resolved or is below the
    thin-page minimum (so a card never links to a leaf page that would 404).
    Empty sections collapse away; returns ``[]`` for departments with no refs.
    """
    from app.categories import leaf_pages, leaf_seo

    sections: list[dict[str, Any]] = []
    for section in CROSS_SURFACE.get(host_slug, []):
        cards: list[dict[str, Any]] = []
        for src_dept, leaf_slug in section["leaves"]:
            leaf = leaf_pages.resolve_leaf(db, src_dept, leaf_slug)
            if leaf is None:
                continue
            count = leaf_pages.leaf_renderable_count(db, leaf)
            if count < leaf_pages.LEAF_PAGE_MIN_PROVIDERS:
                continue
            cards.append(
                {
                    "name": leaf_seo.display_noun(leaf.slug, leaf.name),
                    "count": count,
                    "url": f"/categories/{leaf.department_slug}/{leaf.slug}",
                }
            )
        if cards:
            sections.append({"heading": section["heading"], "leaves": cards})
    return sections
