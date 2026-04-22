"""Phase 8.7 — privacy page, Sentry scrubbing, diagnostic gating, hint log redaction."""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app, scrub_sentry_breadcrumb, scrub_sentry_event


def test_scrub_sentry_event_scrubs_api_chat_request_body() -> None:
    event: dict = {
        "request": {
            "url": "https://example.com/api/chat",
            "method": "POST",
            "data": '{"query":"SECRET_QUERY","session_id":"x"}',
        }
    }
    out = scrub_sentry_event(event, {})
    assert out is not None
    assert out["request"]["data"] == "<scrubbed>"
    assert "SECRET_QUERY" not in json.dumps(out)


def test_scrub_sentry_event_scrubs_chat_path() -> None:
    event: dict = {
        "request": {
            "url": "http://localhost:8000/chat",
            "data": '{"message":"M1","session_id":"s"}',
        }
    }
    out = scrub_sentry_event(event, {})
    assert out["request"]["data"] == "<scrubbed>"


def test_scrub_sentry_event_scrubs_sensitive_extra_keys() -> None:
    event: dict = {
        "request": {"url": "http://x/health"},
        "extra": {"query": "SHOULD_SCRUB", "ok": 1},
    }
    out = scrub_sentry_event(event, {})
    assert out["extra"]["query"] == "<scrubbed>"
    assert out["extra"]["ok"] == 1


def test_scrub_sentry_breadcrumb_scrubs_body_like_data() -> None:
    crumb: dict = {"category": "httplib", "data": {"body": '{"message":"X"}', "method": "POST"}}
    out = scrub_sentry_breadcrumb(crumb, {})
    assert out is not None
    assert out["data"]["body"] == "<scrubbed>"


@pytest.mark.parametrize(
    "raw_val",
    ["", "0", "false", "no", "FALSE"],
)
def test_is_search_diag_verbose_false(monkeypatch: pytest.MonkeyPatch, raw_val: str) -> None:
    monkeypatch.setenv("SEARCH_DIAG_VERBOSE", raw_val)
    from app.core.search_log import is_search_diag_verbose

    assert is_search_diag_verbose() is False


@pytest.mark.parametrize("raw_val", ["true", "1", "yes", "TRUE"])
def test_is_search_diag_verbose_true(monkeypatch: pytest.MonkeyPatch, raw_val: str) -> None:
    monkeypatch.setenv("SEARCH_DIAG_VERBOSE", raw_val)
    from app.core import search_log as sl

    assert sl.is_search_diag_verbose() is True


def test_search_log_skips_when_not_verbose(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEARCH_DIAG_VERBOSE", raising=False)
    from app.core import search_log as sl

    sl._log.handlers.clear()
    mock_log = MagicMock()
    with patch.object(sl, "_log", mock_log):
        sl.log_query("secret", "SEARCH_EVENTS", {}, "RUN_BROAD")
    mock_log.info.assert_not_called()


def test_search_log_writes_when_verbose(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verbose mode must emit search_diag log records (file sink is OS-buffered in CI)."""
    monkeypatch.setenv("SEARCH_DIAG_VERBOSE", "true")
    from app.core import search_log as sl

    sl._log.handlers.clear()
    assert sl.is_search_diag_verbose() is True
    assert not isinstance(sl._log, MagicMock), "search_diag logger must not stay mocked between tests"
    with patch.object(sl._log, "info") as info:
        sl.log_query("hello", "SEARCH_EVENTS", {"a": 1}, "RUN_BROAD")
    assert info.call_count >= 2
    joined = " ".join(" ".join(str(a) for a in (c.args or ())) for c in info.call_args_list)
    assert "hello" in joined
    assert "SEARCH_EVENTS" in joined


def test_emit_search_diag_embedding_block_respects_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEARCH_DIAG_VERBOSE", raising=False)
    printed: list[str] = []

    def _capture(*args: object, **kwargs: object) -> None:
        printed.extend(str(a) for a in args)

    monkeypatch.setattr("builtins.print", _capture)
    from app.core.search import emit_search_diag_embedding_block

    class _Ev:
        title = "E1"

    emit_search_diag_embedding_block(
        "TOP_SECRET",
        is_specific_query=False,
        embedding_from_openai=True,
        effective_threshold=0.35,
        with_emb=[(_Ev(), 0.5)],
    )
    assert printed == []


def test_emit_search_diag_embedding_block_prints_when_verbose(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARCH_DIAG_VERBOSE", "true")
    printed: list[str] = []

    def _capture(*args: object, **kwargs: object) -> None:
        printed.extend(str(a) for a in args)

    monkeypatch.setattr("builtins.print", _capture)
    from app.core.search import emit_search_diag_embedding_block

    class _Ev:
        title = "E1"

    emit_search_diag_embedding_block(
        "visible",
        is_specific_query=True,
        embedding_from_openai=True,
        effective_threshold=0.55,
        with_emb=[(_Ev(), 0.9)],
    )
    blob = "\n".join(printed)
    assert "[search_diag]" in blob
    assert "visible" in blob


def test_privacy_route_200_and_markers() -> None:
    with TestClient(app) as client:
        r = client.get("/privacy")
    assert r.status_code == 200
    body = r.text
    assert "caseylsolomon@gmail.com" in body
    assert "What we collect" in body
    assert "Anthropic" in body
    assert "<!-- TODO: replace caseylsolomon@gmail.com" in body


def test_terms_route_200_and_markers() -> None:
    with TestClient(app) as client:
        r = client.get("/terms")
    assert r.status_code == 200
    body = r.text
    assert "Terms of Service for Havasu Chat" in body
    assert "1. Acceptance" in body
    assert "<!-- TODO: for public US launch, evaluate DMCA 512 agent" in body


def test_index_includes_privacy_footer_link() -> None:
    with TestClient(app) as client:
        r = client.get("/")
    assert r.status_code == 200
    assert 'href="/privacy"' in r.text
    assert 'href="/terms"' in r.text
    assert "Privacy" in r.text
    assert "Terms" in r.text


def test_hint_extractor_validation_failure_logs_no_raw_json(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    import logging

    from app.chat import hint_extractor as he

    bad_json = '{"extracted_hints": "not-an-object"}'

    class _Msg:
        content = bad_json

    class _Choice:
        message = _Msg()

    class _Completion:
        choices = [_Choice()]
        usage = None

    class _Client:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        class chat:
            class completions:
                @staticmethod
                def create(*a: object, **k: object) -> object:
                    return _Completion()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(he, "OpenAI", _Client)
    caplog.set_level(logging.INFO, logger="root")
    with caplog.at_level(logging.INFO):
        assert he.extract_hints("user said something unique xyz123") is None
    joined = caplog.text + "".join(str(r.getMessage()) for r in caplog.records)
    assert "xyz123" not in joined
    assert "not-an-object" not in joined
    assert "raw length=" in joined.lower() or "envelope validation failed" in joined.lower()
