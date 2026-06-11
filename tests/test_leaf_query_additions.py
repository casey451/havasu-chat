"""2026-06-11 leaf-routing additions — normalization + slug-drift CI guard.

DB-free: these assert the dict + normalizer layer only. The DB existence and
≥3-provider gate are exercised by the existing leaf_query integration tests;
entries pointing at not-yet-seeded leaves are deliberate no-ops at runtime
(resolve_leaf_by_slug returns None) and self-activate when the taxonomy
rebuild ships — PENDING_LEAF_SLUGS + the sync test below keep slug names from
drifting silently.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.categories.leaf_query import _QUERY_TO_LEAF, PENDING_LEAF_SLUGS, _normalize

_SEED = Path(__file__).resolve().parents[1] / "docs" / "proposals" / "taxonomy-seed.json"


def _live_seed_slugs() -> frozenset[str]:
    data = json.loads(_SEED.read_text(encoding="utf-8"))
    slugs: set[str] = set()
    for body in data.values():
        slugs.update((body.get("leaves") or {}).keys())
    return frozenset(slugs)


def test_every_target_slug_is_live_or_tracked_pending():
    live = _live_seed_slugs()
    unknown = {
        (term, slug)
        for term, slug in _QUERY_TO_LEAF.items()
        if slug not in live and slug not in PENDING_LEAF_SLUGS
    }
    assert not unknown, f"navigational entries point at untracked slugs: {sorted(unknown)}"


def test_pending_slugs_do_not_mask_live_ones():
    # When the rebuild seeds a leaf, it should be REMOVED from PENDING so the
    # set documents only genuinely-unseeded slugs.
    live = _live_seed_slugs()
    seeded_but_pending = PENDING_LEAF_SLUGS & live
    assert not seeded_but_pending, (
        f"slugs now live in taxonomy-seed.json — drop from PENDING_LEAF_SLUGS: "
        f"{sorted(seeded_but_pending)}"
    )


def test_new_navigational_terms_normalize_to_dict_keys():
    # Phrasings users actually type must reach the entry post-normalization.
    cases = {
        "best laundromat in lake havasu": "laundry-and-dry-cleaning",
        "golf carts": "golf-carts",
        "window tinting near me": "window-tint-and-wraps",
        "vehicle wraps": "window-tint-and-wraps",
        "auto glass": "auto-glass",
        "property management": "property-management",
        "funeral homes": "funeral-cremation-and-cemeteries",
        "urgent care": "urgent-care-and-er",
        "hearing aids": "hearing-and-audiology",
        "smoke shops": "smoke-vape-and-cannabis",
        "computer repair": "computer-and-it-repair",
        "boat storage": "boat-and-rv-storage-service",
        "auto detailing": "auto-detailing",
        "boat detailing": "auto-marine-detailing",
        "pet sitters": "pet-sitting",
        "dog boarding": "boarding-and-daycare",
        "junk removal": "junk-removal-and-hauling",
        "pressure washing": "pressure-washing-and-exterior-cleaning",
        "shooting range": "firearms-and-shooting-sports",
        "notary": "notary",
        "tutoring": "tutoring-and-test-prep",
        "casinos": "casinos-and-gaming",
    }
    for raw, slug in cases.items():
        norm = _normalize(raw)
        assert norm in _QUERY_TO_LEAF, (raw, norm)
        assert _QUERY_TO_LEAF[norm] == slug, (raw, norm, _QUERY_TO_LEAF[norm])


def test_original_entries_untouched():
    for term, slug in {
        "plumbers": "plumbing",
        "boat rentals": "boat-and-watercraft-rentals",
        "med spas": "med-spas-and-aesthetics",
        "bowling": "family-fun-and-arcades",
        "towing": "towing-and-roadside",
    }.items():
        assert _QUERY_TO_LEAF[term] == slug
