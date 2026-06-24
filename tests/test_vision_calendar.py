"""Unit tests for the generic vision calendar/flyer engine.

Pure validation + parsing guards (no live HTTP, no live LLM): each §6 guard is
exercised with recorded JSON. The one live-ish test patches the OpenAI symbol
with a fake client to assert the image is sent as a base64 data URL.
"""

from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path

from app.contrib import vision_calendar as vc

FIXTURES = Path(__file__).parent / "fixtures" / "parks_rec"


def _calendar_rows() -> list[dict]:
    data = json.loads((FIXTURES / "calendar_model_output.json").read_text(encoding="utf-8"))
    return data["events"]


# --------------------------------------------------------------------------- #
# Validation guards
# --------------------------------------------------------------------------- #
def test_validate_keeps_valid_and_holds_low_confidence() -> None:
    rows, stats = vc.validate_rows(_calendar_rows(), month=7, year=2026)
    titles = {r.title for r in rows}
    assert "Tiny Tots Move & Groove" in titles
    assert "Free Summer Craft Series" in titles
    assert stats.kept == 2
    high = next(r for r in rows if r.title.startswith("Tiny Tots"))
    low = next(r for r in rows if r.title.startswith("Free Summer"))
    assert high.should_hide is False
    assert low.should_hide is True  # confidence 0.6 < 0.75
    assert stats.held_low_confidence == 1


def test_validate_drops_out_of_month_date() -> None:
    rows, stats = vc.validate_rows(_calendar_rows(), month=7, year=2026)
    assert all(r.event_date.month == 7 for r in rows)
    assert "August Pizza Party" not in {r.title for r in rows}
    assert stats.dropped_out_of_month == 1


def test_validate_drops_missing_source_cell() -> None:
    rows, stats = vc.validate_rows(_calendar_rows(), month=7, year=2026)
    assert "Unreadable Cell Guess" not in {r.title for r in rows}
    assert stats.dropped_no_provenance == 1


def test_validate_drops_empty_and_overlong_title() -> None:
    rows = [
        {"title": "", "date": "2026-07-03", "source_cell": "x", "confidence": 0.9},
        {"title": "A" * 200, "date": "2026-07-03", "source_cell": "x", "confidence": 0.9},
    ]
    kept, stats = vc.validate_rows(rows, month=7, year=2026)
    assert kept == []
    assert stats.dropped_bad_title == 2


def test_validate_drops_unparseable_date() -> None:
    rows = [{"title": "Mystery", "date": "someday", "source_cell": "x", "confidence": 0.9}]
    kept, stats = vc.validate_rows(rows, month=7, year=2026)
    assert kept == []
    assert stats.dropped_bad_date == 1


def test_missing_confidence_is_held_not_trusted() -> None:
    rows = [{"title": "No Conf", "date": "2026-07-04", "source_cell": "x"}]
    kept, _ = vc.validate_rows(rows, month=7, year=2026)
    assert len(kept) == 1
    assert kept[0].confidence == 0.0
    assert kept[0].should_hide is True


# --------------------------------------------------------------------------- #
# Field parsers
# --------------------------------------------------------------------------- #
def test_parse_time_variants() -> None:
    assert vc._parse_time("10:00") == time(10, 0)
    assert vc._parse_time("9:30 AM") == time(9, 30)
    assert vc._parse_time("1:00 PM") == time(13, 0)
    assert vc._parse_time("12:00 AM") == time(0, 0)
    assert vc._parse_time("12:00 PM") == time(12, 0)
    assert vc._parse_time("9pm") == time(21, 0)
    assert vc._parse_time(None) is None
    assert vc._parse_time("noon") is None
    assert vc._parse_time("25:00") is None


def test_parse_date_public_alias() -> None:
    assert vc.parse_date("2026-07-08") == date(2026, 7, 8)
    assert vc.parse_date("nope") is None


# --------------------------------------------------------------------------- #
# JSON parsing
# --------------------------------------------------------------------------- #
def test_parse_events_json_shapes() -> None:
    assert vc.parse_events_json('{"events":[{"a":1}]}') == [{"a": 1}]
    assert vc.parse_events_json('[{"a":1}]') == [{"a": 1}]
    assert vc.parse_events_json("not json") == []
    assert vc.parse_events_json("") == []
    assert vc.parse_events_json('{"events":"oops"}') == []


