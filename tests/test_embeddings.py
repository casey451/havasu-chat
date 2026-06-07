"""Provider-routed embeddings abstraction (HANDOFF #3).

The ``OpenAI`` symbol in ``app.core.embeddings`` is the patchable seam (the
autouse conftest blocker replaces it with a no-network stand-in; tests that want
a working client re-patch it locally).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core import embeddings


def _resp(vec: list[float]) -> SimpleNamespace:
    return SimpleNamespace(data=[SimpleNamespace(embedding=vec)])


# --- provider resolution ----------------------------------------------------


def test_provider_defaults_to_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMBEDDINGS_PROVIDER", raising=False)
    assert embeddings.provider() == "openai"


@pytest.mark.parametrize("val", ["local", "LOCAL", " local "])
def test_provider_recognizes_local(monkeypatch: pytest.MonkeyPatch, val: str) -> None:
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", val)
    assert embeddings.provider() == "local"


def test_provider_invalid_falls_back_to_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "banana")
    assert embeddings.provider() == "openai"


# --- empty / guard rails ----------------------------------------------------


def test_embed_empty_returns_none() -> None:
    assert embeddings.embed("") is None
    assert embeddings.embed("   ") is None


def test_embed_openai_missing_key_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMBEDDINGS_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert embeddings.embed("hello") is None


def test_embed_blocked_construction_degrades_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # Key present but the autouse no-network OpenAI raises on construction; embed
    # must catch and return None (best-effort contract), not raise.
    monkeypatch.delenv("EMBEDDINGS_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert embeddings.embed("hello") is None


# --- openai provider --------------------------------------------------------


def test_embed_openai_returns_floats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMBEDDINGS_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    client = MagicMock()
    client.embeddings.create.return_value = _resp([0.1, 0.2, 0.3])
    with patch.object(embeddings, "OpenAI", return_value=client):
        out = embeddings.embed("hello world")
    assert out == [0.1, 0.2, 0.3]
    kw = client.embeddings.create.call_args.kwargs
    assert kw["model"] == embeddings.DEFAULT_OPENAI_MODEL
    assert kw["input"] == "hello world"


def test_embed_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMBEDDINGS_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDINGS_MODEL", "text-embedding-3-large")
    client = MagicMock()
    client.embeddings.create.return_value = _resp([1.0])
    with patch.object(embeddings, "OpenAI", return_value=client):
        embeddings.embed("hi")
    assert client.embeddings.create.call_args.kwargs["model"] == "text-embedding-3-large"


def test_embed_openai_swallows_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMBEDDINGS_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    client = MagicMock()
    client.embeddings.create.side_effect = RuntimeError("network")
    with patch.object(embeddings, "OpenAI", return_value=client):
        assert embeddings.embed("hi") is None


def test_embed_malformed_response_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMBEDDINGS_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    client = MagicMock()
    client.embeddings.create.return_value = SimpleNamespace(data=[])
    with patch.object(embeddings, "OpenAI", return_value=client):
        assert embeddings.embed("hi") is None


# --- local provider ---------------------------------------------------------


def test_embed_local_uses_base_url_and_default_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDINGS_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.delenv("EMBEDDINGS_MODEL", raising=False)
    client = MagicMock()
    client.embeddings.create.return_value = _resp([0.5, 0.6])
    factory = MagicMock(return_value=client)
    with patch.object(embeddings, "OpenAI", factory):
        out = embeddings.embed("hola")
    assert out == [0.5, 0.6]
    # Constructed against the local endpoint with the local default model.
    assert factory.call_args.kwargs["base_url"] == "http://127.0.0.1:11434/v1"
    assert client.embeddings.create.call_args.kwargs["model"] == embeddings.DEFAULT_LOCAL_MODEL


def test_embed_local_missing_base_url_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "local")
    monkeypatch.delenv("EMBEDDINGS_BASE_URL", raising=False)
    assert embeddings.embed("hola") is None
