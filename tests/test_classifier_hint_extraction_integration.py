"""Optional real OpenAI hint extraction (run: pytest -m integration)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.bootstrap_env import ensure_dotenv_loaded

ensure_dotenv_loaded()

import pytest

from app.chat.hint_extractor import extract_hints


@pytest.mark.integration
def test_integration_my_six_year_old() -> None:
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        pytest.skip("OPENAI_API_KEY not set")
    h = extract_hints("my 6-year-old likes BMX")
    assert h is not None
    assert h.age == 6 or str(h.age) == "6"


@pytest.mark.integration
def test_integration_open_right_now_null() -> None:
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        pytest.skip("OPENAI_API_KEY not set")
    assert extract_hints("what's open right now") is None


@pytest.mark.integration
def test_integration_channel_and_teenager() -> None:
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        pytest.skip("OPENAI_API_KEY not set")
    h = extract_hints("we're staying near the channel with my teenager")
    assert h is not None
    assert h.location and "channel" in h.location.lower()
    assert h.age is not None or (h.location and "teen" in str(h.location).lower())


@pytest.mark.integration
def test_integration_kid_no_age() -> None:
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        pytest.skip("OPENAI_API_KEY not set")
    assert extract_hints("my kid loves dinosaurs") is None


@pytest.mark.integration
def test_integration_island_bridge_location() -> None:
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        pytest.skip("OPENAI_API_KEY not set")
    h = extract_hints("good things to do near the island bridge")
    assert h is not None
    assert h.location
    assert h.age is None
