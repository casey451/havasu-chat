"""Tests for ``app.chat.context_builder`` (Tier 3 catalog context)."""

from __future__ import annotations

import re
from datetime import date, time, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import ResourceClosedError
from sqlalchemy.orm import Session

from app.chat.context_builder import MAX_CONTEXT_WORDS, build_context_for_tier3
from app.chat.intent_classifier import IntentResult
from app.db.database import SessionLocal
from app.db.models import Event, Program, Provider


@pytest.fixture
def db() -> Session:
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def isolated_catalog(db: Session) -> Session:
    """Empty providers/programs/events for this test only; rolled back so the shared test DB stays clean."""
    nested = db.begin_nested()
    db.execute(delete(Program))
    db.execute(delete(Event))
    db.execute(delete(Provider))
    db.flush()
    yield db
    try:
        nested.rollback()
    except ResourceClosedError:
        pass


def _intent(*, entity: str | None = None, sub: str = "OPEN_ENDED") -> IntentResult:
    return IntentResult(
        mode="ask",
        sub_intent=sub,
        confidence=0.8,
        entity=entity,
        raw_query="q",
        normalized_query="q",
    )


def test_entity_matched_provider_listed_first_with_details(isolated_catalog: Session) -> None:
    db = isolated_catalog
    p_other = Provider(
        provider_name="Zebra Zoo",
        category="recreation",
        phone="111",
        verified=True,
        draft=False,
        is_active=True,
    )
    p_match = Provider(
        provider_name="Target Biz LLC",
        category="food",
        address="123 Main",
        phone="555-1212",
        website="https://target.example",
        hours="9-5",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add_all([p_other, p_match])
    db.flush()

    ctx = build_context_for_tier3("hours?", _intent(entity="Target Biz LLC"), db)
    names = re.findall(r"^Provider: (.+)$", ctx, re.MULTILINE)
    assert names[0] == "Target Biz LLC"
    assert "Provider: Zebra Zoo" in ctx
    assert "address: 123 Main" in ctx
    assert "phone: 555-1212" in ctx
    assert "website: https://target.example" in ctx
    assert "hours: 9-5" in ctx


def test_word_budget_respects_max_words(isolated_catalog: Session) -> None:
    db = isolated_catalog
    p = Provider(
        provider_name="Verbose Place",
        category="recreation",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    filler = "word " * 400
    prog = Program(
        title="T",
        description="Twenty chars minimum xx.",
        activity_category="sports",
        schedule_start_time=time(9, 0),
        schedule_end_time=time(10, 0),
        location_name="Here",
        provider_name=p.provider_name,
        provider_id=p.id,
        schedule_note=filler,
    )
    db.add(prog)
    db.flush()

    with patch("app.chat.context_builder.MAX_CONTEXT_WORDS", 80):
        ctx = build_context_for_tier3("q", _intent(), db)
    assert len(ctx.split()) <= 80


def test_default_context_word_count_at_most_budget(isolated_catalog: Session) -> None:
    db = isolated_catalog
    p = Provider(
        provider_name="Solo",
        category="recreation",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    ctx = build_context_for_tier3("anything", _intent(), db)
    assert len(ctx.split()) <= MAX_CONTEXT_WORDS


def test_draft_providers_excluded(isolated_catalog: Session) -> None:
    db = isolated_catalog
    db.add_all(
        [
            Provider(
                provider_name="Draft Only Inc",
                category="svc",
                draft=True,
                verified=False,
                is_active=True,
            ),
            Provider(
                provider_name="Real Co",
                category="svc",
                draft=False,
                verified=True,
                is_active=True,
            ),
        ]
    )
    db.flush()
    ctx = build_context_for_tier3("q", _intent(), db)
    assert "Draft Only Inc" not in ctx
    assert "Real Co" in ctx


def test_inactive_programs_excluded(isolated_catalog: Session) -> None:
    db = isolated_catalog
    p = Provider(
        provider_name="Prog Shop",
        category="edu",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    db.add_all(
        [
            Program(
                title="Active Lesson",
                description="Twenty chars minimum xx.",
                activity_category="sports",
                schedule_start_time=time(9, 0),
                schedule_end_time=time(10, 0),
                location_name="Here",
                provider_name=p.provider_name,
                provider_id=p.id,
                is_active=True,
            ),
            Program(
                title="Hidden Lesson",
                description="Twenty chars minimum yy.",
                activity_category="sports",
                schedule_start_time=time(11, 0),
                schedule_end_time=time(12, 0),
                location_name="Here",
                provider_name=p.provider_name,
                provider_id=p.id,
                is_active=False,
            ),
        ]
    )
    db.flush()
    ctx = build_context_for_tier3("q", _intent(), db)
    assert "Active Lesson" in ctx
    assert "Hidden Lesson" not in ctx


def test_past_events_excluded(isolated_catalog: Session) -> None:
    db = isolated_catalog
    p = Provider(
        provider_name="Event Host",
        category="fun",
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    today = date.today()
    db.add_all(
        [
            Event(
                title="Yesterday Gig",
                normalized_title="yesterday gig",
                date=today - timedelta(days=2),
                start_time=time(18, 0),
                location_name="Park",
                location_normalized="park",
                description="Twenty chars minimum ev.",
                provider_id=p.id,
                status="live",
            ),
            Event(
                title="Next Week Gig",
                normalized_title="next week gig",
                date=today + timedelta(days=9),
                start_time=time(18, 0),
                location_name="Park",
                location_normalized="park",
                description="Twenty chars minimum ev.",
                provider_id=p.id,
                status="live",
            ),
        ]
    )
    db.flush()
    ctx = build_context_for_tier3("events?", _intent(), db)
    assert "Yesterday Gig" not in ctx
    assert "Next Week Gig" in ctx


def test_long_hours_truncated(isolated_catalog: Session) -> None:
    db = isolated_catalog
    long_h = "x" * 250
    p = Provider(
        provider_name="Long Hours Biz",
        category="svc",
        hours=long_h,
        verified=True,
        draft=False,
        is_active=True,
    )
    db.add(p)
    db.flush()
    ctx = build_context_for_tier3("hours?", _intent(entity="Long Hours Biz"), db)
    assert "hours: " in ctx
    start = ctx.index("hours: ") + len("hours: ")
    # The ``hours: ...`` field can be the last line of the context block
    # with no trailing newline (the ENTITY-catalog code path renders it
    # that way; the Provider-catalog path traditionally adds a newline).
    # Tolerate both: search for the next newline, fall back to end-of-
    # string when none exists.
    end = ctx.find("\n", start)
    if end == -1:
        end = len(ctx)
    hrs_val = ctx[start:end].strip()
    assert hrs_val.endswith("...")
    assert len(hrs_val) == 200


def test_at_most_ten_providers(isolated_catalog: Session) -> None:
    db = isolated_catalog
    for i in range(12):
        db.add(
            Provider(
                provider_name=f"Cap Provider {i:02d}",
                category="misc",
                verified=True,
                draft=False,
                is_active=True,
            )
        )
    db.flush()
    ctx = build_context_for_tier3("list all", _intent(), db)
    assert ctx.count("Provider:") == 10


def test_when_no_active_includes_verified_fallback_slice(isolated_catalog: Session) -> None:
    db = isolated_catalog
    for i in range(11):
        db.add(
            Provider(
                provider_name=f"Inactive Verified {i:02d}",
                category="misc",
                verified=True,
                draft=False,
                is_active=False,
            )
        )
    db.flush()
    ctx = build_context_for_tier3("open ended", _intent(entity=None), db)
    assert ctx.count("Provider:") == 10


def test_DIAGNOSTIC_ci_entity_matched_state_capture(isolated_catalog: Session) -> None:
    """TEMP CI diagnostic — captures why the Entity branch returns empty on CI.

    Local Python 3.13.5 (single-file and full-suite): Entity branch produces
    "Entity: Target Biz LLC". CI Python 3.11.15 (full-suite): names == [].
    Most likely cause: _fetch_entity_rows applies LIMIT 30 BEFORE the
    case-insensitive name filter (which runs in Python). If the Entity table
    holds >30 active rows when this test runs, the matching one falls outside
    the LIMIT and the filter returns []. isolated_catalog clears Provider /
    Event / Program but NOT Entity, so the table accumulates across the run.

    This diagnostic prints:
      - total active Entity row count visible from this session
      - the first 30 Entity names the production query would return (no
        name filter) — exactly the slice _fetch_entity_rows works with
      - whether our matching "Target Biz LLC" is in that slice
      - the result of calling _fetch_entity_rows("Target Biz LLC") directly
      - the ctx string produced by build_context_for_tier3
      - the branch fingerprint

    Then asserts False so pytest prints stdout in the failure traceback.
    Delete this test once the fix is identified.
    """
    from sqlalchemy import func, select as _diag_select

    from app.chat.context_builder import _fetch_entity_rows as _diag_fetch_entity_rows
    from app.db import entity_dual_write as _diag_edw
    from app.db.models import Entity as _DiagEntity

    db = isolated_catalog

    print("\n[CIDIAG] === Entity table baseline (post isolated_catalog setup) ===")
    try:
        baseline_active = db.scalar(
            _diag_select(func.count())
            .select_from(_DiagEntity)
            .where(_DiagEntity.is_active.is_(True))
        )
    except BaseException as exc:  # noqa: BLE001
        baseline_active = f"<count raised: {type(exc).__name__}: {exc}>"
    try:
        baseline_total = db.scalar(_diag_select(func.count()).select_from(_DiagEntity))
    except BaseException as exc:  # noqa: BLE001
        baseline_total = f"<count raised: {type(exc).__name__}: {exc}>"
    print(f"[CIDIAG] baseline Entity total: {baseline_total!r}")
    print(f"[CIDIAG] baseline Entity active: {baseline_active!r}")

    p_other = Provider(
        provider_name="Zebra Zoo",
        category="recreation",
        phone="111",
        verified=True,
        draft=False,
        is_active=True,
    )
    p_match = Provider(
        provider_name="Target Biz LLC",
        category="food",
        address="123 Main",
        phone="555-1212",
        website="https://target.example",
        hours="9-5",
        verified=True,
        draft=False,
        is_active=True,
    )

    db.add_all([p_other, p_match])
    flush_error: BaseException | None = None
    try:
        db.flush()
    except BaseException as exc:  # noqa: BLE001
        flush_error = exc

    print(f"[CIDIAG] flush_error: {flush_error!r}")
    print(f"[CIDIAG] p_match.entity_id post-flush: {p_match.entity_id!r}")
    print(f"[CIDIAG] p_other.entity_id post-flush: {p_other.entity_id!r}")
    print(
        f"[CIDIAG] hook _CATALOG_DUAL_WRITE_HOOKS_REGISTERED = "
        f"{_diag_edw._CATALOG_DUAL_WRITE_HOOKS_REGISTERED!r}"
    )

    try:
        post_total = db.scalar(_diag_select(func.count()).select_from(_DiagEntity))
        post_active = db.scalar(
            _diag_select(func.count())
            .select_from(_DiagEntity)
            .where(_DiagEntity.is_active.is_(True))
        )
    except BaseException as exc:  # noqa: BLE001
        post_total = post_active = f"<count raised: {type(exc).__name__}: {exc}>"
    print(f"[CIDIAG] post-flush Entity total: {post_total!r}")
    print(f"[CIDIAG] post-flush Entity active: {post_active!r}")

    # Reproduce the prefilter slice _fetch_entity_rows uses: select active
    # entities with limit=30 (= limit*3 from caller default of 10), in
    # whatever DB-default order the production query gets.
    try:
        slice_q = (
            _diag_select(_DiagEntity.name)
            .where(_DiagEntity.is_active.is_(True))
            .limit(30)
        )
        slice_names = list(db.scalars(slice_q).all())
    except BaseException as exc:  # noqa: BLE001
        slice_names = f"<scalars raised: {type(exc).__name__}: {exc}>"
    print(f"[CIDIAG] _fetch_entity_rows-style LIMIT 30 slice size: "
          f"{len(slice_names) if isinstance(slice_names, list) else 'N/A'!r}")
    if isinstance(slice_names, list):
        target_in_slice = "Target Biz LLC" in slice_names
        zebra_in_slice = "Zebra Zoo" in slice_names
        print(f"[CIDIAG] 'Target Biz LLC' in slice: {target_in_slice!r}")
        print(f"[CIDIAG] 'Zebra Zoo'      in slice: {zebra_in_slice!r}")
        print(f"[CIDIAG] full slice names (first 30): {slice_names!r}")

    # Now call the actual production helper to see what it returns.
    try:
        helper_rows = _diag_fetch_entity_rows(db, "Target Biz LLC")
        helper_names = [(e.id, e.name) for e in helper_rows]
    except BaseException as exc:  # noqa: BLE001
        helper_names = f"<_fetch_entity_rows raised: {type(exc).__name__}: {exc}>"
    print(f"[CIDIAG] _fetch_entity_rows('Target Biz LLC') -> {helper_names!r}")

    # And the full ctx.
    try:
        ctx = build_context_for_tier3("hours?", _intent(entity="Target Biz LLC"), db)
    except BaseException as exc:  # noqa: BLE001
        ctx = f"<build_context_for_tier3 raised: {type(exc).__name__}: {exc}>"
    print(f"[CIDIAG] ctx repr: {ctx!r}")
    if isinstance(ctx, str):
        starts_entity = "Entity:" in ctx
        starts_provider = "Provider:" in ctx
        is_fallback = "No verified provider rows are available" in ctx
        print(
            f"[CIDIAG] branch fingerprint: entity_branch={starts_entity} "
            f"provider_branch={starts_provider} fallback={is_fallback}"
        )

    raise AssertionError("CIDIAG - see [CIDIAG] stdout above")
