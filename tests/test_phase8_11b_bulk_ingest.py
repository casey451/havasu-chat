from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.contrib.google_bulk_ingest import parse_jsonl, run_ingest
from app.db.database import SessionLocal
from app.db.models import Event, Program, Provider

FIXTURES = Path(__file__).resolve().parent.parent / "scripts" / "fixtures"
SAMPLE_JSONL = FIXTURES / "google_bulk_sample.jsonl"


def _wipe_provider_graph() -> None:
    with SessionLocal() as db:
        db.query(Event).delete()
        db.query(Program).delete()
        db.query(Provider).delete()
        db.commit()


@pytest.fixture(autouse=True)
def _clean_providers() -> None:
    _wipe_provider_graph()
    yield
    _wipe_provider_graph()


def test_parse_jsonl_happy_path(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_text(
        '{"a": 1}\n'
        '{"b": 2}\n'
        '{"c": 3}\n',
        encoding="utf-8",
    )
    rows = parse_jsonl(p)
    assert len(rows) == 3
    assert rows[0] == {"a": 1}
    assert rows[1] == {"b": 2}
    assert rows[2] == {"c": 3}


def test_parse_jsonl_skips_malformed_lines(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "bad.jsonl"
    p.write_text(
        '{"ok": true}\n'
        "not json {{{\n"
        '{"also": "ok"}\n',
        encoding="utf-8",
    )
    rows = parse_jsonl(p)
    assert len(rows) == 2
    assert rows[0] == {"ok": True}
    assert rows[1] == {"also": "ok"}
    err = capsys.readouterr().err
    assert "skip line 2" in err


def test_ingest_inserts_new_provider(tmp_path: Path) -> None:
    row = {
        "google_place_id": "ChIJinsert01",
        "provider_name": "Solo Shop",
        "category": "other",
        "address": "1 Test Way",
    }
    path = tmp_path / "one.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with SessionLocal() as db:
        c = run_ingest(path, db, dry_run=False)
    assert c.inserted == 1
    assert c.updated == 0
    with SessionLocal() as db:
        prov = db.query(Provider).filter(Provider.google_place_id == "ChIJinsert01").one()
    assert prov.provider_name == "Solo Shop"
    assert prov.source == "google_bulk_import"
    assert prov.address == "1 Test Way"


def test_ingest_updates_by_place_id(tmp_path: Path) -> None:
    with SessionLocal() as db:
        db.add(
            Provider(
                id=str(uuid4()),
                provider_name="Old Name",
                category="other",
                source="seed",
                google_place_id="ChIJupdatepl01",
            )
        )
        db.commit()

    row = {
        "google_place_id": "ChIJupdatepl01",
        "provider_name": "New Name",
        "category": "golf",
    }
    jpath = _tmp_jsonl_from_row(tmp_path, row)
    with SessionLocal() as db:
        c = run_ingest(jpath, db, dry_run=False)
    assert c.updated == 1
    assert c.inserted == 0
    with SessionLocal() as db:
        n = db.query(Provider).count()
        prov = db.query(Provider).one()
    assert n == 1
    assert prov.provider_name == "New Name"
    assert prov.category == "golf"


def test_ingest_updates_by_normalized_name_fallback(tmp_path: Path) -> None:
    with SessionLocal() as db:
        db.add(
            Provider(
                id=str(uuid4()),
                provider_name="Joe's Hardware",
                category="other",
                source="seed",
                google_place_id=None,
            )
        )
        db.commit()

    row = {
        "google_place_id": "ChIJjoehard99",
        "provider_name": "Joe's Hardware",
        "category": "hardware store",
    }
    path = _tmp_jsonl_from_row(tmp_path, row)
    with SessionLocal() as db:
        c = run_ingest(path, db, dry_run=False)
    assert c.updated == 1
    with SessionLocal() as db:
        prov = db.query(Provider).one()
    assert prov.google_place_id == "ChIJjoehard99"
    assert prov.source == "seed"
    assert prov.category == "hardware store"


def test_ingest_skips_missing_required_fields(tmp_path: Path) -> None:
    row = {"google_place_id": None, "provider_name": "X", "category": "other"}
    p = _tmp_jsonl_from_row(tmp_path, row)
    with SessionLocal() as db:
        c = run_ingest(p, db, dry_run=False)
    assert c.skipped_missing_required == 1
    assert c.inserted == 0
    with SessionLocal() as db:
        assert db.query(Provider).count() == 0


def test_ingest_skips_duplicate_in_file(tmp_path: Path) -> None:
    p = tmp_path / "dup.jsonl"
    p.write_text(
        '{"google_place_id": "ChIJdup", "provider_name": "First", "category": "other"}\n'
        '{"google_place_id": "ChIJdup", "provider_name": "Second", "category": "golf"}\n',
        encoding="utf-8",
    )
    with SessionLocal() as db:
        c = run_ingest(p, db, dry_run=False)
    assert c.inserted == 1
    assert c.skipped_duplicate_in_file == 1
    with SessionLocal() as db:
        p = db.query(Provider).one()
    assert p.provider_name == "First"


def test_ingest_dry_run_does_not_write() -> None:
    with SessionLocal() as db:
        c = run_ingest(SAMPLE_JSONL, db, dry_run=True)
    assert c.fetched_rows >= 1
    with SessionLocal() as db:
        n = db.query(Provider).filter(Provider.source == "google_bulk_import").count()
    assert n == 0


def test_ingest_does_not_touch_embedding(tmp_path: Path) -> None:
    row = {
        "google_place_id": "ChIJnoembed1",
        "provider_name": "No Embed Shop",
        "category": "other",
    }
    p = _tmp_jsonl_from_row(tmp_path, row)
    with SessionLocal() as db:
        c = run_ingest(p, db, dry_run=False)
    assert c.inserted == 1
    with SessionLocal() as db:
        p = db.query(Provider).one()
    assert p.embedding is None


def test_ingest_does_not_overwrite_protected_fields(tmp_path: Path) -> None:
    with SessionLocal() as db:
        db.add(
            Provider(
                id=str(uuid4()),
                provider_name="Verified Place",
                category="other",
                source="user",
                google_place_id="ChIJprotected1",
                verified=True,
                draft=False,
            )
        )
        db.commit()

    row = {
        "google_place_id": "ChIJprotected1",
        "provider_name": "Verified Place Updated",
        "category": "fitness",
    }
    p = _tmp_jsonl_from_row(tmp_path, row)
    with SessionLocal() as db:
        c = run_ingest(p, db, dry_run=False)
    assert c.updated == 1
    with SessionLocal() as db:
        q = db.query(Provider).one()
    assert q.verified is True
    assert q.draft is False
    assert q.provider_name == "Verified Place Updated"
    assert q.category == "fitness"


def _tmp_jsonl_from_row(tmp_path: Path, row: dict) -> Path:
    path = tmp_path / "ingest.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return path
