"""2.8 — Website promoted into the provider action row.

High-intent visitors shouldn't have to hunt the sidebar for the website. When a
provider has a website (and isn't showing the claim CTA), a secondary "Website"
button renders in the Call/Directions/Save action row. Call stays the only
primary CTA, and the row is ``flex-wrap`` so a 4th button reflows.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.models import Category, Entity, Provider
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _eat_category_id(db) -> int:
    row = db.scalars(select(Category).where(Category.slug == "eat-drink")).first()
    assert row is not None
    return row.id


def _actions_block(html: str) -> str:
    """The markup inside the provider action row (lake: ``<div class="pcta-act">``)."""
    after = html.split('class="pcta-act"', 1)[1]
    return after.split("</div>", 1)[0]


def _make_provider(db, *, suf: str, website: str | None) -> str:
    eat_id = _eat_category_id(db)
    p = Provider(
        provider_name=f"Action Row {suf}",
        category="restaurant",
        category_id=eat_id,
        verified=True,  # → show_claim_cta False, so the Website gate can open
        draft=False,
        is_active=True,
        pending_review=False,
        source="test-2.8",
        slug=f"action-row-{suf}",
        website=website,
    )
    db.add(p)
    db.commit()
    return p.entity_id


def _cleanup(eid: str) -> None:
    with SessionLocal() as db:
        db.execute(delete(Provider).where(Provider.entity_id == eid))
        db.execute(delete(Entity).where(Entity.id == eid))
        db.commit()


def test_website_button_renders_in_action_row_when_present(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    site = f"https://example-{suf}.com"
    with SessionLocal() as db:
        eid = _make_provider(db, suf=suf, website=site)
    try:
        r = client.get(f"/provider/action-row-{suf}")
        assert r.status_code == 200
        actions = _actions_block(r.text)
        assert "Website" in actions, "Website CTA missing from the action row"
        assert site in actions, "Website href missing from the action row"
        # Call must remain the only primary CTA.
        assert actions.count("btn-primary") <= 1
    finally:
        _cleanup(eid)


def test_no_website_button_when_absent(client: TestClient) -> None:
    suf = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        eid = _make_provider(db, suf=suf, website=None)
    try:
        r = client.get(f"/provider/action-row-{suf}")
        assert r.status_code == 200
        actions = _actions_block(r.text)
        assert "Website" not in actions
    finally:
        _cleanup(eid)
