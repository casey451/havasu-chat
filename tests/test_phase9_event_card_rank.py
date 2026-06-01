"""Phase 9b — compute_event_card_rank + _cap_event_share."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.core.ranking import _cap_event_share, compute_event_card_rank
from app.providers.view_models import HavaCardViewModel


def _event(**kwargs) -> SimpleNamespace:
    featured = kwargs.pop("featured", False)
    return SimpleNamespace(featured=featured, **kwargs)


def test_imminence_today_beats_next_week() -> None:
    today = date(2026, 6, 1)
    ev = _event()
    today_score = compute_event_card_rank(event=ev, occurrence_date=today, today=today)
    next_week = compute_event_card_rank(
        event=ev,
        occurrence_date=today + __import__("datetime").timedelta(days=14),
        today=today,
    )
    assert today_score > next_week


def test_tomorrow_boost_between_today_and_later() -> None:
    today = date(2026, 6, 1)
    ev = _event()
    tomorrow = compute_event_card_rank(event=ev, occurrence_date=date(2026, 6, 2), today=today)
    later = compute_event_card_rank(event=ev, occurrence_date=date(2026, 6, 20), today=today)
    assert tomorrow > later


def test_heat_bias_indoor_boost() -> None:
    today = date(2026, 6, 1)
    ev = _event()
    hot = compute_event_card_rank(
        event=ev,
        occurrence_date=today,
        now_temp_f=105.0,
        venue_heat_exposure="indoor",
        today=today,
    )
    mild = compute_event_card_rank(
        event=ev,
        occurrence_date=today,
        now_temp_f=85.0,
        venue_heat_exposure="indoor",
        today=today,
    )
    assert hot > mild


def test_boat_mode_boost() -> None:
    today = date(2026, 6, 1)
    ev = _event()
    with_boat = compute_event_card_rank(
        event=ev,
        occurrence_date=today,
        user_in_boat_mode=True,
        venue_boat_access=True,
        today=today,
    )
    without = compute_event_card_rank(
        event=ev,
        occurrence_date=today,
        user_in_boat_mode=False,
        venue_boat_access=True,
        today=today,
    )
    assert with_boat > without


def test_featured_boost() -> None:
    today = date(2026, 6, 1)
    featured = compute_event_card_rank(
        event=_event(featured=True), occurrence_date=today, today=today
    )
    plain = compute_event_card_rank(
        event=_event(featured=False), occurrence_date=today, today=today
    )
    assert featured > plain


def _vm(et: str) -> HavaCardViewModel:
    return HavaCardViewModel(
        entity_id="x",
        entity_type=et,
        name="n",
        profile_url="/p",
        hero_photo_url=None,
        category_slug="events",
        category_label="Events",
        district_slug="",
        district_name="",
        status_line_text="",
        status_line_color="blue",
        freshness_band="green",
        is_sponsored=False,
        boat_access_badge=False,
        heat_exposure_pill=None,
    )


def test_cap_event_share_40_percent() -> None:
    cards = [(_vm("event"), 2.0) for _ in range(10)] + [(_vm("commercial"), 1.0) for _ in range(10)]
    capped = _cap_event_share(cards, max_event_pct=0.40, limit=20)
    event_n = sum(1 for vm, _ in capped if vm.entity_type == "event")
    assert event_n <= 8
    assert len(capped) <= 20
