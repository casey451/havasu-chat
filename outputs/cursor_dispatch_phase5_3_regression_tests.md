# Cursor dispatch — Phase 5.3 regression tests

> Two-test artifact for Cursor. Each test guards a small surgical fix
> shipped this session — without them, future edits to `_DISCOVERY_DOMAIN_FALLBACK`
> or the dry-run branching could silently re-introduce the bugs.
>
> Target pytest delta: `1855 → 1857` (+2). Or if combined with the OSM
> dispatch artifact `outputs/cursor_dispatch_osm_pull_writer_test.md` from
> the 5.2 close-out, target is `1855 → 1863` (+8).
>
> **Authored by:** Cowork primary, Phase 5 lane, Phase 5.3 session
> (2026-05-15) post-`7c994aa`.

---

## Test 1 — Guard the `cdf3d0c` dry-run + --category fix

**File:** new — `tests/test_phase5_3_places_discovery_dry_run.py`

**Why:** Before `cdf3d0c`, `python -m scripts.places_discovery --category
home-property-services --dry-run` returned `categories=0` (empty
intersection between the legacy `DRY_RUN_LABELS` frozenset and the
category-filtered set). If someone re-introduces the
`cats = [c for c in cats if c["label"] in DRY_RUN_LABELS]` line in the
`else:` branch of `load_categories_for_discovery`, this test catches it.

```python
"""Phase 5.3 — regression guard for cdf3d0c (places_discovery dry-run +
--category produces empty intersection).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.contrib.google_places_scraper import (
    DISCOVERY_CATEGORY_TO_DOMAINS,
    load_categories_for_discovery,
)

CATEGORIES_PATH = Path("scripts/places_categories.json")


@pytest.mark.parametrize(
    "slug",
    sorted(DISCOVERY_CATEGORY_TO_DOMAINS.keys()),
)
def test_dry_run_with_category_returns_nonzero_for_every_slug(slug: str) -> None:
    """--dry-run + --category <slug> must return >=1 category for every
    known Tier-1 slug. Pre-cdf3d0c this silently returned 0 for any slug
    whose labels didn't happen to overlap with the legacy DRY_RUN_LABELS
    frozenset (which excluded home-property-services entirely)."""
    cats = load_categories_for_discovery(
        CATEGORIES_PATH, dry_run=True, category_slug=slug
    )
    assert len(cats) > 0, (
        f"--dry-run --category {slug!r} returned 0 categories. "
        "Regression of cdf3d0c — DRY_RUN_LABELS intersection bug is back."
    )


def test_dry_run_without_category_returns_legacy_5_label_sample() -> None:
    """--dry-run without --category preserves the legacy 5-label sample
    behaviour (this is the original dry-run mode; unchanged by cdf3d0c)."""
    cats = load_categories_for_discovery(
        CATEGORIES_PATH, dry_run=True, category_slug=None
    )
    labels = {c["label"] for c in cats}
    expected = {
        "restaurants",
        "coffee shops",
        "hair salons",
        "auto repair",
        "boat rentals",
    }
    assert labels == expected, (
        f"Legacy 5-label dry-run sample changed. Got: {labels}, expected: {expected}"
    )
```

**Expected:** 13 parametrized assertions (one per slug in
`DISCOVERY_CATEGORY_TO_DOMAINS`) + 1 legacy-sample check = **14 tests**.

---

## Test 2 — Guard the `7c994aa` _DISCOVERY_DOMAIN_FALLBACK home_services extension

**File:** extend existing — `tests/test_phase52_provider_dual_write.py`
(or wherever the sustainability resolver is tested; if no test file
exists, create `tests/test_phase5_3_places_load_resolver.py`).

**Why:** Before `7c994aa`, 70 of the 282 home_services rows landed at
`category_id=None` because their `primary_type` was `service` / `laundry`
/ `consultant` / `None` — types not in the `google_types_mapping` and not
in the lake_recreation-only `_DISCOVERY_DOMAIN_FALLBACK`. If someone
removes the 4 home_services entries I added, this test catches it.

