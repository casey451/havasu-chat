"""Render alert email bodies (Phase 8a)."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.db.models import Entity

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _entity_lines(entities: list[Entity]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for ent in entities:
        rows.append({"name": ent.name or ent.slug or "Venue"})
    return rows


def render_alert_email(
    alert_type: str,
    *,
    trigger: dict[str, Any],
    favorites: list[Entity],
    alerts_url: str,
) -> tuple[str, str, str]:
    favorites_rows = _entity_lines(favorites)
    ctx = {
        "trigger": trigger,
        "favorites": favorites_rows,
        "indoor_favorites": favorites_rows,
        "land_favorites": favorites_rows,
        "alerts_url": alerts_url,
    }
    base_url = alerts_url.rsplit("/account", 1)[0] if "/account" in alerts_url else alerts_url

    if alert_type == "heat_advisory":
        subject = "Heat advisory in Lake Havasu City"
        html_t = _env.get_template("heat_advisory.html.j2")
        text_t = _env.get_template("heat_advisory.txt.j2")
    elif alert_type == "aqi_alert":
        subject = "Air quality alert for Lake Havasu City"
        html_t = _env.get_template("aqi_alert.html.j2")
        text_t = _env.get_template("aqi_alert.txt.j2")
    elif alert_type == "lake_hazard":
        subject = "Lake hazard advisory for Lake Havasu City"
        html_t = _env.get_template("lake_hazard.html.j2")
        text_t = _env.get_template("lake_hazard.txt.j2")
    else:
        subject = "Havasu conditions alert"
        html_body = f"<p>Conditions alert: {html.escape(alert_type)}</p>"
        text_body = f"Conditions alert: {alert_type}\nManage alerts: {alerts_url}\n"
        return subject, html_body, text_body

    ctx["base_url"] = base_url
    return subject, html_t.render(**ctx), text_t.render(**ctx)
