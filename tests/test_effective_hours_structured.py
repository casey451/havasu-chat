"""``effective_hours_structured`` google_hours fallback."""

from __future__ import annotations

from types import SimpleNamespace

from app.providers.queries import effective_hours_structured


def _google_hours_monday_nine_to_five() -> dict:
    return {
        "periods": [
            {
                "open": {"day": 1, "hour": 9, "minute": 0},
                "close": {"day": 1, "hour": 17, "minute": 0},
            },
        ]
    }


def test_effective_hours_structured_prefers_hours_structured() -> None:
    hs = {"tuesday": [{"open": "10:00", "close": "18:00"}]}
    p = SimpleNamespace(
        id=1,
        entity=None,
        hours_structured=hs,
        google_hours=_google_hours_monday_nine_to_five(),
    )
    assert effective_hours_structured(p) == hs


def test_effective_hours_structured_falls_back_to_google_hours() -> None:
    gh = _google_hours_monday_nine_to_five()
    p = SimpleNamespace(id=42, entity=None, hours_structured=None, google_hours=gh)
    out = effective_hours_structured(p)
    assert out is not None
    assert out.get("monday") == [{"open": "09:00", "close": "17:00"}]


def test_effective_hours_structured_empty_dict_not_overridden() -> None:
    p = SimpleNamespace(
        id=2,
        entity=None,
        hours_structured={},
        google_hours=_google_hours_monday_nine_to_five(),
    )
    assert effective_hours_structured(p) == {}


def test_effective_hours_structured_none_when_both_missing() -> None:
    p = SimpleNamespace(id=3, entity=None, hours_structured=None, google_hours=None)
    assert effective_hours_structured(p) is None
