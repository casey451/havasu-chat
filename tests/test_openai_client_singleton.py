"""T2.3 — shared OpenAI client singleton (app/core/openai_client.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core import openai_client
from app.core.openai_client import get_openai_client, reset_openai_client_cache


def teardown_function() -> None:
    reset_openai_client_cache()


def test_real_class_is_cached_per_key(monkeypatch) -> None:
    built = []

    class FakeReal:
        def __init__(self, *, api_key, timeout):
            built.append((api_key, timeout))

    monkeypatch.setattr(openai_client, "_RealOpenAI", FakeReal)
    a = get_openai_client("k1", factory=FakeReal, timeout=30)
    b = get_openai_client("k1", factory=FakeReal, timeout=30)
    c = get_openai_client("k2", factory=FakeReal, timeout=30)
    assert a is b
    assert a is not c
    assert len(built) == 2


def test_fake_factory_bypasses_cache(monkeypatch) -> None:
    class FakeReal:
        def __init__(self, **kw): ...

    monkeypatch.setattr(openai_client, "_RealOpenAI", FakeReal)
    fake = MagicMock()
    r1 = get_openai_client("k", factory=fake, timeout=30)
    r2 = get_openai_client("k", factory=fake, timeout=30)
    assert fake.call_count == 2  # constructed per call, never cached
    assert r1 is fake.return_value and r2 is fake.return_value


def test_hint_extractor_seam_still_intercepts() -> None:
    """The PR #138 contract: patching hint_extractor.OpenAI intercepts construction."""
    from app.chat import hint_extractor

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="{}"))]
    )
    with patch.object(hint_extractor, "OpenAI", return_value=fake_client) as seam:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key", "HINT_GATE": "off"}):
            hint_extractor.extract_hints("my kid is 7 and we are near the island")
    assert seam.called or fake_client.chat.completions.create.called
