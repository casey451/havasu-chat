"""Integration tests for the confidence-tier classifier wired into Tier 2 (Lane CT2.A)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.core.llm_messages as llm_messages
from app.chat import tier2_formatter as tf
from app.core.timezone import now_lake_havasu


def _resp(text, *, prompt_tokens=120, completion_tokens=40):
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


def _provider_row(
    *,
    name="Acme Plumbing",
    phone="(928) 855-1234",
    age_days=1,
    method="owner_confirmed",
    include_verification=True,
):
    row = {
        "type": "provider",
        "id": f"prov-{name.lower().replace(' ', '-')}",
        "name": name,
        "phone": phone,
        "description": "",
        "tags": [],
    }
    if include_verification:
        row["last_verified_at"] = now_lake_havasu() - timedelta(days=age_days)
        row["verification_method"] = method
    return row


def _json_safe_row(row):
    return {k: v for k, v in row.items() if k not in {"last_verified_at", "verification_method"}}


def _user_text(fake):
    return fake.chat.completions.create.call_args.kwargs["messages"][1]["content"]


# 1. flag default off
def test_flag_off_byte_identical_to_current_behavior(monkeypatch):
    monkeypatch.delenv(tf.FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR, raising=False)
    rows = [
        _json_safe_row(
            _provider_row(
                name="Acme Plumbing", phone="(928) 855-1234", age_days=1, method="owner_confirmed"
            )
        ),
        _json_safe_row(
            _provider_row(
                name="Bayview Plumbing", phone="(928) 855-5678", age_days=200, method="manual"
            )
        ),
    ]
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(
        "Acme Plumbing at (928) 855-1234 or Bayview Plumbing at (928) 855-5678."
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _ = tf.format("who's a good plumber", rows)
    user_text = _user_text(fake)
    assert "confidence_hint" not in user_text
    assert "confidence_hedge" not in user_text
    assert "Their listed number is" not in (text or "")
    assert text == "Acme Plumbing at (928) 855-1234 or Bayview Plumbing at (928) 855-5678."


# 2. HIGH tier
def test_flag_on_high_tier_no_hedge_in_prompt(monkeypatch):
    monkeypatch.setenv(tf.FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR, "true")
    rows = [
        _provider_row(
            name="Acme Plumbing", phone="(928) 855-1234", age_days=1, method="owner_confirmed"
        )
    ]
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(
        "Acme Plumbing at (928) 855-1234 is a solid pick."
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _ = tf.format("who's a good plumber", rows)
    user_text = _user_text(fake)
    assert '"confidence_hint":"high"' in user_text
    assert '"confidence_hedge":""' in user_text
    assert "recommend calling to confirm" not in (text or "")
    assert "as of last week" not in (text or "")


# 3. MEDIUM tier
def test_flag_on_medium_tier_hedge_inlined(monkeypatch):
    monkeypatch.setenv(tf.FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR, "true")
    rows = [
        _provider_row(
            name="Bayview Plumbing", phone="(928) 855-5678", age_days=14, method="scraper"
        )
    ]
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(
        "Bayview Plumbing at (928) 855-5678 -- as of last week."
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _ = tf.format("who's a good plumber", rows)
    user_text = _user_text(fake)
    assert '"confidence_hint":"medium"' in user_text
    assert '"confidence_hedge":"as of last week"' in user_text
    assert "as of last week" in (text or "")


# 4. LOW tier
def test_flag_on_low_tier_hedge_inlined(monkeypatch):
    monkeypatch.setenv(tf.FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR, "true")
    rows = [
        _provider_row(
            name="Bayview Plumbing", phone="(928) 855-5678", age_days=200, method="manual"
        )
    ]
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(
        "Bayview Plumbing at (928) 855-5678 -- recommend calling to confirm."
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _ = tf.format("who's a good plumber", rows)
    user_text = _user_text(fake)
    assert '"confidence_hint":"low"' in user_text
    assert '"confidence_hedge":"recommend calling to confirm"' in user_text
    assert "recommend calling to confirm" in (text or "")


# 5. LOW phone post-process appends
def test_flag_on_low_tier_phone_post_process_appends_when_missing(monkeypatch):
    monkeypatch.setenv(tf.FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR, "true")
    rows = [
        _provider_row(
            name="Bayview Plumbing", phone="(928) 855-5678", age_days=200, method="manual"
        )
    ]
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp("Bayview Plumbing's a name we have on file.")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _ = tf.format("who's a good plumber", rows)
        text = tf.postprocess(text, rows)
    assert text is not None
    assert "Their listed number is (928) 855-5678" in text
    assert "recommend calling to confirm" in text


# 6. LOW phone post-process skips when phone present
def test_flag_on_low_tier_phone_post_process_skips_when_present(monkeypatch):
    monkeypatch.setenv(tf.FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR, "true")
    rows = [
        _provider_row(
            name="Bayview Plumbing", phone="(928) 855-5678", age_days=200, method="manual"
        )
    ]
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(
        "Bayview Plumbing at (928) 855-5678 is on file."
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _ = tf.format("who's a good plumber", rows)
        text = tf.postprocess(text, rows)
    assert text is not None
    assert text.count("(928) 855-5678") == 1
    assert "Their listed number is" not in text


# 7. LOW post-process skips when already hedged
def test_flag_on_low_tier_phone_post_process_skips_when_already_hedged(monkeypatch):
    monkeypatch.setenv(tf.FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR, "true")
    rows = [
        _provider_row(
            name="Bayview Plumbing", phone="(928) 855-5678", age_days=200, method="manual"
        )
    ]
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(
        "Bayview Plumbing -- recommend calling to confirm."
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _ = tf.format("who's a good plumber", rows)
        text = tf.postprocess(text, rows)
    assert text is not None
    assert text.count("recommend calling to confirm") == 1
    assert "Their listed number is" not in text


# 8. legacy row without verification
def test_legacy_row_without_verification_fields_classifies_low(monkeypatch):
    monkeypatch.setenv(tf.FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR, "true")
    legacy_row = _provider_row(
        name="Old School Plumbing", phone="(928) 555-0001", include_verification=False
    )
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(
        "Old School Plumbing -- recommend calling to confirm."
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _ = tf.format("who's a good plumber", [legacy_row])
    user_text = _user_text(fake)
    assert '"confidence_hint":"low"' in user_text
    assert '"confidence_hedge":"recommend calling to confirm"' in user_text
    assert "recommend calling to confirm" in (text or "")


# 9. mixed-tier rows
def test_mixed_tier_rows_in_one_response(monkeypatch):
    monkeypatch.setenv(tf.FEATURE_FLAG_CONFIDENCE_TIER_ENV_VAR, "true")
    rows = [
        _provider_row(
            name="Acme Plumbing", phone="(928) 855-1111", age_days=1, method="owner_confirmed"
        ),
        _provider_row(
            name="Bayview Plumbing", phone="(928) 855-2222", age_days=14, method="scraper"
        ),
        _provider_row(
            name="Crestline Plumbing", phone="(928) 855-3333", age_days=200, method="manual"
        ),
    ]
    fake = MagicMock()
    fake.chat.completions.create.return_value = _resp(
        "Acme Plumbing at (928) 855-1111. "
        "Bayview Plumbing at (928) 855-2222 -- as of last week. "
        "Crestline Plumbing at (928) 855-3333 -- recommend calling to confirm."
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        text, _, _ = tf.format("who's a good plumber", rows)
    user_text = _user_text(fake)
    parsed = json.loads(user_text.split("Catalog rows:\n", 1)[1].split("\n\nRespond:", 1)[0])
    by_name = {r["name"]: r for r in parsed}
    assert by_name["Acme Plumbing"]["confidence_hint"] == "high"
    assert by_name["Acme Plumbing"]["confidence_hedge"] == ""
    assert by_name["Bayview Plumbing"]["confidence_hint"] == "medium"
    assert by_name["Bayview Plumbing"]["confidence_hedge"] == "as of last week"
    assert by_name["Crestline Plumbing"]["confidence_hint"] == "low"
    assert by_name["Crestline Plumbing"]["confidence_hedge"] == "recommend calling to confirm"
    assert text is not None
    acme_seg = text.split("Bayview", 1)[0]
    assert "as of last week" not in acme_seg
    assert "recommend calling to confirm" not in acme_seg
    bay_to_crest = text.split("Bayview", 1)[1].split("Crestline", 1)[0]
    assert "as of last week" in bay_to_crest
    assert "recommend calling to confirm" in text
    assert "Their listed number is" not in text


# 10. prompt EXCEPTION clause
def test_prompt_includes_confidence_exception_clause():
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "tier2_formatter.txt"
    body = prompt_path.read_text(encoding="utf-8")
    assert "EXCEPTION (confidence_hedge):" in body
    assert "as of last week" in body
    assert "recommend calling to confirm" in body
    assert "do not paraphrase" in body or "do not paraphrase, expand, or rewrite" in body
