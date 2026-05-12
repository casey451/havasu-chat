"""Phase 2A.1 — account-lite tables + ORM wiring (additive migration only)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal, engine
from app.db.entity_types import ENTITY_TYPE_COMMERCIAL
from app.db.models import AuthSession, Claim, Entity, MagicLinkToken, User, UserFavorite

_ACCOUNT_TABLES = (
    "users",
    "magic_link_tokens",
    "sessions",
    "user_favorites",
    "claims",
)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware_expires() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=15)


def test_account_lite_tables_exist() -> None:
    insp = inspect(engine)
    for name in _ACCOUNT_TABLES:
        assert insp.has_table(name), f"missing table {name}"


@pytest.mark.parametrize(
    ("table_name", "required_columns"),
    [
        (
            "users",
            {
                "id",
                "email",
                "display_name",
                "role",
                "is_active",
                "created_at",
                "last_login_at",
            },
        ),
        (
            "magic_link_tokens",
            {
                "id",
                "email",
                "token_hash",
                "expires_at",
                "consumed_at",
                "requested_from_ip_hash",
                "created_at",
            },
        ),
        (
            "sessions",
            {
                "id",
                "user_id",
                "created_at",
                "last_seen_at",
                "expires_at",
                "ip_hash",
                "user_agent_hash",
            },
        ),
        (
            "user_favorites",
            {"id", "user_id", "entity_id", "created_at"},
        ),
        (
            "claims",
            {
                "id",
                "user_id",
                "entity_id",
                "status",
                "verification_method",
                "claimed_at",
                "verified_at",
                "rejected_at",
                "rejection_reason",
                "verified_by",
            },
        ),
    ],
)
def test_account_lite_column_sets(table_name: str, required_columns: set[str]) -> None:
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns(table_name)}
    assert required_columns <= cols


def test_users_role_check_constraint() -> None:
    now = _now()
    with SessionLocal() as db:
        db.add(
            User(
                email=f"bad-role-{uuid.uuid4().hex[:8]}@example.com",
                role="superuser",
                created_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_claims_status_check_constraint() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        u = User(email=f"claim-bad-{suf}@example.com", created_at=now)
        db.add(u)
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"claim-bad-{suf}",
            name="Bad status",
            source="test",
            created_at=now,
            updated_at=now,
        )
        db.add(e)
        db.flush()
        db.add(
            Claim(
                user_id=u.id,
                entity_id=e.id,
                status="bogus",
                claimed_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_claims_verification_method_check_constraint() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        u = User(email=f"claim-vm-{suf}@example.com", created_at=now)
        db.add(u)
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"claim-vm-{suf}",
            name="VM",
            source="test",
            created_at=now,
            updated_at=now,
        )
        db.add(e)
        db.flush()
        db.add(
            Claim(
                user_id=u.id,
                entity_id=e.id,
                status="pending",
                verification_method="invalid_method",
                claimed_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_users_email_unique() -> None:
    suf = uuid.uuid4().hex[:8]
    email = f"dup-email-{suf}@example.com"
    now = _now()
    with SessionLocal() as db:
        db.add(User(email=email, created_at=now))
        db.commit()
        db.add(User(email=email, created_at=now))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_magic_link_token_hash_unique() -> None:
    suf = uuid.uuid4().hex[:8]
    h = "a" * 64
    now = _now()
    exp = _aware_expires()
    with SessionLocal() as db:
        db.add(
            MagicLinkToken(
                email=f"tok1-{suf}@example.com",
                token_hash=h,
                expires_at=exp,
                created_at=now,
            )
        )
        db.commit()
        db.add(
            MagicLinkToken(
                email=f"tok2-{suf}@example.com",
                token_hash=h,
                expires_at=exp,
                created_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_user_favorites_user_entity_unique() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        u = User(email=f"fav-uq-{suf}@example.com", created_at=now)
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"fav-uq-{suf}",
            name="Fav UQ",
            source="test",
            created_at=now,
            updated_at=now,
        )
        db.add_all([u, e])
        db.flush()
        db.add(UserFavorite(user_id=u.id, entity_id=e.id, created_at=now))
        db.flush()
        db.add(UserFavorite(user_id=u.id, entity_id=e.id, created_at=now))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_claims_user_entity_unique() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        u = User(email=f"cl-uq-{suf}@example.com", created_at=now)
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"cl-uq-{suf}",
            name="Cl UQ",
            source="test",
            created_at=now,
            updated_at=now,
        )
        db.add_all([u, e])
        db.flush()
        db.add(Claim(user_id=u.id, entity_id=e.id, claimed_at=now))
        db.flush()
        db.add(Claim(user_id=u.id, entity_id=e.id, claimed_at=now))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_user_delete_cascades_sessions_favorites_claims() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    exp = _aware_expires()
    with SessionLocal() as db:
        db.execute(text("PRAGMA foreign_keys=ON"))
        u = User(email=f"cascade-u-{suf}@example.com", created_at=now)
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"cascade-u-{suf}",
            name="Cascade user",
            source="test",
            created_at=now,
            updated_at=now,
        )
        db.add_all([u, e])
        db.flush()
        sid = uuid.uuid4().hex
        db.add(
            AuthSession(
                id=sid,
                user_id=u.id,
                created_at=now,
                last_seen_at=now,
                expires_at=exp,
            )
        )
        db.add(UserFavorite(user_id=u.id, entity_id=e.id, created_at=now))
        db.add(Claim(user_id=u.id, entity_id=e.id, claimed_at=now))
        db.commit()
        uid = u.id
        eid = e.id

    with SessionLocal() as db:
        db.execute(text("PRAGMA foreign_keys=ON"))
        row = db.get(User, uid)
        assert row is not None
        db.delete(row)
        db.commit()

    with SessionLocal() as db:
        assert db.get(User, uid) is None
        assert db.query(AuthSession).filter_by(id=sid).count() == 0
        assert db.query(UserFavorite).filter_by(user_id=uid).count() == 0
        assert db.query(Claim).filter_by(user_id=uid).count() == 0
        assert db.get(Entity, eid) is not None

    engine.dispose()


def test_entity_delete_cascades_favorites_and_claims() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        db.execute(text("PRAGMA foreign_keys=ON"))
        u = User(email=f"cascade-e-{suf}@example.com", created_at=now)
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"cascade-e-{suf}",
            name="Cascade entity",
            source="test",
            created_at=now,
            updated_at=now,
        )
        db.add_all([u, e])
        db.flush()
        eid = e.id
        db.add(UserFavorite(user_id=u.id, entity_id=e.id, created_at=now))
        db.add(Claim(user_id=u.id, entity_id=e.id, claimed_at=now))
        db.commit()

    with SessionLocal() as db:
        db.execute(text("PRAGMA foreign_keys=ON"))
        ent = db.get(Entity, eid)
        assert ent is not None
        db.delete(ent)
        db.commit()

    with SessionLocal() as db:
        assert db.get(Entity, eid) is None
        assert db.query(UserFavorite).filter_by(entity_id=eid).count() == 0
        assert db.query(Claim).filter_by(entity_id=eid).count() == 0

    engine.dispose()


def test_session_user_relationship_navigates() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    exp = _aware_expires()
    with SessionLocal() as db:
        u = User(email=f"sess-rel-{suf}@example.com", created_at=now)
        db.add(u)
        db.flush()
        sid = str(uuid.uuid4())
        db.add(
            AuthSession(
                id=sid,
                user_id=u.id,
                created_at=now,
                last_seen_at=now,
                expires_at=exp,
            )
        )
        db.commit()

    with SessionLocal() as db:
        srow = db.get(AuthSession, sid)
        assert srow is not None
        assert srow.user is not None
        assert srow.user.email == f"sess-rel-{suf}@example.com"


def test_user_favorite_entity_relationship_navigates() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        u = User(email=f"fav-rel-{suf}@example.com", created_at=now)
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"fav-rel-{suf}",
            name="Fav rel",
            source="test",
            created_at=now,
            updated_at=now,
        )
        db.add_all([u, e])
        db.flush()
        fav = UserFavorite(user_id=u.id, entity_id=e.id, created_at=now)
        db.add(fav)
        db.commit()
        fid = fav.id

    with SessionLocal() as db:
        loaded = db.get(UserFavorite, fid)
        assert loaded is not None
        assert loaded.entity.slug == f"fav-rel-{suf}"


def test_claim_entity_and_verifier_relationships_navigate() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        verifier = User(email=f"ver-{suf}@example.com", created_at=now)
        claimant = User(email=f"clm-{suf}@example.com", created_at=now)
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"claim-rel-{suf}",
            name="Claim rel",
            source="test",
            created_at=now,
            updated_at=now,
        )
        db.add_all([verifier, claimant, e])
        db.flush()
        c = Claim(
            user_id=claimant.id,
            entity_id=e.id,
            status="verified",
            claimed_at=now,
            verified_at=now,
            verified_by=verifier.id,
            verification_method="in_person",
        )
        db.add(c)
        db.commit()
        cid = c.id
        vid = verifier.id

    with SessionLocal() as db:
        loaded = db.get(Claim, cid)
        assert loaded is not None
        assert loaded.entity.name == "Claim rel"
        assert loaded.verifier is not None
        assert loaded.verifier.id == vid


def test_user_last_login_at_nullable_and_updateable() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    login = (now + timedelta(hours=1)).replace(tzinfo=None)
    with SessionLocal() as db:
        u = User(email=f"lla-{suf}@example.com", created_at=now)
        db.add(u)
        db.commit()
        uid = u.id

    with SessionLocal() as db:
        row = db.get(User, uid)
        assert row is not None
        assert row.last_login_at is None
        row.last_login_at = login
        db.commit()

    with SessionLocal() as db:
        row = db.get(User, uid)
        assert row is not None
        assert row.last_login_at is not None
        assert row.last_login_at == login


def test_users_email_unique_constraint_registered() -> None:
    insp = inspect(engine)
    uq = insp.get_unique_constraints("users")
    assert any("email" in c["column_names"] for c in uq)


def test_claim_null_verification_method_allowed() -> None:
    suf = uuid.uuid4().hex[:8]
    now = _now()
    with SessionLocal() as db:
        u = User(email=f"vm-null-{suf}@example.com", created_at=now)
        e = Entity(
            entity_type=ENTITY_TYPE_COMMERCIAL,
            slug=f"vm-null-{suf}",
            name="VM null",
            source="test",
            created_at=now,
            updated_at=now,
        )
        db.add_all([u, e])
        db.flush()
        db.add(
            Claim(
                user_id=u.id,
                entity_id=e.id,
                status="pending",
                verification_method=None,
                claimed_at=now,
            )
        )
        db.commit()
