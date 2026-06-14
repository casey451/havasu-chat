"""Phase F §7.2 sticky-tier ranking + §7.1 homepage rotation (pure logic)."""

from __future__ import annotations

import random

from app.monetization.serving import (
    RankedItem,
    apply_category_order,
    arrange_top5,
    pick_homepage,
)


def _pos(out: list[RankedItem], key: str) -> int:
    return next(i for i, it in enumerate(out) if it.key == key)


def test_tier1_always_position_1() -> None:
    for seed in range(25):
        out = arrange_top5({1: "A"}, [f"u{i}" for i in range(8)], random.Random(seed))
        assert out[0].key == "A"
        assert out[0].paid_tier == 1


def test_tier3_guaranteed_within_top3() -> None:
    for seed in range(40):
        out = arrange_top5({3: "C"}, [f"u{i}" for i in range(10)], random.Random(seed))
        assert _pos(out, "C") < 3


def test_tier1_locked_and_tier3_floats_in_band() -> None:
    for seed in range(40):
        out = arrange_top5({1: "A", 3: "C"}, [f"u{i}" for i in range(10)], random.Random(seed))
        assert out[0].key == "A"
        c = _pos(out, "C")
        assert 1 <= c < 3  # within top-3 but never position 1 (locked by tier 1)


def test_tier5_guaranteed_within_top5() -> None:
    for seed in range(40):
        out = arrange_top5({5: "E"}, [f"u{i}" for i in range(12)], random.Random(seed))
        assert _pos(out, "E") < 5


def test_completeness_no_duplicates() -> None:
    unpaid = [f"u{i}" for i in range(7)]
    out = arrange_top5({1: "A", 5: "E"}, unpaid, random.Random(3))
    keys = [it.key for it in out]
    assert len(keys) == len(set(keys))               # no dupes
    assert set(keys) == set(unpaid) | {"A", "E"}      # everyone present, once


def test_no_placements_is_just_shuffled_pool() -> None:
    unpaid = [f"u{i}" for i in range(5)]
    out = arrange_top5({}, unpaid, random.Random(1))
    assert {it.key for it in out} == set(unpaid)
    assert all(it.paid_tier is None for it in out)


def test_homepage_pick() -> None:
    assert pick_homepage([], random.Random(1)) is None
    assert pick_homepage(["a", "b", "c"], random.Random(1)) in {"a", "b", "c"}


# --- apply_category_order: overlay that PRESERVES organic order for unpaid ---


def test_overlay_dormant_when_nothing_sold() -> None:
    organic = ["a", "b", "c", "d"]
    assert apply_category_order(organic, {}) == organic


def test_overlay_tier1_pins_front_rest_keep_organic_order() -> None:
    organic = ["a", "b", "c", "d", "e", "f"]
    out = apply_category_order(organic, {1: "d"}, random.Random(0))
    assert out[0] == "d"                       # paid #1 pinned to front
    assert out[1:] == ["a", "b", "c", "e", "f"]  # rest stay in organic order


def test_overlay_tier3_within_top3_rest_organic() -> None:
    organic = [f"p{i}" for i in range(8)]
    for seed in range(20):
        out = apply_category_order(organic, {3: "p5"}, random.Random(seed))
        assert out.index("p5") < 3
        # unpaid keep relative organic order
        rest = [k for k in out if k != "p5"]
        assert rest == [k for k in organic if k != "p5"]


def test_overlay_completeness() -> None:
    organic = [f"p{i}" for i in range(6)]
    out = apply_category_order(organic, {1: "p2", 5: "p4"}, random.Random(2))
    assert sorted(out) == sorted(organic)
    assert len(out) == len(set(out))
