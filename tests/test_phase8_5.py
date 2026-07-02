"""Phase 8.5 — search & intent architecture rewrite (slots-only coverage).

Legacy deterministic intent + ``app.core.search`` pipeline tests were removed
at Slice 71 (Backlog #36 Option A).
"""

from __future__ import annotations

import unittest

from app.core.slots import extract_date_range


class Phase85SlotTests(unittest.TestCase):
    def test_weekend_and_next_week_both_extract(self) -> None:
        # (merge_date_range died with the Track-A slot machinery 2026-07-02;
        # last-mention-wins now happens at the intent layer.)
        assert extract_date_range("this weekend")
        assert extract_date_range("next week")

    def test_first_friday_does_not_set_next_friday_date_range(self) -> None:
        self.assertIsNone(extract_date_range("first friday"))


if __name__ == "__main__":
    unittest.main()
