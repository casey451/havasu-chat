"""WS12 ingest_runs heartbeat — runner instrumentation + freshness canary mode."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import scripts.freshness_check as fc
import scripts.scrape_events as se
from app.db.database import SessionLocal
from app.db.models import IngestRun


def _cleanup(source: str) -> None:
    with SessionLocal() as db:
        for row in db.query(IngestRun).filter(IngestRun.source == source).all():
            db.delete(row)
        db.commit()


class _EmptyClient:
    """A connector whose run() yields nothing (e.g. off-season / no new events)."""

    scrape_source = "test_heartbeat_src"

    def run(self, query):  # noqa: ANN001, ANN201
        return []


def test_run_source_records_heartbeat_even_with_zero_payloads(monkeypatch) -> None:
    src = "test_heartbeat_src"
    _cleanup(src)
    try:
        monkeypatch.setitem(se.SOURCE_REGISTRY, src, _EmptyClient)
        counts = se.run_source(src, dry_run=False)
        assert counts == {}
        with SessionLocal() as db:
            rows = db.query(IngestRun).filter(IngestRun.source == src).all()
        assert len(rows) == 1
        assert rows[0].status == "ok"
        assert rows[0].payloads_total == 0
        assert rows[0].dry_run is False
    finally:
        _cleanup(src)


def test_dry_run_heartbeat_is_flagged(monkeypatch) -> None:
    src = "test_heartbeat_src"
    _cleanup(src)
    try:
        monkeypatch.setitem(se.SOURCE_REGISTRY, src, _EmptyClient)
        se.run_source(src, dry_run=True)
        with SessionLocal() as db:
            row = db.query(IngestRun).filter(IngestRun.source == src).one()
        assert row.dry_run is True
        # newest_run ignores dry-run rows, so freshness sees nothing.
        with SessionLocal() as db:
            assert fc.newest_run(db, src) is None
    finally:
        _cleanup(src)


def _seed_run(source: str, ran_at: datetime, *, dry_run: bool = False) -> None:
    with SessionLocal() as db:
        db.add(
            IngestRun(
                source=source,
                ran_at=ran_at,
                status="ok",
                dry_run=dry_run,
                payloads_total=0,
                counts={},
            )
        )
        db.commit()


def _check(source: str) -> fc.SourceCheck:
    return fc.SourceCheck(
        label=source, source=source, cadence="test", max_age_hours=120.0, mode="ingest_run"
    )


def test_ingest_run_mode_pending_when_never_run() -> None:
    src = "test_heartbeat_pending"
    _cleanup(src)
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        results = fc.evaluate(db, [_check(src)], now=now)
    # Never ran -> PENDING, and PENDING must not be counted as a failure.
    assert results[0].status == "PENDING"


def test_ingest_run_mode_ok_then_stale() -> None:
    src = "test_heartbeat_agebands"
    _cleanup(src)
    now = datetime.now(UTC).replace(tzinfo=None)
    try:
        _seed_run(src, now - timedelta(hours=10))  # within 120h budget
        with SessionLocal() as db:
            assert fc.evaluate(db, [_check(src)], now=now)[0].status == "OK"
        _seed_run(src, now - timedelta(hours=200))  # older, but max() still 10h
        with SessionLocal() as db:
            assert fc.evaluate(db, [_check(src)], now=now)[0].status == "OK"
        _cleanup(src)
        _seed_run(src, now - timedelta(hours=200))  # only an old run -> STALE
        with SessionLocal() as db:
            assert fc.evaluate(db, [_check(src)], now=now)[0].status == "STALE"
    finally:
        _cleanup(src)
