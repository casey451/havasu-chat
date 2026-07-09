"""T1.4 — coalesce contradictory hours segments (2026-07-06).

A cross-midnight Google period that closes at exactly 00:00 (e.g. Fri 09:00 →
Sat 00:00) split into a Friday ``09:00-23:59`` span plus a zero-length Saturday
``00:00-00:00`` tail. The profile template misread that tail as "Open 24 hours",
colliding with the real span → "Open 24 hours, 9 AM–Midnight".

Two fixes, both covered here:
  * the source splitter (``places_hours_to_structured``) no longer emits the
    zero-length tail, so NEW rows are clean; and
  * ``effective_hours_structured`` coalesces per-weekday spans on read, repairing
    rows whose ``hours_structured`` column already baked in the artifact.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.contrib.hours_helper import places_hours_to_structured
from app.providers import queries
from app.providers.queries import _coalesce_day_segments

# --- unit: the per-day coalescer ---------------------------------------------


def test_zero_length_midnight_tail_is_dropped() -> None:
    assert _coalesce_day_segments(
        [{"open": "00:00", "close": "00:00"}, {"open": "09:00", "close": "23:59"}]
    ) == [{"open": "09:00", "close": "23:59"}]


def test_genuine_24h_span_is_preserved() -> None:
    # 00:00-23:59 is the real "open 24 hours" representation and must survive.
    assert _coalesce_day_segments([{"open": "00:00", "close": "23:59"}]) == [
        {"open": "00:00", "close": "23:59"}
    ]


def test_overlapping_and_adjacent_segments_merge() -> None:
    assert _coalesce_day_segments(
        [{"open": "09:00", "close": "17:00"}, {"open": "12:00", "close": "20:00"}]
    ) == [{"open": "09:00", "close": "20:00"}]
    # adjacency (touch at 12:00) merges into one continuous span
    assert _coalesce_day_segments(
        [{"open": "09:00", "close": "12:00"}, {"open": "12:00", "close": "17:00"}]
    ) == [{"open": "09:00", "close": "17:00"}]


def test_contained_segment_is_absorbed() -> None:
    assert _coalesce_day_segments(
        [{"open": "08:00", "close": "22:00"}, {"open": "10:00", "close": "12:00"}]
    ) == [{"open": "08:00", "close": "22:00"}]


def test_disjoint_split_shift_is_kept() -> None:
    # A real lunch-break split (gap between segments) is preserved, not merged.
    assert _coalesce_day_segments(
        [{"open": "09:00", "close": "12:00"}, {"open": "13:00", "close": "17:00"}]
    ) == [{"open": "09:00", "close": "12:00"}, {"open": "13:00", "close": "17:00"}]


def test_close_at_midnight_is_end_of_day_not_zero() -> None:
    # An open segment that closes at 00:00 (midnight) is end-of-day, rendered via
    # the 23:59 clamp so is_open + the "Midnight" label keep working.
    assert _coalesce_day_segments([{"open": "20:00", "close": "00:00"}]) == [
        {"open": "20:00", "close": "23:59"}
    ]


# --- source splitter: no more zero-length overnight tails ---------------------


def _period(od, oh, cd, ch):
    return {"open": {"day": od, "hour": oh, "minute": 0}, "close": {"day": cd, "hour": ch, "minute": 0}}


def test_splitter_drops_close_at_exact_midnight_tail() -> None:
    # Fri (day 5) 09:00 -> Sat (day 6) 00:00: Friday 09:00-23:59, NO Saturday tail.
    out = places_hours_to_structured({"periods": [_period(5, 9, 6, 0)]})
    assert out.get("friday") == [{"open": "09:00", "close": "23:59"}]
    assert out.get("saturday") in (None, [])


def test_splitter_keeps_real_overnight_tail() -> None:
    # Fri 20:00 -> Sat 02:00: Friday 20:00-23:59 + a real Saturday 00:00-02:00.
    out = places_hours_to_structured({"periods": [_period(5, 20, 6, 2)]})
    assert out.get("friday") == [{"open": "20:00", "close": "23:59"}]
    assert out.get("saturday") == [{"open": "00:00", "close": "02:00"}]


# --- integration: repair a stored hours_structured column on read -------------


def test_effective_hours_repairs_stored_golf_n_brews_artifact() -> None:
    # The live Golf N' Brews row's hours_structured column carries the baked-in
    # zero-length tails; effective_hours_structured must return clean spans.
    stored = {
        "saturday": [{"open": "00:00", "close": "00:00"}, {"open": "09:00", "close": "23:59"}],
        "sunday": [{"open": "09:00", "close": "22:00"}, {"open": "00:00", "close": "00:00"}],
        "friday": [{"open": "09:00", "close": "23:59"}],
    }
    prov = SimpleNamespace(entity=None, hours_structured=stored, google_hours=None, id=None)
    eff = queries.effective_hours_structured(prov)  # type: ignore[arg-type]
    assert eff is not None
    assert eff["saturday"] == [{"open": "09:00", "close": "23:59"}]
    assert eff["sunday"] == [{"open": "09:00", "close": "22:00"}]
    assert eff["friday"] == [{"open": "09:00", "close": "23:59"}]
