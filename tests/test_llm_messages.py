"""Tests for ``app.core.llm_messages`` — Anthropic client patched via ``app.core.llm_messages.anthropic``."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.core.llm_messages as llm_messages
from app.core.llm_http import LLM_CLIENT_READ_TIMEOUT_SEC
from app.core.llm_messages import (
    Usage,
    _extract_text_from_message,
    call_anthropic_messages,
    coerce_llm_text_to_json_object,
    load_prompt,
)


def _msg(text: str, usage: SimpleNamespace | None = None) -> SimpleNamespace:
    block = SimpleNamespace(type="text", text=text)
    u = usage or SimpleNamespace(
        input_tokens=10,
        output_tokens=5,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(content=[block], usage=u)


# --- _extract_text_from_message ---


def test_extract_text_empty_content() -> None:
    msg = SimpleNamespace(content=[])
    assert _extract_text_from_message(msg) == ""


def test_extract_text_single_block() -> None:
    msg = SimpleNamespace(content=[SimpleNamespace(type="text", text="hello")])
    assert _extract_text_from_message(msg) == "hello"


def test_extract_text_multiple_blocks_joined() -> None:
    msg = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="a"),
            SimpleNamespace(type="text", text="b"),
        ]
    )
    assert _extract_text_from_message(msg) == "a b"


def test_extract_text_skips_non_text_blocks() -> None:
    msg = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="keep"),
            SimpleNamespace(type="image", text="ignored"),
            SimpleNamespace(type="text", text="me"),
        ]
    )
    assert _extract_text_from_message(msg) == "keep me"


# --- Usage.from_sdk_usage ---


def test_usage_from_sdk_none() -> None:
    u = Usage.from_sdk_usage(None)
    assert u == Usage(0, 0, 0, 0)


def test_usage_from_sdk_all_fields_nonzero() -> None:
    sdk = SimpleNamespace(
        input_tokens=1,
        output_tokens=2,
        cache_read_input_tokens=3,
        cache_creation_input_tokens=4,
    )
    u = Usage.from_sdk_usage(sdk)
    assert u.input_tokens == 1
    assert u.output_tokens == 2
    assert u.cache_read_input_tokens == 3
    assert u.cache_creation_input_tokens == 4
    assert u.billable_input == 1 + 3 + 4


def test_usage_from_sdk_missing_input_tokens_defaults_zero() -> None:
    sdk = SimpleNamespace(
        output_tokens=2,
        cache_read_input_tokens=3,
        cache_creation_input_tokens=4,
    )
    u = Usage.from_sdk_usage(sdk)
    assert u.input_tokens == 0
    assert u.output_tokens == 2
    assert u.cache_read_input_tokens == 3
    assert u.cache_creation_input_tokens == 4


def test_usage_from_sdk_missing_output_tokens_defaults_zero() -> None:
    sdk = SimpleNamespace(
        input_tokens=1,
        cache_read_input_tokens=3,
        cache_creation_input_tokens=4,
    )
    u = Usage.from_sdk_usage(sdk)
    assert u.input_tokens == 1
    assert u.output_tokens == 0
    assert u.cache_read_input_tokens == 3
    assert u.cache_creation_input_tokens == 4


def test_usage_from_sdk_missing_cache_read_defaults_zero() -> None:
    sdk = SimpleNamespace(
        input_tokens=1,
        output_tokens=2,
        cache_creation_input_tokens=4,
    )
    u = Usage.from_sdk_usage(sdk)
    assert u.input_tokens == 1
    assert u.output_tokens == 2
    assert u.cache_read_input_tokens == 0
    assert u.cache_creation_input_tokens == 4


def test_usage_from_sdk_missing_cache_creation_defaults_zero() -> None:
    sdk = SimpleNamespace(
        input_tokens=1,
        output_tokens=2,
        cache_read_input_tokens=3,
    )
    u = Usage.from_sdk_usage(sdk)
    assert u.input_tokens == 1
    assert u.output_tokens == 2
    assert u.cache_read_input_tokens == 3
    assert u.cache_creation_input_tokens == 0


# --- coerce_llm_text_to_json_object ---


def test_coerce_plain_json_object() -> None:
    assert coerce_llm_text_to_json_object('{"a": 1}') == {"a": 1}


def test_coerce_fenced_json_object() -> None:
    raw = "```\n{\"a\": 1}\n```"
    assert coerce_llm_text_to_json_object(raw) == {"a": 1}


def test_coerce_fenced_with_json_language_tag() -> None:
    raw = "```json\n{\"a\": 1}\n```"
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


@pytest.fixture
def anthropic_available() -> None:
    if llm_messages.anthropic is None:
        pytest.skip("anthropic package not installed")


def test_call_anthropic_messages_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    anthropic_available: None,
) -> None:
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> SimpleNamespace:
        captured["create_kwargs"] = kwargs
        return _msg(
            "hello",
            SimpleNamespace(
                input_tokens=100,
                output_tokens=20,
                cache_read_input_tokens=1,
                cache_creation_input_tokens=2,
            ),
        )

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = fake_create

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch.object(llm_messages.anthropic, "Anthropic", return_value=fake_client) as anth_ctor:
        out = call_anthropic_messages(
            system_prompt="SYS",
            user_text="USER",
            max_tokens=99,
            temperature=0.5,
            model="custom-model",
        )

    anth_ctor.assert_called_once_with(api_key="test-key", timeout=LLM_CLIENT_READ_TIMEOUT_SEC)
    assert out is not None
    assert out.text == "hello"
    assert out.usage == Usage(100, 20, 1, 2)
    assert out.raw is not None

    kw = captured["create_kwargs"]
    assert set(kw.keys()) == {"model", "max_tokens", "temperature", "system", "messages"}
    assert kw["model"] == "custom-model"
    assert kw["max_tokens"] == 99
    assert kw["temperature"] == 0.5
    assert kw["system"] == [
        {"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}},
    ]
    assert kw["messages"] == [{"role": "user", "content": "USER"}]


def test_call_anthropic_messages_no_api_key_unset(monkeypatch: pytest.MonkeyPatch, anthropic_available: None) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ctor = MagicMock()
    with patch.object(llm_messages.anthropic, "Anthropic", ctor):
        assert call_anthropic_messages(
            system_prompt="s",
            user_text="u",
            max_tokens=1,
            temperature=0.0,
        ) is None
    ctor.assert_not_called()


def test_call_anthropic_messages_no_api_key_empty(monkeypatch: pytest.MonkeyPatch, anthropic_available: None) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    ctor = MagicMock()
    with patch.object(llm_messages.anthropic, "Anthropic", ctor):
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


def test_call_anthropic_messages_anthropic_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(llm_messages, "anthropic", None)
    assert (
        call_anthropic_messages(
            system_prompt="s",
            user_text="u",
            max_tokens=1,
            temperature=0.0,
        )
        is None
    )


def test_call_anthropic_messages_create_raises(
    monkeypatch: pytest.MonkeyPatch,
    anthropic_available: None,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("boom")
    with patch.object(llm_messages.anthropic, "Anthropic", return_value=fake_client):
        assert (
            call_anthropic_messages(
                system_prompt="s",
                user_text="u",
                max_tokens=1,
                temperature=0.0,
            )
            is None
        )


def test_call_anthropic_messages_empty_text_response(
    monkeypatch: pytest.MonkeyPatch,
    anthropic_available: None,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _msg("")
    with patch.object(llm_messages.anthropic, "Anthropic", return_value=fake_client):
        assert (
            call_anthropic_messages(
                system_prompt="s",
                user_text="u",
                max_tokens=1,
                temperature=0.0,
            )
            is None
        )


def test_call_anthropic_messages_model_explicit_wins_over_env(
    monkeypatch: pytest.MonkeyPatch,
    anthropic_available: None,
) -> None:
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> SimpleNamespace:
        captured["model"] = kwargs["model"]
        return _msg("ok")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_MODEL", "from-env")
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = fake_create
    with patch.object(llm_messages.anthropic, "Anthropic", return_value=fake_client):
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
    anthropic_available: None,
) -> None:
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> SimpleNamespace:
        captured["model"] = kwargs["model"]
        return _msg("ok")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_MODEL", "env-model")
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = fake_create
    with patch.object(llm_messages.anthropic, "Anthropic", return_value=fake_client):
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
    anthropic_available: None,
) -> None:
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> SimpleNamespace:
        captured["model"] = kwargs["model"]
        return _msg("ok")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_MODEL", "")
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = fake_create
    with patch.object(llm_messages.anthropic, "Anthropic", return_value=fake_client):
        call_anthropic_messages(
            system_prompt="s",
            user_text="u",
            max_tokens=1,
            temperature=0.0,
            model=None,
        )
    assert captured["model"] == llm_messages.DEFAULT_MODEL


def test_call_anthropic_messages_model_default_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
    anthropic_available: None,
) -> None:
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> SimpleNamespace:
        captured["model"] = kwargs["model"]
        return _msg("ok")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = fake_create
    with patch.object(llm_messages.anthropic, "Anthropic", return_value=fake_client):
        call_anthropic_messages(
            system_prompt="s",
            user_text="u",
            max_tokens=1,
            temperature=0.0,
            model=None,
        )
    assert captured["model"] == llm_messages.DEFAULT_MODEL
