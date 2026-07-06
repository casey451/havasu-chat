"""T3.3 — mortgage brokers split out of banks into a mortgage-lenders leaf."""

from __future__ import annotations

from app.categories.mortgage_misfiled_rules import classify_mortgage_misfiled_leaf
from scripts.create_mortgage_leaf_2026_07_06 import plan_leaf_action


def test_mortgage_brokers_route_to_mortgage_leaf() -> None:
    for name in (
        "Guild Mortgage Company",
        "loanDepot",
        "Mohave Mortgage - Lake Havasu City",
        "Jason Jackson - PNC Mortgage Loan Officer (NMLS #239510)",
        "AZ LOANS - Lake Havasu City",
        "Mutual Of Omaha Reverse Mortgage",
    ):
        assert classify_mortgage_misfiled_leaf(name) == "mortgage-lenders", name


def test_real_banks_are_left_untouched() -> None:
    for name in ("Wells Fargo Bank", "Arizona Central Credit Union", "Chase Bank", "", None):
        assert classify_mortgage_misfiled_leaf(name) is None, name


def test_create_leaf_planner_insert_noop_abort() -> None:
    dept = {"professional-and-financial": {"id": 30, "level": 0, "parent_id": None}}
    # Department present, leaf absent -> insert.
    assert plan_leaf_action(dict(dept))[0] == "insert"
    # Leaf already correct -> noop.
    with_leaf = dict(dept)
    with_leaf["mortgage-lenders"] = {"id": 200, "level": 1, "parent_id": 30}
    assert plan_leaf_action(with_leaf)[0] == "noop"
    # Leaf exists under the wrong parent -> abort (refuse to mutate).
    wrong = dict(dept)
    wrong["mortgage-lenders"] = {"id": 200, "level": 1, "parent_id": 99}
    assert plan_leaf_action(wrong)[0] == "abort"
    # Missing department -> abort.
    assert plan_leaf_action({})[0] == "abort"
