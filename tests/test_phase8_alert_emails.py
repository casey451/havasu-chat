"""Phase 8a — alert email template render."""

from __future__ import annotations

from app.alerts.render import render_alert_email
from app.db.models import Entity


def test_render_heat_advisory_with_favorites() -> None:
    ent = Entity(id="e1", slug="cafe", name="Cool Cafe", entity_type="business")
    subject, html, text = render_alert_email(
        "heat_advisory",
        trigger={"nws_events": ["Heat Advisory"]},
        favorites=[ent],
        alerts_url="https://example.com/account/alerts",
    )
    assert "Heat" in subject
    assert "Cool Cafe" in text
    assert "Cool Cafe" in html
