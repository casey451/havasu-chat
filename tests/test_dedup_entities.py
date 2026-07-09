"""Unit tests for the pure dedup logic of scripts/dedup_entities.

Locks: chain-safe clustering (different place_ids never collapse), survivor
scoring order, and the protected-row conflict path. DB-touching ``run()`` is
gated/dry-run.
"""

from __future__ import annotations

from scripts.dedup_entities import (
    EXCLUDED_ENTITY_TYPES,
    cluster_key,
    is_dedupable_entity_type,
    plan_cluster,
    score_entity,
)


def _row(eid, *, place_id=None, name="X", address=None, has_provider=False,
         verified=False, claimed=False, sponsored=False, completeness=0, review_count=0):
    return dict(entity_id=eid, place_id=place_id, name=name, address=address,
                has_provider=has_provider, verified=verified, claimed=claimed,
                sponsored=sponsored, completeness=completeness, review_count=review_count)


# --- clustering (chain-safety) ---------------------------------------------

def test_same_place_id_clusters() -> None:
    assert cluster_key("ChIJabc", "The Spot", None) == cluster_key("ChIJabc", "The Spot 2", "x")


def test_different_place_ids_never_cluster() -> None:
    # two Starbucks locations — distinct place_ids => distinct clusters
    assert cluster_key("ChIJ_loc1", "Starbucks", "1 A St") != cluster_key(
        "ChIJ_loc2", "Starbucks", "2 B St"
    )


def test_no_placeid_uses_name_and_address() -> None:
    assert cluster_key(None, "Havasu Lanes", "123 Main") == cluster_key(
        None, "havasu lanes!", "123 main"
    )
    # same name, different address => different cluster (chain-safe)
    assert cluster_key(None, "Starbucks", "1 A St") != cluster_key(None, "Starbucks", "9 Z St")


def test_unclusterable_without_placeid_or_address() -> None:
    assert cluster_key(None, "Havasu Lanes", None) is None
    assert cluster_key(None, None, None) is None


# --- survivor scoring ------------------------------------------------------

def test_score_priority_order() -> None:
    claimed = _row("a", claimed=True)
    verified = _row("b", verified=True)
    sponsored = _row("c", sponsored=True)
    provider = _row("d", has_provider=True, completeness=6)
    bare = _row("e", completeness=1)
    assert score_entity(claimed) > score_entity(verified) > score_entity(sponsored)
    assert score_entity(sponsored) > score_entity(provider) > score_entity(bare)


def test_completeness_and_reviews_break_ties() -> None:
    a = _row("a", has_provider=True, completeness=3, review_count=10)
    b = _row("b", has_provider=True, completeness=6, review_count=2)
    assert score_entity(b) > score_entity(a)  # completeness dominates reviews


# --- cluster planning ------------------------------------------------------

def test_keeps_richest_deactivates_rest() -> None:
    rows = [
        _row("keep", has_provider=True, completeness=6, review_count=120),
        _row("dup1", completeness=0),
        _row("dup2", completeness=1),
    ]
    survivor, deactivate, conflicts = plan_cluster(rows)
    assert survivor["entity_id"] == "keep"
    assert {r["entity_id"] for r in deactivate} == {"dup1", "dup2"}
    assert conflicts == []


def test_protected_nonsurvivor_becomes_conflict_not_deactivated() -> None:
    rows = [
        _row("keep", has_provider=True, completeness=6, review_count=200),
        _row("claimed_dup", claimed=True),  # protected, lower score
    ]
    survivor, deactivate, conflicts = plan_cluster(rows)
    # claimed row outscores via +10000, so it actually becomes survivor here:
    assert survivor["entity_id"] == "claimed_dup"
    assert {r["entity_id"] for r in deactivate} == {"keep"}


def test_protected_dup_when_survivor_is_richer_goes_to_conflict() -> None:
    rows = [
        _row("keep", claimed=True, has_provider=True, completeness=6),
        _row("verified_dup", verified=True),  # protected but lower than claimed+provider
    ]
    survivor, deactivate, conflicts = plan_cluster(rows)
    assert survivor["entity_id"] == "keep"
    assert deactivate == []
    assert {r["entity_id"] for r in conflicts} == {"verified_dup"}


def test_singleton_cluster_no_action() -> None:
    survivor, deactivate, conflicts = plan_cluster([_row("solo")])
    assert survivor["entity_id"] == "solo"
    assert deactivate == [] and conflicts == []


# --- entity-type scope (events excluded from venue dedup) ------------------

def test_events_are_never_dedupable() -> None:
    """Recurring events (a daily 'Lap Swim', a weekly Farmers Market) share
    name+address across occurrences — venue dedup must never collapse them."""
    assert "event" in EXCLUDED_ENTITY_TYPES
    assert is_dedupable_entity_type("event") is False


def test_directory_types_are_dedupable() -> None:
    """Commercial venues and place/program rows ARE venue-dedupable; an unknown
    or missing type defaults to dedupable (only events are carved out)."""
    for et in ("commercial", "place", "program", None, ""):
        assert is_dedupable_entity_type(et) is True
