"""P2.HOME.1 — /home Local pros row uses ``DISCLOSURE_WORD`` for paid badges."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.chat.disclosure_render import DISCLOSURE_WORD
from app.main import app


def test_home_spotlight_row_uses_disclosure_word_not_spotlight_label() -> None:
    """Spotlight cards must show the canonical disclosure word (see disclosure_render)."""
    with TestClient(app) as client:
        r = client.get("/home")
    assert r.status_code == 200
    html_out = r.text
    assert DISCLOSURE_WORD in html_out
    assert "Spotlight" not in html_out
