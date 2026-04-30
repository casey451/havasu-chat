"""Tests for ``scripts/backfill_river_scene_urls.py`` (rescrape backfill)."""

from __future__ import annotations

import importlib.util
import io
import sys
import uuid
from contextlib import redirect_stdout
from datetime import date, time
from pathlib import Path
from unittest.mock import patch

import pytest
from app.contrib.river_scene import RiverSceneEvent, normalize_to_contribution
from app.db.database import SessionLocal
from app.db.models import Contribution, Event

ROOT = Path(__file__).resolve().parents[1]

U_CHANGE = "https://riverscenemagazine.com/e/change-case"
U_MATCH = "https://riverscenemagazine.com/e/match-case"
U_NOORG = "https://riverscenemagazine.com/e/noorg-case"
U_FAIL = "https://riverscenemagazine.com/e/fail-case"


def _rse(*, url: str, labels: dict | None = None) -> RiverSceneEvent:
    return RiverSceneEvent(
        title="RS Test Event",
        url=url,
        start_date=date(2026, 7, 4),
        end_date=date(2026, 7, 4),
        start_time=time(10, 0),
        end_time=time(20, 0),
        description_html="<p>Enough body text for submission notes to exceed minimal length checks.</p>",
        venue_name="Venue Hall",
        venue_address=None,
        organizer=None,
        category_slugs=["music"],
        raw={"labels": labels if labels is not None else {}},
    )