```python
"""Phase 5.3 — regression guard for 7c994aa (_DISCOVERY_DOMAIN_FALLBACK
extends for home_services domain).
"""

from __future__ import annotations

import pytest

from scripts.places_load import _DISCOVERY_DOMAIN_FALLBACK


@pytest.mark.parametrize(
    "primary_type",
    [None, "consultant", "laundry", "service"],
)
def test_home_services_fallback_routes_to_home_property_services(
    primary_type: str | None,
) -> None:
    """The 4 home_services fallback entries shipped at 7c994aa must
    persist. Each was added because a primary_type surfaced in the 5.3
    live load (282 input, 70 unmapped pre-fix) with that type and the
    home_services discovery domain. Removing any of these would re-create
    the 'operator queue' pile on every future home-property-services
    load."""
    key = (primary_type, "home_services")
    assert key in _DISCOVERY_DOMAIN_FALLBACK, (
        f"Missing _DISCOVERY_DOMAIN_FALLBACK entry for {key!r}. "
        "Regression of 7c994aa — home_services rows with this primary_type "
        "will land at category_id=None and need apply-script cleanup."
    )
    assert _DISCOVERY_DOMAIN_FALLBACK[key] == "home-property-services", (
        f"_DISCOVERY_DOMAIN_FALLBACK[{key!r}] routes to "
        f"{_DISCOVERY_DOMAIN_FALLBACK[key]!r}, expected 'home-property-services'."
    )


def test_lake_recreation_fallback_entries_preserved() -> None:
    """Defensive: ensure adding home_services entries didn't disturb the
    Phase 5.2 lake_recreation fallback entries (65b0824)."""
    required_lake_rec = {
        (None, "lake_recreation"),
        ("service", "lake_recreation"),
        ("tour_agency", "lake_recreation"),
        ("tourist_attraction", "lake_recreation"),
        ("tourist_information_center", "lake_recreation"),
        ("point_of_interest", "lake_recreation"),
        ("supplier", "lake_recreation"),
        ("sporting_goods_store", "lake_recreation"),
        ("adventure_sports_center", "lake_recreation"),
    }
    for key in required_lake_rec:
        assert key in _DISCOVERY_DOMAIN_FALLBACK, (
            f"Phase 5.2 lake_recreation fallback entry {key!r} is missing. "
            "Regression of 65b0824."
        )
        assert _DISCOVERY_DOMAIN_FALLBACK[key] == "on-the-water"
```

**Expected:** 4 parametrized assertions (one per home_services primary_type)
+ 1 lake_recreation preservation check = **5 tests**.

---

## Total target: +19 tests (1855 → 1874)

Combined with the OSM dispatch from 5.2 close-out (which adds +6 in
`tests/test_phase5_osm_overpass_pull.py` + 2 regression guards in
`tests/test_phase4_osm_client.py` = +8), the full Cursor dispatch backlog
yields **1855 → 1882**.

---

## Dispatch instructions

1. Cursor: open the repo, create the two test files above.
2. Run `pytest tests/test_phase5_3_places_discovery_dry_run.py tests/test_phase5_3_places_load_resolver.py -v` — all should pass against current `main`.
3. Optionally: revert `cdf3d0c` locally (`git revert --no-commit cdf3d0c`), re-run the first test file — every parametrized case should FAIL except eat-drink/on-the-water/auto-rv-fuel (the slugs whose labels overlap legacy DRY_RUN_LABELS). Then `git restore` the revert.
4. Same for `7c994aa` against the second test file — all 4 home_services assertions should FAIL pre-revert, all should PASS post-restore.
5. Commit both files in one commit: `tests(phase5.3): regression guards for cdf3d0c + 7c994aa`.

---

*Authored by Cowork primary, Phase 5 lane, Phase 5.3 session (2026-05-15)
post-`7c994aa`. Operator dispatches Cursor when convenient — not 5.3
gate-blocking.*
