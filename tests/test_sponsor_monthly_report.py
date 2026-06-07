"""Monthly sponsor report (HANDOFF #4) — read-only, dry-run default."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.db.database import SessionLocal
from app.db.models import AnalyticsEvent, Sponsor
from scripts import sponsor_monthly_report as smr


@pytest.fixture
def db():
    created_sponsors: list[str] = []
    created_events: list[str] = []
    with SessionLocal() as session:
        yield session, created_sponsors, created_events
        if created_events:
            session.query(AnalyticsEvent).filter(
                AnalyticsEvent.id.in_(created_events)
            ).delete(synchronize_session=False)
        if created_sponsors:
            session.query(Sponsor).filter(Sponsor.id.in_(created_sponsors)).delete(
                synchronize_session=False
            )
        session.commit()


def _add_sponsor(db, *, name, slot, starts, ends) -> str:
    session, created_sponsors, _ = db
    sp = Sponsor(name=name, cta_url="https://x.test", slot=slot, starts_at=starts, ends_at=ends)
    session.add(sp)
    session.commit()
    created_sponsors.append(sp.id)
    return sp.id


def _add_event(db, *, sponsor_id, event_name, slot, when) -> None:
    session, _, created_events = db
    ev = AnalyticsEvent(event_name=event_name, slot=slot, sponsor_id=sponsor_id, created_at=when)
    session.add(ev)
    session.commit()
    created_events.append(ev.id)


# --- pure date helpers ------------------------------------------------------


def test_month_bounds_mid_year():
    start, end = smr.month_bounds(2026, 5)
    assert start == datetime(2026, 5, 1)
    assert end == datetime(2026, 6, 1)


def test_month_bounds_december_rolls_year():
    start, end = smr.month_bounds(2026, 12)
    assert start == datetime(2026, 12, 1)
    assert end == datetime(2027, 1, 1)


def test_prior_month_january_rolls_back():
    assert smr.prior_month(datetime(2026, 1, 9)) == (2025, 12)
    assert smr.prior_month(datetime(2026, 6, 6)) == (2026, 5)


# --- gather_report ----------------------------------------------------------


def test_spotlight_impressions_and_clicks_with_prior(db):
    session, *_ = db
    sid = _add_sponsor(
        db,
        name="Acme",
        slot="spotlight",
        starts=datetime(2026, 4, 1, tzinfo=UTC),
        ends=datetime(2026, 7, 1, tzinfo=UTC),
    )
    # May (report month): 2 impressions, 1 click.
    _add_event(db, sponsor_id=sid, event_name="home.spotlight.impression", slot="spotlight", when=datetime(2026, 5, 10))
    _add_event(db, sponsor_id=sid, event_name="home.spotlight.impression", slot="spotlight", when=datetime(2026, 5, 12))
    _add_event(db, sponsor_id=sid, event_name="home.sponsor.click", slot="spotlight", when=datetime(2026, 5, 12))
    # April (prior): 1 impression, 0 clicks.
    _add_event(db, sponsor_id=sid, event_name="home.spotlight.impression", slot="spotlight", when=datetime(2026, 4, 9))

    report = smr.gather_report(session, 2026, 5)
    row = next(r for r in report.rows if r.sponsor_id == sid)
    assert row.impressions == 2
    assert row.clicks == 1
    assert row.prev_impressions == 1
    assert row.ctr == pytest.approx(0.5)


def test_non_spotlight_tier_clicks_only_ctr_none(db):
    session, *_ = db
    sid = _add_sponsor(
        db, name="MarqueeCo", slot="marquee",
        starts=datetime(2026, 4, 1, tzinfo=UTC), ends=None,
    )
    _add_event(db, sponsor_id=sid, event_name="home.sponsor.click", slot="marquee", when=datetime(2026, 5, 5))
    report = smr.gather_report(session, 2026, 5)
    row = next(r for r in report.rows if r.sponsor_id == sid)
    assert row.clicks == 1
    assert row.impressions == 0
    assert row.ctr is None


def test_sponsor_outside_window_excluded(db):
    session, *_ = db
    sid = _add_sponsor(
        db, name="OldCo", slot="spotlight",
        starts=datetime(2026, 1, 1, tzinfo=UTC), ends=datetime(2026, 2, 1, tzinfo=UTC),
    )
    report = smr.gather_report(session, 2026, 5)
    assert all(r.sponsor_id != sid for r in report.rows)


def test_click_outside_window_not_counted(db):
    session, *_ = db
    sid = _add_sponsor(
        db, name="EdgeCo", slot="spotlight",
        starts=datetime(2026, 4, 1, tzinfo=UTC), ends=None,
    )
    # June click must not land in the May report.
    _add_event(db, sponsor_id=sid, event_name="home.sponsor.click", slot="spotlight", when=datetime(2026, 6, 1))
    report = smr.gather_report(session, 2026, 5)
    row = next(r for r in report.rows if r.sponsor_id == sid)
    assert row.clicks == 0


# --- rendering --------------------------------------------------------------


def test_render_marks_uninstrumented_ctr_na(db):
    session, *_ = db
    sid = _add_sponsor(
        db, name="PromoCo", slot="promoted",
        starts=datetime(2026, 4, 1, tzinfo=UTC), ends=None,
    )
    _add_event(db, sponsor_id=sid, event_name="home.sponsor.click", slot="promoted", when=datetime(2026, 5, 5))
    report = smr.gather_report(session, 2026, 5)
    text = smr.render_text(report)
    html = smr.render_html(report)
    assert "PromoCo" in text and "PromoCo" in html
    assert "n/a" in text  # CTR n/a for the uninstrumented tier


# --- CLI --------------------------------------------------------------------


def test_dry_run_prints_and_does_not_send(capsys):
    with patch("app.auth.email_sender.send_alert_email") as send:
        rc = smr.main(["--month", "2026-05"])
    assert rc == 0
    send.assert_not_called()
    assert "sponsor report" in capsys.readouterr().out.lower()


def test_execute_requires_recipient(monkeypatch):
    monkeypatch.delenv("REPORT_RECIPIENT", raising=False)
    rc = smr.main(["--month", "2026-05", "--execute"])
    assert rc == 2


def test_execute_sends_with_recipient(monkeypatch):
    monkeypatch.setenv("REPORT_RECIPIENT", "casey@example.com")
    with patch("app.auth.email_sender.send_alert_email") as send:
        rc = smr.main(["--month", "2026-05", "--execute"])
    assert rc == 0
    send.assert_called_once()
    assert send.call_args.kwargs["to_email"] == "casey@example.com"


def test_bad_month_arg_returns_2():
    assert smr.main(["--month", "nonsense"]) == 2
