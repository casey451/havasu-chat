"""Tests for ``scripts/cleanup_non_river_scene.py`` (destructive cleanup; in-memory SQLite only)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date, time
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import (
    ChatLog,
    Contribution,
    Event,
    FieldHistory,
    LlmMentionedEntity,
    Program,
    Provider,
)

ROOT = Path(__file__).resolve().parents[1]

RS = "river_scene_import"
OP = "operator_backfill"
ADM = "admin"


@pytest.fixture(scope="module")
def cleanup_mod():
    path = ROOT / "scripts" / "cleanup_non_river_scene.py"
    name = "cleanup_non_river_scene_test_mod"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = S()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _seed_chat(db) -> str:
    cid = "cl-test-1"
    db.add(
        ChatLog(
            id=cid,
            session_id="sess",
            message="hello",
            role="user",
            intent=None,
        )
    )
    db.commit()
    return cid


def _seed_full_graph(db, *, bad_rs_link: bool = False) -> None:
    """RS inventory: 2 contributions + 2 events; deletable rows with known counts."""
    chat_id = _seed_chat(db)

    p1 = Provider(
        id="prov-seed-1",
        provider_name="Seed Gym",
        category="fitness",
        source="seed",
    )
    p2 = Provider(
        id="prov-rs-1",
        provider_name="RS Place",
        category="music",
        source="seed",
    )
    db.add_all([p1, p2])
    db.flush()

    pr_admin = Program(
        id="prog-admin-1",
        title="Admin Swim",
        description="d",
        activity_category="swim",
        schedule_days=["Mon"],
        schedule_start_time=time(9, 0),
        schedule_end_time=time(10, 0),
        location_name="Pool",
        provider_name="City",
        source=ADM,
        provider_id=p1.id,
    )
    pr_scrape = Program(
        id="prog-scrape-1",
        title="Scraped Yoga",
        description="d",
        activity_category="yoga",
        schedule_days=["Tue"],
        schedule_start_time=time(11, 0),
        schedule_end_time=time(12, 0),
        location_name="Studio",
        provider_name="Yoga Co",
        source="scraped",
        provider_id=p1.id,
    )
    db.add_all([pr_admin, pr_scrape])
    db.flush()

    ev_rs_a = "ev-rs-a"
    ev_rs_b = "ev-rs-b"
    ev_adm = "ev-admin-1"

    db.add_all(
        [
            Event(
                id=ev_rs_a,
                title="RS A",
                normalized_title="rs a",
                date=date(2026, 6, 1),
                end_date=None,
                start_time=time(10, 0),
                end_time=None,
                location_name="L",
                location_normalized="l",
                description="rs",
                event_url="https://riverscenemagazine.com/e/a",
                source_url=None,
                source=RS,
                provider_id=p2.id,
            ),
            Event(
                id=ev_rs_b,
                title="RS B",
                normalized_title="rs b",
                date=date(2026, 6, 2),
                end_date=None,
                start_time=time(11, 0),
                end_time=None,
                location_name="L2",
                location_normalized="l2",
                description="rs2",
                event_url="https://riverscenemagazine.com/e/b",
                source_url=None,
                source=RS,
                provider_id=p2.id,
            ),
            Event(
                id=ev_adm,
                title="Admin Fair",
                normalized_title="admin fair",
                date=date(2026, 7, 1),
                end_date=None,
                start_time=time(9, 0),
                end_time=None,
                location_name="Park",
                location_normalized="park",
                description="fair",
                event_url="https://example.com/fair",
                source_url=None,
                source=ADM,
                provider_id=p1.id,
            ),
        ]
    )
    db.flush()

    target_rs_event = ev_adm if bad_rs_link else ev_rs_a

    db.add_all(
        [
            Contribution(
                entity_type="event",
                submission_name="RS A",
                submission_url="https://riverscenemagazine.com/e/a",
                source=RS,
                status="approved",
                created_event_id=target_rs_event,
                created_program_id=pr_admin.id,
                created_provider_id=p1.id,
            ),
            Contribution(
                entity_type="event",
                submission_name="RS B",
                submission_url="https://riverscenemagazine.com/e/b",
                source=RS,
                status="approved",
                created_event_id=ev_rs_b,
                created_program_id=None,
                created_provider_id=None,
            ),
            Contribution(
                entity_type="event",
                submission_name="Backfill",
                submission_url="https://example.com/bf",
                source=OP,
                status="approved",
                created_event_id=ev_adm,
                created_program_id=None,
                created_provider_id=None,
            ),
        ]
    )
    db.flush()

    db.add_all(
        [
            LlmMentionedEntity(chat_log_id=chat_id, mentioned_name="Aquatic"),
            LlmMentionedEntity(chat_log_id=chat_id, mentioned_name="Golf"),
        ]
    )
    db.add_all(
        [
            FieldHistory(
                entity_type="program",
                entity_id=pr_admin.id,
                field_name="hours",
                old_value="9",
                new_value="10",
                source="seed",
                state="pending",
            ),
        ]
    )
    db.commit()


def _table_counts(db) -> dict[str, int]:
    return {
        "llm": db.query(LlmMentionedEntity).count(),
        "fh": db.query(FieldHistory).count(),
        "c_op": db.query(Contribution).filter(Contribution.source == OP).count(),
        "e_adm": db.query(Event).filter(Event.source == ADM).count(),
        "p": db.query(Program).count(),
        "pr": db.query(Provider).count(),
        "c_rs": db.query(Contribution).filter(Contribution.source == RS).count(),
        "e_rs": db.query(Event).filter(Event.source == RS).count(),
    }


def test_parse_args_rejects_dry_run_and_apply_together(cleanup_mod) -> None:
    with pytest.raises(SystemExit) as ei:
        cleanup_mod._parse_args(["--dry-run", "--apply"])
    assert ei.value.code == 2


def test_yes_requires_apply(monkeypatch: pytest.MonkeyPatch, cleanup_mod) -> None:
    monkeypatch.setattr(sys, "argv", ["cleanup_non_river_scene.py", "--yes"])
    with pytest.raises(SystemExit) as ei:
        cleanup_mod._parse_args()
    assert ei.value.code == 2


@pytest.mark.parametrize("extra", [[], ["--dry-run"]])
def test_preview_argv_sets_apply_false(
    monkeypatch: pytest.MonkeyPatch, cleanup_mod, extra: list[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["cleanup_non_river_scene.py", *extra])
    ns = cleanup_mod._parse_args()
    assert ns.apply is False


def test_apply_argv_sets_apply(monkeypatch: pytest.MonkeyPatch, cleanup_mod) -> None:
    monkeypatch.setattr(sys, "argv", ["cleanup_non_river_scene.py", "--apply"])
    ns = cleanup_mod._parse_args()
    assert ns.apply is True


def test_dry_run_leaves_rows_unchanged(cleanup_mod, db_session) -> None:
    _seed_full_graph(db_session)
    before = _table_counts(db_session)
    cleanup_mod.run_cleanup(db_session, apply=False, min_rs_contributions=2, min_rs_events=2)
    after = _table_counts(db_session)
    assert before == after
    assert before["llm"] == 2
    assert before["fh"] == 1
    assert before["c_op"] == 1
    assert before["e_adm"] == 1
    assert before["p"] == 2
    assert before["pr"] == 2


def test_dry_run_counters_match_expectation(cleanup_mod, db_session) -> None:
    _seed_full_graph(db_session)
    c = cleanup_mod.count_deletable_rows(db_session)
    assert c.llm_mentioned_entities == 2
    assert c.field_history == 1
    assert c.contributions_non_rs == 1
    assert c.events_non_rs == 1
    assert c.programs == 2
    assert c.providers == 2
    assert c.total == 9


def test_apply_matches_dry_run_counts(cleanup_mod, db_session) -> None:
    _seed_full_graph(db_session)
    expected = cleanup_mod.count_deletable_rows(db_session)
    cleanup_mod.run_cleanup(
        db_session,
        apply=True,
        assume_yes=True,
        min_rs_contributions=2,
        min_rs_events=2,
    )
    after = cleanup_mod.count_deletable_rows(db_session)
    assert after.total == 0
    assert db_session.query(Contribution).filter(Contribution.source == RS).count() == 2
    assert db_session.query(Event).filter(Event.source == RS).count() == 2
    assert expected.total == 9


def test_idempotent_second_apply(cleanup_mod, db_session) -> None:
    _seed_full_graph(db_session)
    cleanup_mod.run_cleanup(
        db_session,
        apply=True,
        assume_yes=True,
        min_rs_contributions=2,
        min_rs_events=2,
    )
    first_total = 9
    assert cleanup_mod.count_deletable_rows(db_session).total == 0
    cleanup_mod.run_cleanup(
        db_session,
        apply=True,
        assume_yes=True,
        min_rs_contributions=2,
        min_rs_events=2,
    )
    c2 = cleanup_mod.count_deletable_rows(db_session)
    assert c2.total == 0
    # first run deleted known total; second deletes nothing
    assert first_total > 0


def test_preflight_halts_when_rs_counts_too_low(cleanup_mod, db_session) -> None:
    _seed_full_graph(db_session)
    with pytest.raises(cleanup_mod.PreflightError):
        cleanup_mod.run_cleanup(db_session, apply=False, min_rs_contributions=10, min_rs_events=2)


def test_preflight_halts_on_rs_to_admin_event_link(cleanup_mod, db_session) -> None:
    _seed_full_graph(db_session, bad_rs_link=True)
    with pytest.raises(cleanup_mod.PreflightError):
        cleanup_mod.run_cleanup(db_session, apply=False, min_rs_contributions=2, min_rs_events=2)


def test_transactional_rollback_on_injected_failure(cleanup_mod, db_session) -> None:
    _seed_full_graph(db_session)
    before = _table_counts(db_session)
    with pytest.raises(RuntimeError, match="injected"):
        cleanup_mod.run_cleanup(
            db_session,
            apply=True,
            assume_yes=True,
            min_rs_contributions=2,
            min_rs_events=2,
            inject_failure_before="events",
        )
    db_session.rollback()
    after = _table_counts(db_session)
    assert after == before


def test_fk_order_survives_on_synthetic_db(cleanup_mod, db_session) -> None:
    _seed_full_graph(db_session)
    cleanup_mod.run_cleanup(
        db_session,
        apply=True,
        assume_yes=True,
        min_rs_contributions=2,
        min_rs_events=2,
    )
    db_session.expire_all()
    assert db_session.query(Program).count() == 0
    assert db_session.query(Provider).count() == 0
    rs_ev = db_session.query(Event).filter(Event.source == RS).all()
    assert len(rs_ev) == 2
    assert all(e.provider_id is None for e in rs_ev)
    rs_c = db_session.query(Contribution).filter(Contribution.source == RS).all()
    assert len(rs_c) == 2
    assert all(c.created_program_id is None for c in rs_c)
    assert all(c.created_provider_id is None for c in rs_c)


def test_apply_prompt_requires_exact_yes(cleanup_mod, db_session) -> None:
    _seed_full_graph(db_session)
    with pytest.raises(cleanup_mod.ApplyAborted):
        cleanup_mod.run_cleanup(
            db_session,
            apply=True,
            assume_yes=False,
            min_rs_contributions=2,
            min_rs_events=2,
            input_fn=lambda _: "no",
        )


def test_apply_prompt_accepts_yes(cleanup_mod, db_session) -> None:
    _seed_full_graph(db_session)
    cleanup_mod.run_cleanup(
        db_session,
        apply=True,
        assume_yes=False,
        min_rs_contributions=2,
        min_rs_events=2,
        input_fn=lambda _: "yes",
    )
    assert cleanup_mod.count_deletable_rows(db_session).total == 0


def _session_local_cm(session):
    class _CM:
        def __enter__(self_inner):
            return session

        def __exit__(self_inner, *a):
            return False

    return _CM()


def test_main_preflight_returns_3(cleanup_mod, db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_full_graph(db_session)
    monkeypatch.setattr(cleanup_mod, "SessionLocal", lambda: _session_local_cm(db_session))
    monkeypatch.delenv("CLEANUP_MIN_RS_CONTRIBUTIONS", raising=False)
    monkeypatch.delenv("CLEANUP_MIN_RS_EVENTS", raising=False)
    assert cleanup_mod.main(["--dry-run"]) == 3


def test_main_dry_run_returns_0_with_env_floor(
    cleanup_mod, db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_full_graph(db_session)
    monkeypatch.setattr(cleanup_mod, "SessionLocal", lambda: _session_local_cm(db_session))
    monkeypatch.setenv("CLEANUP_MIN_RS_CONTRIBUTIONS", "2")
    monkeypatch.setenv("CLEANUP_MIN_RS_EVENTS", "2")
    assert cleanup_mod.main(["--dry-run"]) == 0


def test_main_apply_yes_returns_0(cleanup_mod, db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_full_graph(db_session)
    monkeypatch.setattr(cleanup_mod, "SessionLocal", lambda: _session_local_cm(db_session))
    monkeypatch.setenv("CLEANUP_MIN_RS_CONTRIBUTIONS", "2")
    monkeypatch.setenv("CLEANUP_MIN_RS_EVENTS", "2")
    assert cleanup_mod.main(["--apply", "--yes"]) == 0
    assert cleanup_mod.count_deletable_rows(db_session).total == 0


def test_main_apply_declined_returns_5(
    cleanup_mod, db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_full_graph(db_session)
    monkeypatch.setattr(cleanup_mod, "SessionLocal", lambda: _session_local_cm(db_session))
    monkeypatch.setenv("CLEANUP_MIN_RS_CONTRIBUTIONS", "2")
    monkeypatch.setenv("CLEANUP_MIN_RS_EVENTS", "2")
    monkeypatch.setattr("builtins.input", lambda _p: "no")
    assert cleanup_mod.main(["--apply"]) == 5
