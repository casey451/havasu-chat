"""Shared LLM-mock helpers for integration tests.

Project-wide policy: ``docs/maintainability/llm_mock_pattern.md``.

The dominant pattern across integration tests is to mock OpenAI Chat Completions
at the ``app.core.llm_messages.OpenAI`` seam. Before this module existed, every
caller redefined the same two helpers (``_resp`` and ``_patched_openai``); they
now live here once. The leading-underscore module name signals "test-internal,
not for app code."

Usage (preferred, context-manager form)::

    from unittest.mock import patch
    import app.core.llm_messages as llm_messages
    from tests._llm_mocks import patched_openai_client

    def test_something(monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        fake = patched_openai_client("expected LLM voice text")
        with patch.object(llm_messages, "OpenAI", return_value=fake):
            # exercise code under test
            ...

Always set ``OPENAI_API_KEY`` to a non-empty test value before patching.
``app/core/llm_messages.py:118-120`` short-circuits to ``None`` when the key is
unset, so without the env var the patched class is never reached and the test
asserts the *fallback* shape rather than the LLM-coupled contract.

For multi-call tests (e.g. parser + formatter), use ``MagicMock(side_effect=
[resp1, resp2])`` directly with ``build_chat_completion_response`` for each
response. Don't extend ``patched_openai_client`` to take a list — keep the
simple case simple.

Different patch target? ``test_llm_cache.py`` patches ``llm_cache.OpenAI``, not
``llm_messages.OpenAI``, because the cache module imports ``OpenAI`` directly
for the cache-key embedding path. The response-shape helper still applies; only
the patch target differs. This is intentional — see policy doc §3.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


def build_chat_completion_response(
    text: str,
    *,
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> SimpleNamespace:
    """Build the OpenAI Chat Completions response shape that production reads.

    Mirrors what ``app.core.llm_messages.call_anthropic_messages`` extracts:
    ``resp.choices[0].message.content`` for the text body and
    ``resp.usage.{prompt_tokens,completion_tokens}`` for the token counts.

    ``cache_*`` token counts are not surfaced — production zeroes them out
    in ``Usage.from_sdk_usage`` (see the docstring on that classmethod).
    """
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    return SimpleNamespace(choices=[choice], usage=usage)


def patched_openai_client(
    text: str,
    *,
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> MagicMock:
    """Return a configured ``MagicMock`` ready to drop into ``return_value=``.

    The mock's ``.chat.completions.create`` call returns the response built by
    :func:`build_chat_completion_response`. Drop directly into a
    ``patch.object(llm_messages, "OpenAI", return_value=...)`` block.

    To assert what the production code passed to OpenAI, inspect
    ``fake.chat.completions.create.call_args`` after the call. The
    ``messages`` kwarg is the system+user payload — useful for pinning that
    catalog context (e.g. confidence-tier hedges) reaches the LLM.
    """
    fake = MagicMock()
    fake.chat.completions.create.return_value = build_chat_completion_response(
        text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    return fake
