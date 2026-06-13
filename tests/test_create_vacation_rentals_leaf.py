"""Unit tests for scripts/create_vacation_rentals_leaf.plan_leaf_action.

Phase 4 (2026-06-12): the leaf-creation planner is pure (no DB), so these lock
the insert / noop / abort decisions. The gated ``run()`` is dry-run by default
and exercised against the live DB during the approved apply.
"""

from __future__ import annotations

from scripts.create_vacation_rentals_leaf import (
    LODGING_DEPT_SLUG,
    NEW_LEAF_SLUG,
    plan_leaf_action,
)


def _lodging(id_: int = 33) -> dict[str, dict]:
    return {LODGING_DEPT_SLUG: {"id": id_, "level": 0, "parent_id": None}}


def test_inserts_when_leaf_missing() -> None:
    action, _ = plan_leaf_action(_lodging())
    assert action == "insert"


def test_noop_when_leaf_already_correct() -> None:
    cats = _lodging()
    cats[NEW_LEAF_SLUG] = {"id": 200, "level": 1, "parent_id": 33}
    action, msg = plan_leaf_action(cats)
    assert action == "noop", msg


def test_aborts_when_lodging_department_missing() -> None:
    action, msg = plan_leaf_action({})
    assert action == "abort"
    assert LODGING_DEPT_SLUG in msg


def test_aborts_when_lodging_slug_is_not_level_zero() -> None:
    # A stray non-department row holding the slug must not be used as a parent.
    action, _ = plan_leaf_action({LODGING_DEPT_SLUG: {"id": 33, "level": 1, "parent_id": 9}})
    assert action == "abort"


def test_aborts_when_leaf_exists_with_wrong_parent() -> None:
    cats = _lodging()
    cats[NEW_LEAF_SLUG] = {"id": 200, "level": 1, "parent_id": 99}  # wrong dept
    action, msg = plan_leaf_action(cats)
    assert action == "abort"
    assert NEW_LEAF_SLUG in msg


def test_aborts_when_leaf_exists_as_department() -> None:
    cats = _lodging()
    cats[NEW_LEAF_SLUG] = {"id": 200, "level": 0, "parent_id": None}
    action, _ = plan_leaf_action(cats)
    assert action == "abort"
