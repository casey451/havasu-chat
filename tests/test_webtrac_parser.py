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


# --- Confirmed against live data 2026-05-07: Vermont Systems uses
# `itemstatus--available`, `itemstatus--unavailable`, `itemstatus--full`.
# Other plausible states (waitlist, cancelled) haven't been observed yet
# but the parser handles any non-"available" state generically.

_NON_AVAILABLE_HTML = """
<html><body>
<div class="result-content">
  <div class="header result-header"><div class="result-header__info">
    <h2><span>Basketball</span> - <em>161601</em></h2>
    <div class="result-header__count">2 Sections</div>
  </div></div>
  <table class="table"><tbody>
    <tr>
      <td class="button-cell button-cell--cart"><a class="button cart-button" href="?ARFMIDList=9435142">Add</a></td>
      <td class="label-cell" data-title="Availability"><span class="nowrap itemstatus itemstatus--unavailable">Unavailable</span></td>
      <td class="label-cell" data-title="Description"><a href="https://register.lhcaz.gov/webtrac/web/iteminfo.html?Module=AR&FMID=9435142">Jr. Suns Basketball 10-12 year olds</a></td>
      <td class="label-cell" data-title="Dates"><span class="nowrap">05/12/2026</span> -<span class="nowrap">07/16/2026</span></td>
      <td class="label-cell" data-title="Times"><span class="nowrap"> 5:00 pm</span> -<span class="nowrap"> 8:00 pm</span></td>
      <td class="label-cell" data-title="Days">M, Tu, W, Th</td>
      <td class="label-cell" data-title="Location">Lake Havasu City Parks &amp; Recreation</td>
      <td class="label-cell" data-title="Ages">10-12.99</td>
      <td class="label-cell" data-title="Cost">$50.00/$50.00</td>
    </tr>
    <tr>
      <td class="button-cell button-cell--cart"><a class="button cart-button" href="?ARFMIDList=9435200">Add</a></td>
      <td class="label-cell" data-title="Availability"><span class="nowrap itemstatus itemstatus--full">Full</span></td>
      <td class="label-cell" data-title="Description"><a href="https://register.lhcaz.gov/webtrac/web/iteminfo.html?Module=AR&FMID=9435200">Jr. Suns Basketball 7-9 year olds</a></td>
      <td class="label-cell" data-title="Dates"><span class="nowrap">05/12/2026</span> -<span class="nowrap">07/16/2026</span></td>
      <td class="label-cell" data-title="Times"><span class="nowrap"> 5:30 pm</span> -<span class="nowrap"> 8:30 pm</span></td>
      <td class="label-cell" data-title="Days">M, Tu, W, Th</td>
      <td class="label-cell" data-title="Location">Various Locations</td>
      <td class="label-cell" data-title="Ages">7-9.99</td>
      <td class="label-cell" data-title="Cost">$50.00/$50.00</td>
    </tr>
  </tbody></table>
</div>
</body></html>
"""


class NonAvailableStateTests(unittest.TestCase):
    """Confirms the parser correctly maps the live Vermont Systems CSS
    suffixes for non-bookable sections."""

    def setUp(self) -> None:
        from app.contrib.webtrac import parse_search_html

        self.sections = parse_search_html(_NON_AVAILABLE_HTML)

    def test_two_sections_parsed(self) -> None:
        self.assertEqual(len(self.sections), 2)

    def test_unavailable_state(self) -> None:
        s = next(x for x in self.sections if x.fmid == 9435142)
        self.assertEqual(s.availability_state, "unavailable")
        self.assertEqual(s.availability_label, "Unavailable")
        self.assertFalse(s.available_for_signup)

    def test_full_state(self) -> None:
        s = next(x for x in self.sections if x.fmid == 9435200)
        self.assertEqual(s.availability_state, "full")
        self.assertEqual(s.availability_label, "Full")
        self.assertFalse(s.available_for_signup)

    def test_filter_drops_both(self) -> None:
        from app.contrib.webtrac import filter_for_chat

        self.assertEqual(filter_for_chat(self.sections), [])

    def test_basketball_recurring_pattern(self) -> None:
        # The full Basketball section spans a real date range with a
        # multi-day weekly pattern — exercises the loader's
        # _webtrac_is_recurring branch.
        s = next(x for x in self.sections if x.fmid == 9435142)
        self.assertNotEqual(s.start_date, s.end_date)
        self.assertEqual(s.days, ("M", "Tu", "W", "Th"))


if __name__ == "__main__":
    unittest.main()
