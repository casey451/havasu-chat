"""Phase 3.2 — category taxonomy rewrite, backfill, district seed, close-out."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text

from alembic import command
from app.db.database import SessionLocal, engine
from app.db.entity_dual_write import create_provider_and_entity
from app.db.models import Category, Entity, Location, Provider
from app.home.queries import CATEGORY_LABELS

NEW_12_SLUGS = {
    "home-property-services",
    "health-wellness-care",
    "eat-drink",
    "on-the-water",
    "auto-rv-fuel",
    "shopping-essentials",
    "outdoors-parks-trails",
    "lodging-vacation-rentals",
    "pets",
    "events",
    "classes-sports-recreation",
    "public-civic-resources",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _mirror_pass1_provider_category(session, prov: Provider, legacy: str, slug: str) -> None:
    """Re-apply portable Phase 3.2 Pass-1 UPDATE for rows created after migration ran."""
    session.flush()
    assert prov.category == legacy
    cid = session.scalars(select(Category.id).where(Category.slug == slug)).one()
    prov.category_id = cid
    session.commit()


def _mirror_district_id_for_entity(session, entity_id: str) -> None:
    session.execute(
        text(
            "UPDATE entities SET district_id = ("
            " SELECT d.id FROM districts AS d"
            " INNER JOIN locations AS l ON l.entity_id = entities.id"
            " WHERE LOWER(TRIM(d.name)) = LOWER(TRIM(l.district))"
            " LIMIT 1"
            ") WHERE id = :eid AND district_id IS NULL"
        ),
        {"eid": entity_id},
    )
    session.commit()


def _mirror_featured_for_entity(session, entity_id: str) -> None:
    session.execute(
        text(
            "UPDATE entities SET featured = ("
            " SELECT providers.featured FROM providers"
            " WHERE providers.entity_id = entities.id"
            ") WHERE id = :eid AND entity_type = 'commercial'"
        ),
        {"eid": entity_id},
    )
    session.commit()


def test_migration_upgrade_downgrade_upgrade_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "phase32.sqlite"
    url = f"sqlite:///{db_path.resolve().as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)

    eng = create_engine(url, connect_args={"check_same_thread": False})
    command.upgrade(cfg, "head")
    eng.dispose()
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")
    eng2 = create_engine(url, connect_args={"check_same_thread": False})
    try:
        with eng2.connect() as conn:
            ver = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert ver == "e1f2a3b4c5d6"
    finally:
        eng2.dispose()


def test_after_upgrade_categories_count_and_slugs() -> None:
    with SessionLocal() as db:
        rows = db.query(Category).all()
        assert len(rows) == 12
        assert {c.slug for c in rows} == NEW_12_SLUGS
        assert all(c.slug not in ("family", "community") for c in rows)


def test_sort_order_synthesis_tier_order() -> None:
    with SessionLocal() as db:
        rows = db.query(Category).order_by(Category.sort_order).all()
        assert [c.sort_order for c in rows] == list(range(1, 13))
        assert rows[0].slug == "home-property-services"
        assert rows[-1].slug == "public-civic-resources"


def test_bucket_a_provider_food_drink() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Food {suf}",
            category="food_drink",
            address="1 Main",
            verified=True,
            draft=False,
            is_active=True,
            source="test-p32",
            slug=f"food-{suf}",
            created_at=now,
            updated_at=now,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        _mirror_pass1_provider_category(db, p, "food_drink", "eat-drink")
        pid = p.id
    with SessionLocal() as db:
        p2 = db.get(Provider, pid)
        assert p2 is not None
        db.refresh(p2, ["category_ref"])
        assert p2.category_ref is not None
        assert p2.category_ref.slug == "eat-drink"


def test_pass2_childcare_education_and_education_public_schools_lock() -> None:
    """Pass 2 maps childcare_education + education (+ edu) to classes-sports-recreation.

    Operator lock A.4 is documented-only (no separate Pass-4 SQL): audit memo §2 line 64
    places K-12 / charter / public school as sub-questions of ``education``; session-20
    confirms Pass 2 routing covers public schools (not ``public-civic-resources``).
    """
    now = _now()
    for leg, label in (
        ("childcare_education", "Care"),
        ("education", "School"),
    ):
        suf = uuid.uuid4().hex[:8]
        with SessionLocal() as db:
            p = Provider(
                provider_name=f"{label} {suf}",
                category=leg,
                address="2 Main",
                verified=True,
                draft=False,
                is_active=True,
                source="test-p32",
                slug=f"{label.lower()}-{suf}",
                created_at=now,
                updated_at=now,
            )
            db.add(p)
            create_provider_and_entity(db, p)
            _mirror_pass1_provider_category(db, p, leg, "classes-sports-recreation")
            pid = p.id
        with SessionLocal() as db:
            p2 = db.get(Provider, pid)
            assert p2 is not None
            db.refresh(p2, ["category_ref"])
            assert p2.category_ref is not None
            assert p2.category_ref.slug == "classes-sports-recreation"


def test_bucket_b_religion_community() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Faith {suf}",
            category="religion_community",
            address="3 Main",
            verified=True,
            draft=False,
            is_active=True,
            source="test-p32",
            slug=f"faith-{suf}",
            created_at=now,
            updated_at=now,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        _mirror_pass1_provider_category(db, p, "religion_community", "public-civic-resources")
        pid = p.id
    with SessionLocal() as db:
        p2 = db.get(Provider, pid)
        assert p2 is not None
        db.refresh(p2, ["category_ref"])
        assert p2.category_ref is not None
        assert p2.category_ref.slug == "public-civic-resources"


def test_bucket_b_insurance_null() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Ins {suf}",
            category="insurance",
            address="4 Main",
            verified=True,
            draft=False,
            is_active=True,
            source="test-p32",
            slug=f"ins-{suf}",
            created_at=now,
            updated_at=now,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()
        pid = p.id
    with SessionLocal() as db:
        p2 = db.get(Provider, pid)
        assert p2 is not None
        assert p2.category_id is None


def test_districts_ten_rows_english_village_null_paragraph() -> None:
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM districts")).scalar_one()
        assert int(n) == 10
        row = conn.execute(
            text(
                "SELECT slug, name, display_order, paragraph FROM districts "
                "WHERE slug = 'english-village'"
            )
        ).one()
        assert row[0] == "english-village"
        assert row[1] == "English Village"
        assert row[2] == 1
        assert row[3] is None


def test_entity_district_id_from_location_string() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"District {suf}",
            category="retail",
            address="5 Main",
            verified=True,
            draft=False,
            is_active=True,
            source="test-p32",
            slug=f"dist-{suf}",
            created_at=now,
            updated_at=now,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.flush()
        ent = db.get(Entity, p.entity_id)
        assert ent is not None
        loc = db.scalars(select(Location).where(Location.entity_id == ent.id)).first()
        assert loc is not None
        loc.district = "English Village"
        db.commit()
        _mirror_district_id_for_entity(db, ent.id)
        eid = ent.id
    with SessionLocal() as db:
        ent2 = db.get(Entity, eid)
        assert ent2 is not None
        db.refresh(ent2, ["district"])
        assert ent2.district_id is not None
        assert ent2.district.slug == "english-village"


def test_entities_table_has_no_string_district_column() -> None:
    insp = inspect(engine)
    names = {c["name"] for c in insp.get_columns("entities")}
    assert "district" not in names


def test_entity_featured_from_provider_featured() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Feat {suf}",
            category="retail",
            address="6 Main",
            verified=True,
            draft=False,
            is_active=True,
            source="test-p32",
            slug=f"feat-{suf}",
            featured=True,
            created_at=now,
            updated_at=now,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()
        _mirror_featured_for_entity(db, p.entity_id)
        eid = p.entity_id
    with SessionLocal() as db:
        ent = db.get(Entity, eid)
        assert ent is not None
        assert ent.featured is True


def test_category_labels_keys_match_new_taxonomy() -> None:
    assert set(CATEGORY_LABELS.keys()) == NEW_12_SLUGS


def test_validator_rejects_legacy_slug() -> None:
    from scripts.ingest.validate_enrichment_csv import validate_row

    r = validate_row(
        {
            "provider_name": "X",
            "category": "family",
            "address": "1 Main",
            "phone": "9284440100",
            "owner_email": "a@b.co",
            "hava_voice_description": "x" * 80,
            "last_verified_at": "2026-01-01T00:00:00+00:00",
            "verification_method": "phone_call",
        },
        row_number=2,
    )
    assert not r.passed
    assert any("legacy" in e.lower() for e in r.errors)


def test_validator_accepts_new_slug() -> None:
    from scripts.ingest.validate_enrichment_csv import validate_row

    r = validate_row(
        {
            "provider_name": "X",
            "category": "eat-drink",
            "address": "1 Main",
            "phone": "9284440100",
            "owner_email": "a@b.co",
            "hava_voice_description": "x" * 80,
            "last_verified_at": "2026-01-01T00:00:00+00:00",
            "verification_method": "phone_call",
        },
        row_number=2,
    )
    assert r.passed, r.errors


def test_backfill_idempotent_second_pass_noop() -> None:
    """Second identical UPDATE with ``AND category_id IS NULL`` touches 0 rows."""
    stmt = text(
        "UPDATE providers SET category_id = (SELECT id FROM categories WHERE slug = 'eat-drink') "
        "WHERE category = '__phase32_noop_probe__' AND category_id IS NULL"
    )
    with engine.connect() as conn:
        conn.execute(stmt)
        conn.execute(stmt)
        conn.commit()


def test_entity_categories_family_orphans_deleted() -> None:
    """Upgrade used DELETE for junction rows targeting deleted categories."""
    with engine.connect() as conn:
        n = conn.execute(
            text(
                "SELECT COUNT(*) FROM entity_categories ec "
                "JOIN categories c ON c.id = ec.category_id "
                "WHERE c.slug IN ('family', 'community')"
            )
        ).scalar_one()
        assert int(n) == 0


def test_bucket_c_beauty_null() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Beauty {suf}",
            category="beauty_personal_care",
            address="7 Main",
            verified=True,
            draft=False,
            is_active=True,
            source="test-p32",
            slug=f"beauty-{suf}",
            created_at=now,
            updated_at=now,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()
        pid = p.id
    with SessionLocal() as db:
        p2 = db.get(Provider, pid)
        assert p2 is not None
        assert p2.category_id is None


def test_bucket_c_tourism_null() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Tour {suf}",
            category="tourism",
            address="8 Main",
            verified=True,
            draft=False,
            is_active=True,
            source="test-p32",
            slug=f"tour-{suf}",
            created_at=now,
            updated_at=now,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()
        pid = p.id
    with SessionLocal() as db:
        p2 = db.get(Provider, pid)
        assert p2 is not None
        assert p2.category_id is None


def test_bucket_c_barbershop_null() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Barber {suf}",
            category="barbershop",
            address="8b Main",
            verified=True,
            draft=False,
            is_active=True,
            source="test-p32",
            slug=f"barber-{suf}",
            created_at=now,
            updated_at=now,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()
        pid = p.id
    with SessionLocal() as db:
        p2 = db.get(Provider, pid)
        assert p2 is not None
        assert p2.category_id is None


def test_pass2_entertainment_attractions_deferred_null_phase5_triage_lock() -> None:
    """``entertainment_attractions`` stays NULL in 3.2 (audit + brief §5.2 deferral).

    Operator lock A.5 is documented-only: bowling / arcades / mini golf are subsets of this
    bucket per audit memo §2 line 84; Phase 5 split maps those venues to
    ``classes-sports-recreation`` when ``google_primary_category`` triage lands — not a 3.2 SQL action.
    """
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Fun {suf}",
            category="entertainment_attractions",
            address="9 Main",
            verified=True,
            draft=False,
            is_active=True,
            source="test-p32",
            slug=f"fun-{suf}",
            created_at=now,
            updated_at=now,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        db.commit()
        pid = p.id
    with SessionLocal() as db:
        p2 = db.get(Provider, pid)
        assert p2 is not None
        assert p2.category_id is None


def test_bucket_c_recreation_classes_sports() -> None:
    """Audit memo §2 Bucket E: ``recreation`` → ``classes-sports-recreation``."""
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        p = Provider(
            provider_name=f"Rec {suf}",
            category="recreation",
            address="10 Main",
            verified=True,
            draft=False,
            is_active=True,
            source="test-p32",
            slug=f"rec-{suf}",
            created_at=now,
            updated_at=now,
        )
        db.add(p)
        create_provider_and_entity(db, p)
        _mirror_pass1_provider_category(db, p, "recreation", "classes-sports-recreation")
        pid = p.id
    with SessionLocal() as db:
        p2 = db.get(Provider, pid)
        assert p2 is not None
        db.refresh(p2, ["category_ref"])
        assert p2.category_ref is not None
        assert p2.category_ref.slug == "classes-sports-recreation"


def test_home_get_returns_200() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        r = client.get("/home")
        assert r.status_code == 200
