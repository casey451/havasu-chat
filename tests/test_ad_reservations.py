"""Manual-invoice "Reserve this spot" ad-placement order flow.

Covers the /portal/reserve form + POST, the admin queue + status FSM, and a
migration upgrade/downgrade cycle for the ad_reservations table. Mirrors
tests/test_business_portal.py (portal) and the phase-migration tests that pin a
revision and assert its down_revision (tests/test_phase9_events_schema.py).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, inspect, text

from alembic import command
from app.admin.auth import COOKIE_NAME, sign_admin_cookie
from app.db.database import SessionLocal
from app.db.models import AdReservation, AdReservationStatus
from app.main import app


def _login_admin(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_PASSWORD", "changeme")
    client.cookies.set(COOKIE_NAME, sign_admin_cookie())


def _cleanup(business_name: str) -> None:
    with SessionLocal() as db:
        db.execute(delete(AdReservation).where(AdReservation.business_name == business_name))
        db.commit()


# ── form rendering ────────────────────────────────────────────────────────────


def test_reserve_form_category_renders_product_and_category_select() -> None:
    with TestClient(app) as client:
        r = client.get("/portal/reserve?product=category")
    assert r.status_code == 200
    body = r.text
    assert "Category Sponsorship" in body
    assert "<select" in body and 'name="category"' in body
    # A real taxonomy label is offered as an option.
    assert "Eat &amp; Drink" in body or "Eat & Drink" in body
    assert "no payment" in body.lower()


def test_reserve_form_non_category_shows_notes_not_select() -> None:
    with TestClient(app) as client:
        r = client.get("/portal/reserve?product=founding")
    assert r.status_code == 200
    assert 'name="notes"' in r.text
    assert 'name="category"' not in r.text


def test_reserve_unknown_product_redirects_to_advertise() -> None:
    with TestClient(app) as client:
        r = client.get("/portal/reserve?product=bogus", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/portal/advertise"


# ── POST: create + validation ──────────────────────────────────────────────────


def test_reserve_post_valid_creates_pending_and_lands_on_thanks() -> None:
    biz = f"Test Biz {uuid.uuid4().hex[:8]}"
    try:
        with TestClient(app) as client:
            r = client.post(
                "/portal/reserve",
                data={
                    "product": "founding",
                    "business_name": biz,
                    "contact_name": "Pat Prospect",
                    "contact_email": "pat@example.com",
                    "notes": "Launch promo",
                },
                follow_redirects=False,
            )
        assert r.status_code == 303
        assert r.headers["location"] == "/portal/reserve/thanks"
        with SessionLocal() as db:
            rows = (
                db.query(AdReservation).filter(AdReservation.business_name == biz).all()
            )
        assert len(rows) == 1
        row = rows[0]
        assert row.status == AdReservationStatus.PENDING.value
        assert row.product_key == "founding"
        assert row.product_name == "Founding Partner"
        assert row.source == "advertise_page"
    finally:
        _cleanup(biz)


def test_reserve_post_category_snapshots_label() -> None:
    biz = f"Cat Biz {uuid.uuid4().hex[:8]}"
    try:
        with TestClient(app) as client:
            r = client.post(
                "/portal/reserve",
                data={
                    "product": "category",
                    "business_name": biz,
                    "contact_name": "Cat Owner",
                    "contact_email": "cat@example.com",
                    "category": "eat-drink",
                },
                follow_redirects=False,
            )
        assert r.status_code == 303
        with SessionLocal() as db:
            row = (
                db.query(AdReservation).filter(AdReservation.business_name == biz).one()
            )
        assert row.category_or_notes == "Eat & Drink"
    finally:
        _cleanup(biz)


def test_reserve_post_missing_email_rerenders_and_creates_no_row() -> None:
    biz = f"NoEmail Biz {uuid.uuid4().hex[:8]}"
    try:
        with TestClient(app) as client:
            r = client.post(
                "/portal/reserve",
                data={
                    "product": "founding",
                    "business_name": biz,
                    "contact_name": "Pat Prospect",
                    "contact_email": "",
                },
                follow_redirects=False,
            )
        assert r.status_code == 400
        assert "Reserve this spot" in r.text  # form re-rendered
        assert biz in r.text  # input preserved
        with SessionLocal() as db:
            count = (
                db.query(AdReservation).filter(AdReservation.business_name == biz).count()
            )
        assert count == 0
    finally:
        _cleanup(biz)


# ── admin queue + status FSM ────────────────────────────────────────────────────


def test_admin_queue_lists_and_status_advances_pending_to_contacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    biz = f"Admin Biz {uuid.uuid4().hex[:8]}"
    res_id = str(uuid.uuid4())
    try:
        with SessionLocal() as db:
            db.add(
                AdReservation(
                    id=res_id,
                    product_key="gas",
                    product_name="Gas / Utility Sponsor",
                    business_name=biz,
                    contact_name="Gas Owner",
                    contact_email="gas@example.com",
                    status=AdReservationStatus.PENDING.value,
                )
            )
            db.commit()

        client = TestClient(app)
        _login_admin(client, monkeypatch)
        listing = client.get("/admin/ad-reservations")
        assert listing.status_code == 200
        assert biz in listing.text

        advance = client.post(
            f"/admin/ad-reservations/{res_id}/status",
            data={"status": AdReservationStatus.CONTACTED.value},
            follow_redirects=False,
        )
        assert advance.status_code == 303
        with SessionLocal() as db:
            row = db.get(AdReservation, res_id)
            assert row is not None
            assert row.status == AdReservationStatus.CONTACTED.value
    finally:
        _cleanup(biz)


def test_admin_queue_requires_login() -> None:
    client = TestClient(app)
    r = client.get("/admin/ad-reservations", follow_redirects=False)
    assert r.status_code in (302, 303)


# ── migration upgrade/downgrade cycle ───────────────────────────────────────────


def test_migration_upgrade_downgrade_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "ad_reservations.sqlite"
    url = f"sqlite:///{db_path.resolve().as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)

    # Pin to this migration's revision so the test stays valid as later
    # migrations land (the phase-9 test does the same).
    AD_RESERVATIONS_REVISION = "f1a7c9e2b3d4"
    command.upgrade(cfg, AD_RESERVATIONS_REVISION)

    script = ScriptDirectory.from_config(cfg)
    rev = script.get_revision(AD_RESERVATIONS_REVISION)
    assert rev is not None
    # Chains off the true head at authoring time.
    assert rev.down_revision == "a7c9e1f3b5d7"

    eng = create_engine(url, connect_args={"check_same_thread": False})
    try:
        insp = inspect(eng)
        assert "ad_reservations" in insp.get_table_names()
        cols = {c["name"] for c in insp.get_columns("ad_reservations")}
        for name in (
            "id",
            "product_key",
            "product_name",
            "business_name",
            "contact_name",
            "contact_email",
            "contact_phone",
            "category_or_notes",
            "status",
            "source",
            "created_at",
        ):
            assert name in cols
        with eng.connect() as conn:
            ver = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert ver == AD_RESERVATIONS_REVISION
        indexes = {ix["name"] for ix in insp.get_indexes("ad_reservations")}
        assert "ix_ad_reservations_status" in indexes
        assert "ix_ad_reservations_created_at" in indexes
    finally:
        eng.dispose()

    command.downgrade(cfg, "-1")
    eng = create_engine(url, connect_args={"check_same_thread": False})
    try:
        insp = inspect(eng)
        assert "ad_reservations" not in insp.get_table_names()
    finally:
        eng.dispose()
