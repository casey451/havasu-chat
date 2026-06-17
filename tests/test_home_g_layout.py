"""Workstream G — home reorder + tiered ad slots.

Covers the new section order (category strip + Tier-1 marquee above the fold,
Explore grid promoted above the month calendar, Tier-3 promoted after Explore),
and the real-or-omit behavior of the marquee (card when sold, slim claim when
unsold) and promoted (rendered when sold, absent when unsold) slots.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Sponsor, SponsorStatus
from app.main import app

_NAME_PREFIX = "GTEST-"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _seed_sponsor(slot: str, *, headline: str) -> str:
    name = f"{_NAME_PREFIX}{slot}-{uuid4().hex[:6]}"
    with SessionLocal() as db:
        s = Sponsor(
            name=name,
            slot=slot,
            status=SponsorStatus.APPROVED.value,
            active=True,
            headline=headline,
            pitch="A clearly-labeled local sponsor.",
            eyebrow="Local business",
            cta_label="Visit",
            cta_url="https://example.com",
            weight=10,
        )
        db.add(s)
        db.commit()
        return s.id


def _cleanup_sponsors() -> None:
    with SessionLocal() as db:
        for s in db.scalars(
            select(Sponsor).where(Sponsor.name.like(f"{_NAME_PREFIX}%"))
        ).all():
            db.delete(s)
        db.commit()


@pytest.fixture(autouse=True)
def _sponsor_cleanup() -> Iterator[None]:
    _cleanup_sponsors()
    yield
    _cleanup_sponsors()


# --- section order + always-on blocks ---------------------------------------


def test_home_section_order_breadth_and_explore_above_month(
    client: TestClient, seeded_nav_departments: dict
) -> None:
    r = client.get("/home")
    assert r.status_code == 200
    body = r.text
    # Always-present sections, in G order. (home-week is gated on events, and
    # home-featured — copy audit 2026-06-10 — on a real sold spotlight, so
    # neither is part of this chain.)
    # Phase 6B: the premium sponsor placard (home-marquee) was relocated ABOVE
    # THE FOLD — directly under the intent chips and above the explore grid — so a
    # sold placement renders on first load. Order is now intents → marquee →
    # (week) → explore → … → calendar.
    i_intents = body.find("home-intents")
    i_explore = body.find("home-explore")
    i_marquee = body.find("home-marquee")
    i_cal = body.find("home-cal")
    assert -1 < i_intents < i_marquee < i_explore < i_cal
    # Core fix preserved: the directory grid lands BEFORE the month calendar.
    assert i_explore < i_cal


def test_home_category_strip_present_with_pills(
    client: TestClient, seeded_nav_departments: dict
) -> None:
    # §2.5: the category grid is the consolidated color-tile "home-explore"; the
    # compact "home-catstrip" pill strip was removed as a duplicate.
    body = client.get("/home").text
    assert "home-explore" in body
    assert "catchip" in body


def test_home_featured_hidden_until_a_spotlight_sells(client: TestClient) -> None:
    """Copy audit 2026-06-10: two empty ad surfaces read as 'nobody advertises
    here' — the Featured row renders only once a real spotlight is sold."""
    body = client.get("/home").text
    assert "Featured <em>this week</em>" not in body
    assert "home-featured" not in body


def test_home_featured_renders_when_spotlight_sold(client: TestClient) -> None:
    sid = _seed_sponsor("spotlight", headline="Desert Bloom Coffee")
    body = client.get("/home").text
    assert "Featured <em>this week</em>" in body
    assert "Desert Bloom Coffee" in body
    # The href arrives via a Jinja VARIABLE, so autoescape renders the
    # ampersand as &amp; — assert the parts, not the raw join.
    assert f"/sponsor/click?id={sid}" in body
    assert "slot=spotlight" in body
    # Phase 6B order: the placard (marquee) sits above the fold under the chips,
    # then the explore grid, then the featured row.
    assert body.find("home-marquee") < body.find("home-explore") < body.find("home-featured")


# --- Tier-1 marquee (real-or-omit) ------------------------------------------


def test_marquee_collapses_to_claim_when_unsold(client: TestClient) -> None:
    body = client.get("/home").text
    assert "marquee-claim" in body
    assert "marquee-card" not in body


def test_marquee_renders_card_when_sold(client: TestClient) -> None:
    sid = _seed_sponsor("marquee", headline="Joes Lakeside Grill")
    body = client.get("/home").text
    assert "marquee-card" in body
    assert "marquee-claim" not in body
    assert "Joes Lakeside Grill" in body
    assert f"/sponsor/click?id={sid}&slot=marquee" in body
    # Labeled, per the honesty contract.
    assert "Featured" in body


# --- Tier-3 promoted (real-or-omit) -----------------------------------------


def test_promoted_absent_when_unsold(client: TestClient) -> None:
    body = client.get("/home").text
    assert "home-promoted" not in body


def test_promoted_renders_when_sold(client: TestClient) -> None:
    sid = _seed_sponsor("promoted", headline="Havasu Solar Co")
    body = client.get("/home").text
    assert "home-promoted" in body
    assert "Havasu Solar Co" in body
    assert f"/sponsor/click?id={sid}&slot=promoted" in body
    assert "Sponsored" in body
