"""Shared template environment and small helpers for the portal."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("dashboard", "Dashboard", "/admin/portal"),
    ("moderation", "Moderation", "/admin/portal/moderation"),
    ("addresses", "Address flags", "/admin/portal/addresses"),
    ("users", "Users & access", "/admin/portal/users"),
    ("chat", "Chat insights", "/admin/portal/chat"),
    ("ops", "Ops", "/admin/portal/ops"),
    ("audit", "Audit log", "/admin/portal/audit"),
)


def render(
    request: Request, template_name: str, active: str, context: dict | None = None
) -> HTMLResponse:
    ctx = {
        "request": request,
        "nav_items": NAV_ITEMS,
        "active": active,
        "now_utc": datetime.now(UTC),
    }
    if context:
        ctx.update(context)
    return templates.TemplateResponse(request, template_name, ctx)


def window_start(days: int) -> datetime:
    """UTC start of an N-day rolling window (naive, matching DB columns)."""
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)


def fmt_ago(dt: datetime | None) -> str:
    """Compact relative-time label for table cells."""
    if dt is None:
        return "—"
    base = dt if dt.tzinfo is None else dt.astimezone(UTC).replace(tzinfo=None)
    delta = datetime.now(UTC).replace(tzinfo=None) - base
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


templates.env.filters["ago"] = fmt_ago
