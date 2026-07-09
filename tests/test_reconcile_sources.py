"""Tests for the reconciliation classification core + report + ledger persist."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.contrib.reconcile_core import (
    classify_business,
    classify_event,
    invariant_green,
    summarize,
)

# provider index: name-slug -> (id, current_leaf)
_PROVIDERS_BY_NAME = {
    "arizona-s-fun-on-the-water": ("prov-1", "boat-and-watercraft-rentals"),  # mis-filed
    "lobster-3-ways": ("prov-2", "restaurants"),  # correctly filed
}
_PROVIDERS_BY_WEB: dict[str, tuple[str, str | None]] = {}


def _biz(name, cat, addr="Lake Havasu City, AZ"):
    return classify_business(
        source="go_lake_havasu",
        source_url=f"https://golakehavasu.com/partner/{name}",
        name=name,
        address=addr,
        source_category=cat,
        providers_by_name=_PROVIDERS_BY_NAME,
        providers_by_web=_PROVIDERS_BY_WEB,
    )


def test_business_matched() -> None:
    r = _biz("Lobster 3 Ways", "Restaurant/Bar")
    assert r.match_status == "matched"
    assert r.matched_id == "prov-2"
    assert r.mapped == "restaurants"


def test_business_miscategorized() -> None:
    # present but filed in rentals, crosswalk says charter
    r = _biz("Arizona's Fun on the Water", "Charters")
    assert r.match_status == "miscategorized"
    assert r.mapped == "boat-tours-and-charters"
    assert r.matched_id == "prov-1"


def test_business_missing() -> None:
    r = _biz("Brand New Charter Co", "Charters")
    assert r.match_status == "missing"
    assert r.mapped == "boat-tours-and-charters"
    assert r.matched_id is None


def test_business_excluded_out_of_area() -> None:
    r = _biz("Parker Marina", "Boating", addr="Parker, AZ")
    assert r.match_status == "excluded"
    assert r.exclusion_reason == "outside-service-area"
    assert r.region == "parker"


def test_business_excluded_suppressed() -> None:
    r = classify_business(
        source="go_lake_havasu",
        source_url="https://x/y",
        name="Wake Surf Adventures",
        address="Lake Havasu City, AZ",
        source_category="Charters",
        providers_by_name=_PROVIDERS_BY_NAME,
        providers_by_web=_PROVIDERS_BY_WEB,
        suppressed_names=frozenset({"wake-surf-adventures"}),
    )
    assert r.match_status == "excluded"
    assert r.exclusion_reason == "suppressed"


# --- events ---

_EVENTS_BY_KEY = {("london-bridge-days", "2026-10-10"): "evt-1"}


def _evt(title, cat, d, venue="Lake Havasu City"):
    return classify_event(
        source="river_scene",
        source_url=f"https://riverscene.com/event/{title}",
        title=title,
        event_date=d,
        venue=venue,
        source_category=cat,
        events_by_key=_EVENTS_BY_KEY,
    )


def test_event_matched() -> None:
    r = _evt("London Bridge Days", "festival", date(2026, 10, 10))
    assert r.match_status == "matched"
    assert r.mapped == "festival"


def test_event_missing() -> None:
    r = _evt("Some New Concert", "music", date(2026, 9, 1))
    assert r.match_status == "missing"
    assert r.mapped == "music"


def test_event_excluded_out_of_area() -> None:
    r = _evt("Laughlin River Run", "racing", date(2026, 4, 1), venue="Laughlin, NV")
    assert r.match_status == "excluded"
    assert r.exclusion_reason == "outside-service-area"


# --- summarize / invariant ---


def test_summarize_and_invariant() -> None:
    rows = [
        _biz("Lobster 3 Ways", "Restaurant/Bar"),  # matched
        _biz("Parker Marina", "Boating", addr="Parker, AZ"),  # excluded w/ reason
    ]
    counts = summarize(rows)
    assert counts["matched"] == 1
    assert counts["excluded"] == 1
    assert counts.get("excluded_without_reason", 0) == 0
    assert invariant_green(counts) is True


def test_invariant_red_on_missing() -> None:
    rows = [_biz("Brand New Charter Co", "Charters")]  # missing
    assert invariant_green(summarize(rows)) is False


def test_persist_ledger_upsert() -> None:
    from sqlalchemy import select

    from app.contrib.reconcile_live import persist_ledger
    from app.db.database import SessionLocal
    from app.db.models import SourceListing

    rows = [_biz("Ledger Test Co", "Charters")]  # missing -> ledger row
    persist_ledger(rows)
    persist_ledger(rows)  # second run must upsert, not duplicate
    with SessionLocal() as db:
        hits = db.scalars(
            select(SourceListing).where(
                SourceListing.source_url == "https://golakehavasu.com/partner/Ledger Test Co"
            )
        ).all()
        assert len(hits) == 1
        assert hits[0].match_status == "missing"
        assert hits[0].mapped_leaf == "boat-tours-and-charters"
        db.delete(hits[0])
        db.commit()


def test_write_report(tmp_path: Path) -> None:
    from scripts.reconcile_sources import write_report

    rows = [
        _biz("Lobster 3 Ways", "Restaurant/Bar"),
        _biz("Arizona's Fun on the Water", "Charters"),  # miscategorized
    ]
    md, csvp = write_report(rows, tmp_path, "2026-07-03")
    assert md.exists() and csvp.exists()
    text = md.read_text(encoding="utf-8")
    assert "miscategorized" in text
    assert "RED" in text  # miscategorized present -> invariant red
