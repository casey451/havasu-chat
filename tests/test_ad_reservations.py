"""Ad-reservation admin queue + status FSM, and the ad_reservations migration.

The public "Reserve this spot" flow (/portal/reserve) was removed in the
advertise-page teardown. The ``ad_reservations`` table, the AdReservation model,
and the admin queue remain so historical leads stay viewable; these tests cover
the admin queue + status FSM and the table's migration upgrade/downgrade cycle.
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
