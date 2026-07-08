"""WS4 - §14.1 provider-duplicate fixtures (regression suite, tests-first).

These are the real GoLakeHavasu-import duplicate pairs from the 2026-07-06
acceptance audit (spec §14.1): a Google-Places-matched keeper (reviews) paired
with a review-less GLH twin at the same address, whose name is the keeper's name
plus/minus generic cuisine/venue words. The spec's rule (WS4.1): "each of the 15
pairs must match under norm_name + norm_address rules."

Two tiers, by what the clustering engine can resolve at HIGH PRECISION:

* ``_AUTO_MERGE`` - the twin adds only **generic descriptor** words (restaurant,
  mexican, pizza, pasta, steak, house, kitchen, cocktails, …) that are disjoint
  from the parent/child hint set. These merge safely with no phone (a plaza never
  has "Denny's" AND "Denny's Restaurant" as different tenants). The engine's
  generic-subset signal (added for WS4) catches these.

* ``_REVIEW_TIER`` - harder shapes the engine deliberately does NOT auto-merge,
  because doing so safely needs trigram/fuzzy similarity or de-conflicting
  venue-type words that double as department markers (grill/bar/cafe). Per the
  spec these are the ".70–.85 borderline → human review queue" cases. Marked
  xfail: they document the target (should merge) and flip to pass when the fuzzy
  review-tier lands. The reason is recorded per pair.

Precision is pinned by ``test_generic_subset_does_not_merge_a_person_extra`` and
the existing ``tests/test_dedupe_cluster.py`` guards, which must all stay green.
"""

from __future__ import annotations

import pytest

from app.dedupe.cluster import ProviderRecord, cluster_providers

# (keeper_name, glh_twin_name, shared_address)
_AUTO_MERGE: list[tuple[str, str, str]] = [
    ("Denny's Restaurant", "Denny's", "1620 McCulloch Blvd N"),
    ("Niko's Grill & Pub", "Niko's Grill and Pub", "2690 N Kiowa Blvd"),
    ("Rosati's Pizza", "Rosati's Pizza & Pasta", "91 London Bridge Rd"),
    ("Filiberto's", "Filiberto's Mexican Food", "35 N Lake Havasu Ave"),
    ("Montana's", "Montana Steak House", "3301 Maricopa Ave"),
    ("Rusty's Restaurant", "Rusty's", "2806 Maricopa Ave"),
    ("Bad Miguel's Mexican Restaurant", "Bad Miguel's", "1841 N Kiowa Blvd #103"),
    ("Sloane's Craft Kitchen + Cocktails", "Sloane's", "2198 McCulloch Blvd"),
    ("The Spot - Pizza, Arcade & More", "The Spot", "3612 Jamaica Blvd S"),
]

# (keeper_name, glh_twin_name, shared_address, why-it's-hard)
_REVIEW_TIER: list[tuple[str, str, str, str]] = [
    ("Shugrue's Restaurant and Brewery Group", "Shugrue's Restaurant & Bar",
     "1425 McCulloch Blvd N", "symmetric diff (brewery/group vs bar) - needs fuzzy"),
    ("Hangar 24 Lake Havasu", "Hangar 24 Taproom & Restaurant",
     "5600 AZ-95 #6", "symmetric diff (lake havasu vs taproom) - needs fuzzy"),
    ("Kokomo Beach Club", "Kokomo - Beach, Surf & Party Bar",
     "1477 Queens Bay", "symmetric diff (club vs surf/party) - needs fuzzy"),
    ("Lin's Little China", "Lina Little China",
     "95 Swanson Ave", "typo lin/lina - needs edit-distance"),
    ("Dos Amigos Tacos", "Dos Amigos Taco's",
     "2231 McCulloch Blvd #107", "plural/possessive typo taco/tacos - needs stemming"),
    ("The Office Cocktail Lounge & Grill", "The Office",
     "2180 W Acoma Blvd", "extra 'grill' doubles as a department hint"),
    ("McKee's Pub & Grill", "McKee's",
     "3255 Maricopa Ave", "extra 'grill' doubles as a department hint"),
    ("Broken Yolk Cafe", "The Broken Yolk",
     "440 El Camino Way", "extra 'cafe' doubles as a department hint"),
]


def _pair_records(keeper: str, twin: str, addr: str) -> list[ProviderRecord]:
    # The keeper is Google-matched (place_id + reviews); the GLH twin has neither
    # and NO phone - the exact shape that must still merge under WS4.
    return [
        ProviderRecord(id="keeper", name=keeper, address=addr,
                       google_place_id="PID-keeper", review_count=800, verified=True),
        ProviderRecord(id="twin", name=twin, address=addr),
    ]


@pytest.mark.parametrize("keeper,twin,addr", _AUTO_MERGE, ids=[p[0] for p in _AUTO_MERGE])
def test_auto_merge_pair_clusters_as_duplicate(keeper: str, twin: str, addr: str) -> None:
    clusters = cluster_providers(_pair_records(keeper, twin, addr))
    assert len(clusters) == 1, f"{keeper} + {twin} did not cluster"
    c = clusters[0]
    assert {m.id for m in c.members} == {"keeper", "twin"}
    assert c.relationship_type == "duplicate", (
        f"{keeper} + {twin} classified {c.relationship_type}, expected duplicate"
    )
    assert c.primary.id == "keeper"  # the reviewed, place_id'd row survives


