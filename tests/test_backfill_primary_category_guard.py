"""Guard tests for scripts/backfill_primary_category.py (manual-assignment guard).

The backfill must never overwrite a manually assigned ``primary_category`` with
NULL when derivation has no signal. Regression for the 2026-06-04 manual
classification pass (52 signal-less rows assigned by hand).
"""

from __future__ import annotations

import pytest

from scripts.backfill_primary_category import should_write


@pytest.mark.parametrize(
    ("derived", "current", "expected"),
    [
        # The guard: no derivation signal + manual value present -> never write.
        (None, "outdoors-parks-trails", False),
        (None, "professional-services", False),
        # No signal, nothing stored -> nothing to change.
        (None, None, False),
        # Normal backfill behavior is unchanged.
        ("eat-drink", None, True),                      # fill missing
        ("eat-drink", "on-the-water", True),            # correct drifted value
        ("eat-drink", "eat-drink", False),              # already correct
    ],
)
def test_should_write(derived: str | None, current: str | None, expected: bool) -> None:
    assert should_write(derived, current) is expected


def test_guard_is_asymmetric() -> None:
    """A real derivation may overwrite anything; only None is fenced."""
    assert should_write("events", "professional-services") is True
    assert should_write(None, "events") is False
