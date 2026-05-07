"""
Parser tests for ``app.contrib.webtrac``.

The fixture under ``tests/fixtures/webtrac/adult.html`` is a captured
response from ``register.lhcaz.gov/webtrac/web/search.html?module=AR&category=ADULT``
trimmed to the structural minimum (every ``.result-content`` block kept,
header/footer/JS noise stripped). Tests assert the exact section count
plus a representative record from each parsed program.
"""

from __future__ import annotations

import unittest
from datetime import date, time
from pathlib import Path

from app.contrib.webtrac import (
    Section,
    filter_for_chat,
    parse_search_html,
)


FIXTURE = Path(__file__).parent / "fixtures" / "webtrac" / "adult.html"


def _load() -> list[Section]:
    return parse_search_html(FIXTURE.read_text(encoding="utf-8"))


class ParseSearchHtmlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sections = _load()

    def test_total_section_count(self) -> None:
        # 6 art-and-crafts + 1 dodgeball + 3 kayaking + 1 cooking
        self.assertEqual(len(self.sections), 11)

    def test_program_grouping(self) -> None:
        by_pid = {s.program_id for s in self.sections}
        self.assertEqual(by_pid, {501057, 510077, 303490, 510060})

    def test_fmid_unique_and_nonzero(self) -> None:
        fmids = [s.fmid for s in self.sections]
        self.assertEqual(len(fmids), len(set(fmids)))
        self.assertTrue(all(f > 0 for f in fmids))

    def test_first_art_section_fields(self) -> None:
        first = next(s for s in self.sections if s.fmid == 63751705)
        self.assertEqual(first.program_id, 501057)
        self.assertEqual(first.program_name, "Adult art and crafts")
        self.assertEqual(first.section_name, "Mason jar Terrarium 1-2:30pm")
        self.assertEqual(first.start_date, date(2026, 5, 13))
        self.assertEqual(first.end_date, date(2026, 5, 13))
        self.assertEqual(first.start_time, time(13, 0))
        self.assertEqual(first.end_time, time(14, 30))
        self.assertEqual(first.days, ("W",))
        self.assertEqual(first.location, "Lake Havasu City Parks & Recreation")
        self.assertEqual(first.age_min, 12.0)
        self.assertEqual(first.age_max, 99.99)
        self.assertEqual(first.cost_resident, 8.0)
        self.assertEqual(first.cost_nonresident, 8.0)
        self.assertTrue(first.available_for_signup)
        self.assertEqual(first.availability_state, "available")
        self.assertIn("FMID=63751705", first.info_url)

    def test_kayaking_locations(self) -> None:
        kayaking = [s for s in self.sections if s.program_id == 303490]
        locs = {s.location for s in kayaking}
        self.assertEqual(locs, {"Rotary Park", "Site Six"})

    def test_dodgeball_is_free(self) -> None:
        dodge = next(s for s in self.sections if s.program_id == 510077)
        self.assertEqual(dodge.cost_resident, 0.0)
        self.assertEqual(dodge.cost_nonresident, 0.0)
        self.assertEqual(dodge.days, ("F",))
        self.assertEqual(dodge.start_time, time(18, 30))

    def test_all_available_in_adult_fixture(self) -> None:
        # The Adult fixture happens to contain only Available sections;
        # the chat filter should preserve all of them.
        self.assertEqual(len(filter_for_chat(self.sections)), 11)

    def test_to_dict_is_json_safe(self) -> None:
        import json

        record = self.sections[0].to_dict()
        # round-trip through json — datetimes/dates should already be ISO strings
        s = json.dumps(record)
        self.assertIn("FMID=", json.loads(s)["info_url"])


class ChatFilterTests(unittest.TestCase):
    def test_filter_drops_non_available_states(self) -> None:
        sections = _load()
        # Synthesize an "unavailable" version of one section
        s0 = sections[0]
        unavailable = Section(
            **{**s0.__dict__, "availability_state": "unavailable", "available_for_signup": False}
        )
        mixed = sections + [unavailable]
        kept = filter_for_chat(mixed)
        self.assertEqual(len(kept), 11)  # unavailable one dropped
        self.assertNotIn(unavailable, kept)


if __name__ == "__main__":
    unittest.main()
