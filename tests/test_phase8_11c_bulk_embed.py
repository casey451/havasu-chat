from __future__ import annotations

import logging
from typing import Any
from unittest import mock
from uuid import uuid4

import pytest

from app.contrib.google_bulk_embed import EMBED_TEXT_MAX_CHARS, build_embedding_text, run_embed
from app.db.database import SessionLocal
from app.db.models import Event, Program, Provider


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


@pytest.fixture(autouse=True)
def _no_batch_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.contrib.google_bulk_embed.time.sleep", lambda *_: None)


@pytest.fixture(autouse=True)
def _openai_key_for_embed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-dry run_embed() requires a key at startup; most tests only mock the API call."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-embed-key-synthetic")


def _vec(d: int = 1536) -> list[float]:
    return [0.01] * d


def test_build_embedding_text_full() -> None:
    t = build_embedding_text("Acme", "cafe", "Great coffee")
    assert t == "Acme | cafe | Great coffee"


def test_build_embedding_text_missing_description() -> None:
    t = build_embedding_text("Zed", "gym", None)
    assert t == "Zed | gym"


def test_build_embedding_text_missing_category_and_description() -> None:
    t = build_embedding_text("Solo", None, None)
    assert t == "Solo"


def test_build_embedding_text_missing_name() -> None:
    assert build_embedding_text(None, "a", "b") is None
    assert build_embedding_text("", "a", "b") is None


def test_build_embedding_text_empty_strings() -> None:
    t = build_embedding_text("N", "   ", "")
    assert t == "N"


def test_build_embedding_text_strips_whitespace() -> None:
    t = build_embedding_text("  Name  ", "  Cat  ", "  desc  ")
    assert t == "Name | Cat | desc"


def test_run_embed_raises_without_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with SessionLocal() as db:
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
            run_embed(db, dry_run=False)


def test_build_embedding_text_truncates_long_text() -> None:
    long_desc = "D" * (EMBED_TEXT_MAX_CHARS + 500)
    t = build_embedding_text("A", "B", long_desc)
    assert t is not None
    assert len(t) == EMBED_TEXT_MAX_CHARS


@mock.patch("app.contrib.google_bulk_embed._call_embed_with_retries")
def test_run_embed_happy_path(mock_api: Any) -> None:
    v = _vec()
    mock_api.return_value = [v, v, v]
    pids: list[str] = []
    with SessionLocal() as db:
        for n in range(3):
            pid = str(uuid4())
            pids.append(pid)
            db.add(
                Provider(
                    id=pid,
                    provider_name=f"P{n}",
                    category="c",
                    description="d",
                    source="google_bulk_import",
                )
            )
        db.commit()

    with SessionLocal() as db:
        c = run_embed(db, batch_size=10, dry_run=False)

    assert c.embedded == 3
    assert c.scanned == 3
    assert c.errors == 0
    mock_api.assert_called_once()
    with SessionLocal() as db:
        for pid in pids:
            p = db.query(Provider).filter(Provider.id == pid).one()
            assert p.embedding is not None
            assert len(p.embedding) == 1536


@mock.patch("app.contrib.google_bulk_embed._call_embed_with_retries")
def test_run_embed_skips_already_embedded(mock_api: Any) -> None:
    v = [0.1] * 1536
    pid_ok = str(uuid4())
    pid_new = str(uuid4())
    with SessionLocal() as db:
        db.add(
            Provider(
                id=pid_ok,
                provider_name="Has",
                category="a",
                description="b",
                source="seed",
                embedding=v,
            )
        )
        db.add(
            Provider(
                id=pid_new,
                provider_name="New",
                category="a",
                description="b",
                source="seed",
                embedding=None,
            )
        )
        db.commit()

    mock_api.return_value = [_vec()]  # one call for one row
    with SessionLocal() as db:
        c = run_embed(db, batch_size=10, dry_run=False)
    assert c.embedded == 1
    mock_api.assert_called_once()
    with SessionLocal() as db:
        a = db.query(Provider).filter(Provider.id == pid_ok).one()
        b = db.query(Provider).filter(Provider.id == pid_new).one()
        assert a.embedding == v
        assert b.embedding is not None


@mock.patch("app.contrib.google_bulk_embed._call_embed_with_retries")
def test_run_embed_dry_run_does_not_write(mock_api: Any) -> None:
    with SessionLocal() as db:
        for n in range(2):
            db.add(
                Provider(
                    id=str(uuid4()),
                    provider_name=f"D{n}",
                    category="c",
                    description="d",
                    source="seed",
                    embedding=None,
                )
            )
        db.commit()
    with SessionLocal() as db:
        c = run_embed(db, dry_run=True)
    assert c.scanned == 2
    assert c.embedded == 0
    mock_api.assert_not_called()
    with SessionLocal() as db:
        assert all(p.embedding is None for p in db.query(Provider).all())


@mock.patch("app.contrib.google_bulk_embed._embed_batch_for_texts_api")
def test_run_embed_handles_api_error_and_continues(mock_raw: Any) -> None:
    v = _vec()
    pids: list[str] = []
    with SessionLocal() as db:
        for n in range(3):
            pid = str(uuid4())
            pids.append(pid)
            db.add(
                Provider(
                    id=pid,
                    provider_name=f"E{n}",
                    category="c",
                    source="google_bulk_import",
                )
            )
        db.commit()

    mock_raw.side_effect = [RuntimeError("transient"), [v, v, v]]
    with SessionLocal() as db:
        c = run_embed(db, batch_size=50, dry_run=False)
    assert c.embedded == 3
    assert c.errors == 0
    assert mock_raw.call_count == 2
    with SessionLocal() as db:
        for pid in pids:
            p = db.query(Provider).filter(Provider.id == pid).one()
            assert p.embedding is not None


@mock.patch("app.contrib.google_bulk_embed._call_embed_with_retries")
def test_run_embed_name_only_fallback_counter(mock_api: Any, caplog: pytest.LogCaptureFixture) -> None:
    v = _vec()
    mock_api.return_value = [v]
    pid = str(uuid4())
    with SessionLocal() as db:
        db.add(
            Provider(
                id=pid,
                provider_name="OnlyName",
                category="",
                description=None,
                source="google_bulk_import",
            )
        )
        db.commit()
    with caplog.at_level(logging.WARNING):
        with SessionLocal() as db:
            c = run_embed(db, batch_size=5, dry_run=False)
    assert c.embedded == 1
    assert c.skipped_only_name == 1
    with SessionLocal() as db:
        p = db.query(Provider).one()
        assert p.embedding is not None
    assert "name-only" in caplog.text
