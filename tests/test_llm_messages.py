"""Tests for ``app.core.llm_messages`` with the OpenAI client patched in-place."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.core.llm_messages as llm_messages
from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC
from app.core.llm_messages import (
    DEFAULT_MODEL,
    Usage,
    call_anthropic_messages,
    coerce_llm_text_to_json_object,
    load_prompt,
)


def _resp(text: str, usage: SimpleNamespace | None = None) -> SimpleNamespace:
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    u = usage or SimpleNamespace(prompt_tokens=10, completion_tokens=5)
    return SimpleNamespace(choices=[choice], usage=u)


# --- Usage.from_sdk_usage ---


def test_usage_from_sdk_none() -> None:
    u = Usage.from_sdk_usage(None)
    assert u == Usage(0, 0, 0, 0)


def test_usage_from_sdk_openai_prompt_and_completion_tokens() -> None:
    sdk = SimpleNamespace(prompt_tokens=100, completion_tokens=20)
    u = Usage.from_sdk_usage(sdk)
    assert u.input_tokens == 100
    assert u.output_tokens == 20
    assert u.cache_read_input_tokens == 0
    assert u.cache_creation_input_tokens == 0
    assert u.billable_input == 100


def test_usage_from_sdk_missing_prompt_tokens_defaults_zero() -> None:
    sdk = SimpleNamespace(completion_tokens=2)
    u = Usage.from_sdk_usage(sdk)
    assert u.input_tokens == 0
    assert u.output_tokens == 2
    assert u.cache_read_input_tokens == 0
    assert u.cache_creation_input_tokens == 0


def test_usage_from_sdk_missing_completion_tokens_defaults_zero() -> None:
    sdk = SimpleNamespace(prompt_tokens=1)
    u = Usage.from_sdk_usage(sdk)
    assert u.input_tokens == 1
    assert u.output_tokens == 0
    assert u.cache_read_input_tokens == 0
    assert u.cache_creation_input_tokens == 0


def test_usage_from_sdk_ignores_openai_cached_token_details() -> None:
    sdk = SimpleNamespace(
        prompt_tokens=10,
        completion_tokens=5,
        prompt_tokens_details=SimpleNamespace(cached_tokens=3),
    )
    u = Usage.from_sdk_usage(sdk)
    assert u == Usage(10, 5, 0, 0)
    assert u.billable_input == 10


# --- coerce_llm_text_to_json_object ---


def test_coerce_plain_json_object() -> None:
    assert coerce_llm_text_to_json_object('{"a": 1}') == {"a": 1}


def test_coerce_fenced_json_object() -> None:
    raw = '```\n{"a": 1}\n```'
    assert coerce_llm_text_to_json_object(raw) == {"a": 1}


def test_coerce_fenced_with_json_language_tag() -> None:
    raw = '```json\n{"a": 1}\n```'
    assert coerce_llm_text_to_json_object(raw) == {"a": 1}


def test_coerce_non_object_json_returns_none() -> None:
    assert coerce_llm_text_to_json_object("[1, 2]") is None
    assert coerce_llm_text_to_json_object('"str"') is None
    assert coerce_llm_text_to_json_object("42") is None


def test_coerce_malformed_returns_none() -> None:
    assert coerce_llm_text_to_json_object("{not json") is None


# --- load_prompt ---


def test_load_prompt_reads_existing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path
    pdir = root / "prompts"
    pdir.mkdir()
    (pdir / "h2_llm_messages_probe.txt").write_text("  body\n  ", encoding="utf-8")
    fake_py = root / "app" / "core" / "llm_messages.py"
    fake_py.parent.mkdir(parents=True)
    fake_py.touch()
    monkeypatch.setattr(llm_messages, "__file__", str(fake_py))
    assert load_prompt("h2_llm_messages_probe") == "body"


def test_load_prompt_missing_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path
    fake_py = root / "app" / "core" / "llm_messages.py"
    fake_py.parent.mkdir(parents=True)
    fake_py.touch()
    monkeypatch.setattr(llm_messages, "__file__", str(fake_py))
    with pytest.raises(FileNotFoundError):
        load_prompt("definitely_missing_prompt_xyz")


# --- call_anthropic_messages ---


def test_call_anthropic_messages_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> SimpleNamespace:
        captured["create_kwargs"] = kwargs
        return _resp(
            "hello",
            SimpleNamespace(prompt_tokens=100, completion_tokens=20),
        )

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = fake_create

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake_client) as openai_ctor:
        out = call_anthropic_messages(
            system_prompt="SYS",
            user_text="USER",
            max_tokens=99,
            temperature=0.5,
            model="custom-model",
        )

    openai_ctor.assert_called_once_with(api_key="test-key", timeout=LLM_CLIENT_READ_TIMEOUT_SEC)
    assert out is not None
    assert out.text == "hello"
    assert out.usage == Usage(100, 20, 0, 0)
    assert out.raw is not None

    kw = captured["create_kwargs"]
    assert set(kw.keys()) == {"model", "max_tokens", "temperature", "messages"}
    assert kw["model"] == "custom-model"
    assert kw["max_tokens"] == 99
    assert kw["temperature"] == 0.5
    assert kw["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USER"},
    ]


def test_call_anthropic_messages_no_api_key_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ctor = MagicMock()
    with patch.object(llm_messages, "OpenAI", ctor):
        assert (
            call_anthropic_messages(
                system_prompt="s",
                user_text="u",
                max_tokens=1,
                temperature=0.0,
            )
            is None
        )
    ctor.assert_not_called()


def test_call_anthropic_messages_no_api_key_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    ctor = MagicMock()
    with patch.object(llm_messages, "OpenAI", ctor):
        assert (
            call_anthropic_messages(
                system_prompt="s",
                user_text="u",
                max_tokens=1,
                temperature=0.0,
            )
            is None
        )
    ctor.assert_not_called()


def test_call_anthropic_messages_openai_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setattr(llm_messages, "OpenAI", None)
    assert (
        call_anthropic_messages(
            system_prompt="s",
            user_text="u",
            max_tokens=1,
            temperature=0.0,
        )
        is None
    )


def test_call_anthropic_messages_create_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = RuntimeError("boom")
    with patch.object(llm_messages, "OpenAI", return_value=fake_client):
        assert (
            call_anthropic_messages(
                system_prompt="s",
                user_text="u",
                max_tokens=1,
                temperature=0.0,
            )
            is None
        )


def test_call_anthropic_messages_empty_text_returns_result_with_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    fake_resp = _resp(
        "",
        SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_resp
    with patch.object(llm_messages, "OpenAI", return_value=fake_client):
        out = call_anthropic_messages(
            system_prompt="s",
            user_text="u",
            max_tokens=1,
            temperature=0.0,
        )
    assert out is not None
    assert out.text == ""
    assert out.usage == Usage(10, 5, 0, 0)
    assert out.raw is fake_resp


def test_call_anthropic_messages_missing_choices_returns_empty_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    fake_resp = SimpleNamespace(
        choices=[], usage=SimpleNamespace(prompt_tokens=11, completion_tokens=22)
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_resp
    with patch.object(llm_messages, "OpenAI", return_value=fake_client):
        out = call_anthropic_messages(
            system_prompt="s",
            user_text="u",
            max_tokens=1,
            temperature=0.0,
        )
    assert out is not None
    assert out.text == ""
    assert out.usage == Usage(11, 22, 0, 0)
    assert out.raw is fake_resp


def test_call_anthropic_messages_model_explicit_wins_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> SimpleNamespace:
        captured["model"] = kwargs["model"]
        return _resp("ok")

    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_MODEL", "from-env")
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = fake_create
    with patch.object(llm_messages, "OpenAI", return_value=fake_client):
        call_anthropic_messages(
            system_prompt="s",
            user_text="u",
            max_tokens=1,
            temperature=0.0,
            model="from-arg",
        )
    assert captured["model"] == "from-arg"


def test_call_anthropic_messages_model_from_env_when_arg_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> SimpleNamespace:
        captured["model"] = kwargs["model"]
        return _resp("ok")

    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = fake_create
    with patch.object(llm_messages, "OpenAI", return_value=fake_client):
        call_anthropic_messages(
            system_prompt="s",
            user_text="u",
            max_tokens=1,
            temperature=0.0,
            model=None,
        )
    assert captured["model"] == "env-model"


def test_call_anthropic_messages_model_default_when_env_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> SimpleNamespace:
        captured["model"] = kwargs["model"]
        return _resp("ok")

    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_MODEL", "")
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = fake_create
    with patch.object(llm_messages, "OpenAI", return_value=fake_client):
        call_anthropic_messages(
            system_prompt="s",
            user_text="u",
            max_tokens=1,
            temperature=0.0,
            model=None,
        )
    assert captured["model"] == DEFAULT_MODEL


def test_call_anthropic_messages_model_default_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> SimpleNamespace:
        captured["model"] = kwargs["model"]
        return _resp("ok")

    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = fake_create
    with patch.object(llm_messages, "OpenAI", return_value=fake_client):
        call_anthropic_messages(
            system_prompt="s",
            user_text="u",
            max_tokens=1,
            temperature=0.0,
            model=None,
        )
    assert captured["model"] == DEFAULT_MODEL
