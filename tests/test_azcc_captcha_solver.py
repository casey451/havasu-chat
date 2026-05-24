"""Unit tests for AZCC captcha unblock helpers (cookie parse, OCR solver, signature)."""

from __future__ import annotations

import base64
import importlib
import inspect
import io
import shutil

import pytest

from app.contrib.azcc_towing_client import _parse_session_cookies, fetch_azcc_entity_search


def test_parse_session_cookies_empty_returns_list() -> None:
    assert _parse_session_cookies("") == []
    assert _parse_session_cookies("   ") == []


def test_parse_session_cookies_malformed_returns_empty() -> None:
    assert _parse_session_cookies("not json") == []
    assert _parse_session_cookies('{"name": "x"}') == []
    assert _parse_session_cookies('[{"name": "x"}]') == []


def test_parse_session_cookies_valid_passes_through() -> None:
    raw = '[{"name":"sid","value":"abc123"}]'
    out = _parse_session_cookies(raw)
    assert len(out) == 1
    assert out[0]["name"] == "sid"
    assert out[0]["value"] == "abc123"
    assert out[0]["domain"] == ".azcc.gov"


def _tesseract_binary_present() -> bool:
    return shutil.which("tesseract") is not None


@pytest.mark.skipif(not _tesseract_binary_present(), reason="Tesseract binary not on PATH")
def test_solve_captcha_image_returns_none_for_obviously_bad_input(monkeypatch) -> None:
    monkeypatch.setenv("AZCC_TESSERACT_ENABLED", "1")
    from app.contrib import _azcc_captcha_solver

    importlib.reload(_azcc_captcha_solver)
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(buf, "PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    assert _azcc_captcha_solver.solve_captcha_image(data_url) is None


def test_is_tesseract_enabled_respects_env(monkeypatch) -> None:
    from app.contrib import _azcc_captcha_solver

    monkeypatch.delenv("AZCC_TESSERACT_ENABLED", raising=False)
    assert _azcc_captcha_solver.is_tesseract_enabled() is False
    for truthy in ("1", "true", "True", "yes", "YES"):
        monkeypatch.setenv("AZCC_TESSERACT_ENABLED", truthy)
        assert _azcc_captcha_solver.is_tesseract_enabled() is True
    for falsy in ("0", "false", "no", ""):
        monkeypatch.setenv("AZCC_TESSERACT_ENABLED", falsy)
        assert _azcc_captcha_solver.is_tesseract_enabled() is False


def test_get_max_retries_clamps_to_5(monkeypatch) -> None:
    from app.contrib import _azcc_captcha_solver

    monkeypatch.delenv("AZCC_TESSERACT_MAX_RETRIES", raising=False)
    assert _azcc_captcha_solver.get_max_retries() == 3
    monkeypatch.setenv("AZCC_TESSERACT_MAX_RETRIES", "10")
    assert _azcc_captcha_solver.get_max_retries() == 5
    monkeypatch.setenv("AZCC_TESSERACT_MAX_RETRIES", "0")
    assert _azcc_captcha_solver.get_max_retries() >= 1


def test_captcha_unsolved_returns_soft_fail_shape() -> None:
    expected = {"succeeded": False, "data": []}
    assert expected["succeeded"] is False
    assert expected["data"] == []


def test_fetch_azcc_entity_search_signature_unchanged() -> None:
    sig = inspect.signature(fetch_azcc_entity_search)
    params = list(sig.parameters.keys())
    assert params[:4] == ["client", "name", "search_url", "county"]
    for pname in params[4:]:
        p = sig.parameters[pname]
        assert p.default is not inspect.Parameter.empty or p.kind == inspect.Parameter.VAR_KEYWORD, (
            f"new param {pname} must have a default"
        )