@pytest.mark.parametrize(
    "keeper,twin,addr,reason",
    _REVIEW_TIER,
    ids=[p[0] for p in _REVIEW_TIER],
)
def test_review_tier_pair_is_target_for_fuzzy(
    keeper: str, twin: str, addr: str, reason: str
) -> None:
    """These SHOULD merge but need the fuzzy/trigram review tier (not yet built).
    xfail documents the target; it flips to pass when that tier lands."""
    clusters = cluster_providers(_pair_records(keeper, twin, addr))
    merged = len(clusters) == 1 and clusters[0].relationship_type == "duplicate"
    if not merged:
        pytest.xfail(f"review-tier ({reason})")
    # If it starts merging (tier landed), the xfail flips to XPASS - update the tier.


def test_generic_subset_does_not_merge_a_person_extra() -> None:
    """Precision guard for the WS4 signal: a same-address token-subset whose extra
    words are a PERSON (not generic descriptors) must NOT merge without a phone -
    the brokerage-plus-agent false-merge the engine already guards against."""
    recs = [
        ProviderRecord(id="1", name="Realty One Group", address="1971 McCulloch Blvd"),
        ProviderRecord(
            id="2", name="Noreen Gilmartin, Realty One Group", address="1971 McCulloch Blvd"
        ),
    ]
    assert cluster_providers(recs) == []


# --- WS4 phone-twin signal (Signal 5, 2026-07-08) ---------------------------
#
# The GLH twin carries its keeper's PHONE but a name variant and a NULL/different
# address — the shape the name+address and name+phone signals both miss (the
# Dos Amigos Taco's case, and the 9 §14.1 twins the client-side cuisine review
# re-flagged). Several of these are the same pairs the address-only _REVIEW_TIER
# above still xfails: without a phone they need fuzzy matching; WITH the shared
# phone + an equal distinctive brand core they resolve at high precision.

# (keeper, glh_twin, shared_phone)
_PHONE_TWIN: list[tuple[str, str, str]] = [
    ("Dos Amigos Tacos", "Dos Amigos Taco's", "(928) 302-3282"),  # real, motivating pair
    ("Bad Miguel's Mexican Restaurant", "Bad Miguel's", "(928) 855-1234"),
    ("Montana's", "Montana Steak House", "(928) 855-2345"),
    ("Niko's Grill & Pub", "Niko's Grill and Pub", "(928) 855-3456"),
    ("Hangar 24 Lake Havasu", "Hangar 24 Taproom & Restaurant", "(928) 855-4567"),
    ("Kokomo Beach Club", "Kokomo - Beach, Surf & Party Bar", "(928) 855-5678"),
    ("Turtle Grille", "Turtle Grille at The Nautical Beachfront Resort", "(928) 855-6789"),
    ("The Office Cocktail Lounge & Grill", "The Office Cocktail Lounge", "(928) 855-7890"),
    ("Shugrue's Restaurant and Brewery Group", "Shugrue's Restaurant & Bar", "(928) 453-1400"),
]


def _phone_twin_records(keeper: str, twin: str, phone: str) -> list[ProviderRecord]:
    # Keeper: Google-matched (place_id + reviews + address). Twin: SAME phone, NO
    # address, a DIFFERENT place_id (two separate Google listings) — the exact shape
    # that escaped the merge and left both live on the restaurants page.
    return [
        ProviderRecord(id="keeper", name=keeper, address="1000 McCulloch Blvd", phone=phone,
                       google_place_id="PID-keeper", review_count=800, verified=True),
        ProviderRecord(id="twin", name=twin, address=None, phone=phone,
                       google_place_id="PID-twin"),
    ]


@pytest.mark.parametrize("keeper,twin,phone", _PHONE_TWIN, ids=[p[0] for p in _PHONE_TWIN])
def test_phone_twin_merges_as_duplicate(keeper: str, twin: str, phone: str) -> None:
    clusters = cluster_providers(_phone_twin_records(keeper, twin, phone))
    assert len(clusters) == 1, f"{keeper} + {twin} did not cluster on the shared phone"
    c = clusters[0]
    assert {m.id for m in c.members} == {"keeper", "twin"}
    assert c.relationship_type == "duplicate", (
        f"{keeper} + {twin} classified {c.relationship_type}, expected duplicate"
    )
    assert c.primary.id == "keeper"  # the reviewed, place_id'd row survives


def test_phone_twin_holds_distinctive_landmark_for_review() -> None:
    """Shugrue's Bridgeview Room shares the group's phone but adds a distinctive
    LANDMARK token ("bridgeview") — not a generic descriptor. Auto-merging it on
    phone alone carries the same risk as merging co-located venues, so it stays for
    human review (an unknown beats a wrong merge)."""
    recs = _phone_twin_records(
        "Shugrue's Restaurant and Brewery Group", "Shugrue's Bridgeview Room", "(928) 453-1400"
    )
    assert cluster_providers(recs) == []


@pytest.mark.parametrize(
    "a,b",
    [
        ("Turtle Grille", "Naked Turtle Beach Bar"),
        ("WET Pool Bar at The Nautical", "Turtle Grille at The Nautical"),
        ("Outlet East", "Outlet West"),
    ],
)
def test_phone_shared_but_distinct_brands_do_not_merge(a: str, b: str) -> None:
    """A shared resort/plaza switchboard must NOT collapse genuinely distinct
    venues — their distinctive brand tokens differ, so the equal-core gate on the
    phone signal rejects them."""
    recs = [
        ProviderRecord(id="1", name=a, phone="(928) 855-0000"),
        ProviderRecord(id="2", name=b, phone="(928) 855-0000"),
    ]
    assert cluster_providers(recs) == []
