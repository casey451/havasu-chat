"""Local dev checks for Phase 6.4 acceptance (no commit). Uses TestClient + mocks."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.chat.hint_extractor import ExtractedHints  # noqa: E402
from app.core.session import clear_session_state, get_session  # noqa: E402
from app.core.timezone import format_now_lake_havasu, now_lake_havasu  # noqa: E402
from app.main import app  # noqa: E402


def scenario_a() -> None:
    clear_session_state("mv-scen-a")
    captured: list[dict] = []

    def cap_t3(*_a, **kw):
        captured.append(kw)
        return ("stub-tier3", 10, 5, 5)

    with TestClient(app) as client:
        client.post(
            "/api/chat/onboarding",
            json={"session_id": "mv-scen-a", "visitor_status": "visiting", "has_kids": True},
        )
        with patch("app.chat.unified_router.extract_hints", return_value=ExtractedHints(age=6, location="near the channel")):
            with patch("app.chat.unified_router.try_tier1", return_value=None):
                with patch(
                    "app.chat.unified_router.try_tier2_with_usage",
                    return_value=(None, None, None, None),
                ):
                    with patch("app.chat.unified_router.answer_with_tier3", side_effect=cap_t3):
                        r = client.post(
                            "/api/chat",
                            json={
                                "session_id": "mv-scen-a",
                                "query": "I'm visiting with my 6-year-old, we're near the channel, what should we do tomorrow",
                            },
                        )
    assert r.status_code == 200, r.text
    hints = get_session("mv-scen-a")["onboarding_hints"]
    assert hints.get("visitor_status") == "visiting"
    assert hints.get("has_kids") is True
    assert hints.get("age") == 6
    assert "channel" in (hints.get("location") or "").lower()
    assert captured, "tier3 not called"
    kw = captured[0]
    oh = kw.get("onboarding_hints") or {}
    assert "visiting" in str(oh).lower() or oh.get("visitor_status") == "visiting"
    assert oh.get("age") == 6
    now_line = kw.get("now_line") or ""
    assert now_line.lower().startswith("now:")
    assert str(now_lake_havasu().year) in now_line, (now_line, format_now_lake_havasu())
    print("scenario_a: OK (Tier3 kwargs show hints + Now with calendar year)")


def scenario_b() -> None:
    clear_session_state("mv-scen-b")
    entities: list[str | None] = []

    def cap_t3(q, intent, db, **kw):
        entities.append(intent.entity)
        return ("stub", 1, 1, 1)

    q1 = "What are the hours for Altitude Trampoline Park — Lake Havasu City?"
    q2 = "what time does it open?"
    with TestClient(app) as client:
        with patch("app.chat.unified_router.extract_hints", return_value=None):
            with patch("app.chat.unified_router.try_tier1", return_value=None):
                with patch(
                    "app.chat.unified_router.try_tier2_with_usage",
                    return_value=(None, None, None, None),
                ):
                    with patch("app.chat.unified_router.answer_with_tier3", side_effect=cap_t3):
                        r1 = client.post(
                            "/api/chat",
                            json={"session_id": "mv-scen-b", "query": q1},
                        )
                        assert r1.status_code == 200
                        r2 = client.post(
                            "/api/chat",
                            json={"session_id": "mv-scen-b", "query": q2},
                        )
                        assert r2.status_code == 200
    pe = get_session("mv-scen-b").get("prior_entity") or {}
    assert pe.get("name"), pe
    assert entities and entities[-1] == pe.get("name"), entities
    print("scenario_b: OK (prior_entity set; Tier3 saw resolved entity on pronoun turn)")


def main() -> None:
    scenario_a()
    scenario_b()


if __name__ == "__main__":
    main()
