"""§2.2 — the seeded daily shuffle + >threshold gate + no-review tail.

Pure-function tests (no DB, no clock): order is deterministic per (category, day),
rotates across days, keeps the rated pool on top, the new/unrated businesses in a
labeled tail (never excluded), and respects the paid cap.
"""

from __future__ import annotations

from app.monetization.serving import (
    ItemRating,
    arrange_listing,
    daily_seed,
    listing_day,
    partition_by_rating,
)


def _items() -> list[ItemRating]:
    return [
        ItemRating("a", 4.8, 120),   # rated pool
        ItemRating("b", 4.1, 5),     # rated pool
        ItemRating("c", 3.5, 30),    # low band (reviews, at/below gate)
        ItemRating("d", None, None),  # new/unrated tail
        ItemRating("e", 4.9, 0),     # 0 reviews → new/unrated tail (rating ignored)
        ItemRating("f", 4.2, 60),    # rated pool
    ]


def test_partition_splits_rated_new_and_low() -> None:
    rated, new_unrated, low = partition_by_rating(_items(), 4.0)
    assert set(rated) == {"a", "b", "f"}
    assert set(new_unrated) == {"d", "e"}
    assert set(low) == {"c"}


def test_threshold_is_strict_greater_than() -> None:
    items = [ItemRating("x", 4.0, 10), ItemRating("y", 4.01, 10)]
    rated, _new, low = partition_by_rating(items, 4.0)
    assert rated == ["y"]
    assert low == ["x"]  # exactly 4.0 is NOT > 4.0


def test_order_is_rated_then_low_then_new_tail() -> None:
    arr = arrange_listing(
        _items(), {}, category_slug="cat", day="2026-06-22", threshold=4.0, cap=3
    )
    # Positions: rated pool first, then the low band, then the new/unrated tail
    # at the very bottom (its own labeled section).
    rated_idx = [arr.order.index(k) for k in ("a", "b", "f")]
    low_idx = arr.order.index("c")
    tail_idx = [arr.order.index(k) for k in ("d", "e")]
    assert max(rated_idx) < low_idx
    assert low_idx < min(tail_idx)
    assert arr.new_unrated == frozenset({"d", "e"})


def test_deterministic_within_a_day_rotates_across_days() -> None:
    a1 = arrange_listing(_items(), {}, category_slug="cat", day="2026-06-22", threshold=4.0, cap=3)
    a2 = arrange_listing(_items(), {}, category_slug="cat", day="2026-06-22", threshold=4.0, cap=3)
    assert a1.order == a2.order  # stable within a day
    # Across a spread of days the rated-pool order is not always identical.
    days = [f"2026-07-{d:02d}" for d in range(1, 15)]
    rated_orders = {
        tuple(
            k
            for k in arrange_listing(
                _items(), {}, category_slug="cat", day=d, threshold=4.0, cap=3
            ).order
            if k in {"a", "b", "f"}
        )
        for d in days
    }
    assert len(rated_orders) > 1


def test_different_categories_get_different_seeds() -> None:
    assert daily_seed("cat-a", "2026-06-22") != daily_seed("cat-b", "2026-06-22")


def test_shuffle_off_preserves_input_order_but_still_pins() -> None:
    arr = arrange_listing(
        _items(),
        {1: "f"},
        category_slug="cat",
        day="2026-06-22",
        threshold=4.0,
        cap=3,
        shuffle=False,
    )
    assert arr.order[0] == "f"             # tier-1 pinned to the top
    assert arr.new_unrated == frozenset()  # no tail labeling when shuffle is off
    # the rest keep their incoming order
    assert arr.order[1:] == ["a", "b", "c", "d", "e"]


def test_tier1_pins_above_the_shuffle() -> None:
    arr = arrange_listing(
        _items(), {1: "c"}, category_slug="cat", day="2026-06-22", threshold=4.0, cap=3
    )
    assert arr.order[0] == "c"
    assert "c" in arr.sponsored


def test_paid_holder_never_labeled_new() -> None:
    # 'd' has no reviews (would be tail) but is sold tier-1 → not in the new tail.
    arr = arrange_listing(
        _items(), {1: "d"}, category_slug="cat", day="2026-06-22", threshold=4.0, cap=3
    )
    assert arr.order[0] == "d"
    assert "d" not in arr.new_unrated
    assert "d" in arr.sponsored


def test_cap_limits_pinned_paid_block() -> None:
    # Five sold tiers but cap=3 → at most 3 paid cards before the first organic.
    many = [ItemRating(k, 4.5, 50) for k in ("p1", "p2", "p3", "p4", "p5")]
    many += [ItemRating(f"o{i}", 4.5, 50) for i in range(6)]
    tiers = {1: "p1", 2: "p2", 3: "p3", 4: "p4", 5: "p5"}
    arr = arrange_listing(
        many, tiers, category_slug="cat", day="2026-06-22", threshold=4.0, cap=3
    )
    # All five remain labeled sponsored...
    assert {"p1", "p2", "p3", "p4", "p5"} <= arr.sponsored
    # ...but only 3 are pinned within the first 3 slots (p4/p5 are not pinned top).
    top3 = set(arr.order[:3])
    assert top3 == {"p1", "p2", "p3"}


def test_cap_holds_even_with_shuffle_off() -> None:
    # The mobile cap must apply on the shuffle-off rollback path too.
    many = [ItemRating(k, 4.5, 50) for k in ("p1", "p2", "p3", "p4", "p5")]
    many += [ItemRating(f"o{i}", 4.5, 50) for i in range(6)]
    tiers = {1: "p1", 2: "p2", 3: "p3", 4: "p4", 5: "p5"}
    arr = arrange_listing(
        many, tiers, category_slug="cat", day="2026-06-22", threshold=4.0, cap=3,
        shuffle=False,
    )
    assert set(arr.order[:3]) == {"p1", "p2", "p3"}  # only 3 pinned
    assert {"p4", "p5"} <= arr.sponsored             # overflow still labeled


def test_listing_day_is_a_date_string() -> None:
    from datetime import datetime

    from app.core.timezone import LAKE_HAVASU_TZ

    d = listing_day(datetime(2026, 6, 22, 15, 0, tzinfo=LAKE_HAVASU_TZ))
    assert d == "2026-06-22"