@pytest.fixture(scope="module")
def backfill_mod():
    path = ROOT / "scripts" / "backfill_river_scene_urls.py"
    spec = importlib.util.spec_from_file_location("backfill_river_scene_urls", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _wipe_contributions_and_events() -> None:
    with SessionLocal() as db:
        db.query(Contribution).delete()
        db.query(Event).delete()
        db.commit()


def _payload_triplet(backfill_mod, rse: RiverSceneEvent) -> tuple[str, str, str]:
    return backfill_mod._payload_targets(normalize_to_contribution(rse))


def _add_event_contribution(
    *,
    article_url: str,
    event_url: str,
    description: str,
    source_url: str | None,
    with_contribution: bool = True,
) -> str:
    eid = str(uuid.uuid4())
    with SessionLocal() as db:
        ev = Event(
            id=eid,
            title="RS Test",
            normalized_title="rs test",
            date=date(2026, 7, 4),
            end_date=None,
            start_time=time(10, 0),
            end_time=None,
            location_name="Havasu",
            location_normalized="havasu",
            description=description,
            event_url=event_url,
            source_url=source_url,
            source="river_scene_import",
        )
        db.add(ev)
        if with_contribution:
            db.add(
                Contribution(
                    entity_type="event",
                    submission_name="RS Test",
                    submission_url=article_url,
                    source_url=source_url,
                    submission_notes=description,
                    event_date=date(2026, 7, 4),
                    event_end_date=None,
                    event_time_start=time(10, 0),
                    event_time_end=None,
                    source="river_scene_import",
                    status="approved",
                    created_event_id=eid,
                )
            )
        db.commit()
    return eid


def _fetch_router():
    """Return fetch_and_parse_event mock keyed by article URL."""

    def _fetch(url: str, client=None, today=None):
        if U_FAIL in url:
            raise ConnectionError("simulated fetch failure")
        if U_CHANGE in url:
            return _rse(url=U_CHANGE, labels={"Website": "https://organizer-change.example/out"})
        if U_MATCH in url:
            return _rse(url=U_MATCH, labels={"Website": "https://organizer-match.example/same"})
        if U_NOORG in url:
            return _rse(url=U_NOORG, labels={})
        raise AssertionError(f"unexpected fetch url {url!r}")

    return _fetch


def test_parse_args_rejects_dry_run_and_apply_together(monkeypatch: pytest.MonkeyPatch, backfill_mod) -> None:
    monkeypatch.setattr(sys, "argv", ["backfill_river_scene_urls.py", "--dry-run", "--apply"])
    with pytest.raises(SystemExit) as ei:
        backfill_mod._parse_args()
    assert ei.value.code == 2


@pytest.mark.parametrize("extra", [[], ["--dry-run"]])
def test_preview_modes_do_not_set_apply(
    monkeypatch: pytest.MonkeyPatch, backfill_mod, extra: list[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["backfill_river_scene_urls.py", *extra])
    ns = backfill_mod._parse_args()
    assert ns.apply is False


def test_apply_flag_sets_apply(monkeypatch: pytest.MonkeyPatch, backfill_mod) -> None:
    monkeypatch.setattr(sys, "argv", ["backfill_river_scene_urls.py", "--apply"])
    ns = backfill_mod._parse_args()
    assert ns.apply is True


def test_counter_partition_dry_run(backfill_mod) -> None:
    rse_match = _rse(url=U_MATCH, labels={"Website": "https://organizer-match.example/same"})
    eu_m, desc_m, sk_m = _payload_triplet(backfill_mod, rse_match)

    rse_noorg = _rse(url=U_NOORG, labels={})
    eu_no, desc_no, sk_no = _payload_triplet(backfill_mod, rse_noorg)

    _add_event_contribution(
        article_url=U_CHANGE,
        event_url="https://stale.example/old",
        description="wrong description for change row",
        source_url=None,
    )
    _add_event_contribution(
        article_url=U_MATCH,
        event_url=eu_m,
        description=desc_m,
        source_url=sk_m if sk_m else None,
    )
    _add_event_contribution(
        article_url=U_NOORG,
        event_url=eu_no,
        description=desc_no,
        source_url=sk_no if sk_no else None,
    )
    _add_event_contribution(
        article_url=U_FAIL,
        event_url="https://example.com/ignored",
        description="fail row",
        source_url=None,
    )
    _add_event_contribution(
        article_url="placeholder",
        event_url="",
        description="no article url row",
        source_url=None,
        with_contribution=False,
    )

    with patch.object(backfill_mod.time, "sleep", lambda *a, **k: None):
        with patch.object(backfill_mod, "fetch_and_parse_event", side_effect=_fetch_router()):
            total, would_change, no_change, no_org, applied, skipped, no_art = backfill_mod.run_rescrape(
                apply=False
            )

    assert total == 5
    assert no_art == 1
    assert skipped == 1
    assert would_change == 1
    assert no_change == 2
    assert no_org == 1
    assert applied == 0


def test_apply_matches_would_change_from_preview(backfill_mod) -> None:
    _add_event_contribution(
        article_url=U_CHANGE,
        event_url="https://stale.example/old",
        description="wrong description for change row",
        source_url=None,
    )

    with patch.object(backfill_mod.time, "sleep", lambda *a, **k: None):
        with patch.object(backfill_mod, "fetch_and_parse_event", side_effect=_fetch_router()):
            pre = backfill_mod.run_rescrape(apply=False)
            assert pre[1] == 1  # would_change
            post = backfill_mod.run_rescrape(apply=True)
            assert post[4] == post[1] == 1  # applied == would_change


def test_print_diff_always_includes_source_url_lines(backfill_mod) -> None:
    """Would-change driven only by description; source_url block still prints."""
    ev = Event(
        id="evt-test",
        title="t",
        normalized_title="t",
        date=date(2026, 1, 1),
        end_date=None,
        start_time=time(9, 0),
        end_time=None,
        location_name="x",
        location_normalized="x",
        description="old desc",
        event_url="https://same.example/e",
        source_url="https://src-current.example/",
        source="river_scene_import",
    )
    proposed_desc = "new desc with enough chars xxxxxxxxxxxxxxxxxxxx"
    proposed_src = "https://src-proposed.example/path"
    buf = io.StringIO()
    with redirect_stdout(buf):
        backfill_mod._print_diff(
            ev.id,
            ev,
            event_url="https://same.example/e",
            description=proposed_desc,
            src_key=proposed_src,
        )
    out = buf.getvalue()
    assert "source_url:" in out
    assert "https://src-current.example/" in out
    assert "https://src-proposed.example/path" in out


def test_two_applies_idempotent(backfill_mod) -> None:
    _add_event_contribution(
        article_url=U_CHANGE,
        event_url="https://stale.example/old",
        description="wrong description for change row",
        source_url=None,
    )

    with patch.object(backfill_mod.time, "sleep", lambda *a, **k: None):
        with patch.object(backfill_mod, "fetch_and_parse_event", side_effect=_fetch_router()):
            first = backfill_mod.run_rescrape(apply=True)
            assert first[1] >= 1  # would_change
            assert first[4] == first[1]  # applied
            second = backfill_mod.run_rescrape(apply=True)
            assert second[4] == 0  # applied
            assert second[1] == 0  # would_change
            assert second[2] >= 1  # no_change