# --------------------------------------------------------------------------- #
# Self-check demotion
# --------------------------------------------------------------------------- #
def test_apply_self_check_flags_demotes_unsure_dates() -> None:
    rows, _ = vc.validate_rows(
        [{"title": "Sure Thing", "date": "2026-07-08", "source_cell": "x", "confidence": 0.99}],
        month=7,
        year=2026,
    )
    assert rows[0].should_hide is False
    demoted = vc.apply_self_check_flags(rows, {date(2026, 7, 8)})
    assert demoted == 1
    assert rows[0].should_hide is True
    # Idempotent: already-held rows aren't re-counted.
    assert vc.apply_self_check_flags(rows, {date(2026, 7, 8)}) == 0


# --------------------------------------------------------------------------- #
# Live vision call wiring (fake client; no network)
# --------------------------------------------------------------------------- #
class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.message = type("M", (), {"content": content})()


class _FakeCompletions:
    def __init__(self, captured: dict) -> None:
        self._captured = captured

    def create(self, **kwargs):
        self._captured.update(kwargs)
        return type("R", (), {"choices": [_FakeMessage('{"events":[]}')]})()


class _FakeClient:
    def __init__(self, captured: dict, **_kw) -> None:
        self.chat = type("C", (), {"completions": _FakeCompletions(captured)})()


def test_call_vision_sends_base64_data_url(monkeypatch) -> None:
    captured: dict = {}

    def _factory(captured_=captured):
        def make(**kwargs):
            return _FakeClient(captured_, **kwargs)

        return make

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    img = (FIXTURES / "sample_calendar.png").read_bytes()
    out = vc.call_vision(
        img,
        system_prompt="transcribe",
        model="gpt-4o",
        mime="image/png",
        openai_symbol=_factory(),
    )
    assert out == '{"events":[]}'
    # The image must reach the model as a base64 data URL.
    content = captured["messages"][1]["content"]
    image_part = next(p for p in content if p["type"] == "image_url")
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")
    assert captured["temperature"] == 0
    assert captured["response_format"] == {"type": "json_object"}


def test_call_vision_no_key_returns_empty(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VISION_BASE_URL", raising=False)
    assert vc.call_vision(b"x", system_prompt="p", openai_symbol=object()) == ""


# --------------------------------------------------------------------------- #
# Self-hosted (local) vision backend — no OpenAI key / no token spend
# --------------------------------------------------------------------------- #
class _CtorCapturingClient:
    """Fake OpenAI client capturing the constructor kwargs (base_url etc.)."""

    last_ctor: dict = {}

    def __init__(self, **ctor) -> None:
        _CtorCapturingClient.last_ctor = ctor
        self._create_kwargs: dict = {}
        self.chat = type(
            "C", (), {"completions": type("Cc", (), {"create": self._create})()}
        )()

    def _create(self, **kwargs):
        self._create_kwargs.update(kwargs)
        _CtorCapturingClient.last_create = kwargs  # type: ignore[attr-defined]
        return type("R", (), {"choices": [_FakeMessage('{"events":[]}')]})()


def test_local_endpoint_used_when_base_url_set(monkeypatch) -> None:
    # No OpenAI key at all -> a self-hosted endpoint still works (no token spend).
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("VISION_BASE_URL", "http://10.0.0.5:11434/v1")
    monkeypatch.setenv("VISION_MODEL", "qwen2.5vl:3b")

    out = vc.call_vision(b"img", system_prompt="p", openai_symbol=_CtorCapturingClient)

    assert out == '{"events":[]}'
    # The client was pointed at the local base URL with a non-empty placeholder key.
    assert _CtorCapturingClient.last_ctor["base_url"] == "http://10.0.0.5:11434/v1"
    assert _CtorCapturingClient.last_ctor["api_key"]  # "local" by default
    # The served model name (VISION_MODEL) is used, not the OpenAI default.
    assert _CtorCapturingClient.last_create["model"] == "qwen2.5vl:3b"  # type: ignore[attr-defined]


def test_vision_model_resolution(monkeypatch) -> None:
    monkeypatch.delenv("VISION_MODEL", raising=False)
    monkeypatch.delenv("PARKS_REC_VISION_MODEL", raising=False)
    assert vc.vision_model() == "gpt-4o"
    monkeypatch.setenv("PARKS_REC_VISION_MODEL", "legacy-model")
    assert vc.vision_model() == "legacy-model"
    monkeypatch.setenv("VISION_MODEL", "minicpm-v")  # generic wins over legacy
    assert vc.vision_model() == "minicpm-v"
