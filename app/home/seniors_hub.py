"""WS10 /seniors — today's live Senior-Center feed (view-model).

The /seniors page is otherwise static (address, the two monthly calendar images,
the transcribed weekly-activities grid, Meals on Wheels). WS2/WS10 want a live
"today's seniors feed" on it too — the Senior Center's activities are ingested as
senior-tagged Events (``scripts/load_senior_center.py``), so we read them through
the SAME ``day_groups(seniors=True)`` narrow the ``?seniors=1`` calendar toggle
uses. That keeps /seniors and the calendar in agreement, and it's honest-omit: an
empty day shows nothing rather than a fabricated activity.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.home import events_views


def _walk(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten every event row across a day_groups tree (rows + subgroups)."""
    out: list[dict[str, Any]] = []

    def _w(node: dict[str, Any]) -> None:
        out.extend(node.get("rows") or [])
        for sub in node.get("subgroups") or []:
            _w(sub)
        for child in node.get("children") or []:
            _w(child)

    for g in groups:
        _w(g)
    return out


def today_seniors_rows(
    db: Session, *, day: date, now: datetime | None = None, limit: int = 20
) -> list[dict[str, str]]:
    """Today's senior activities — the ``seniors=True`` narrow (``is_senior_event``).

    Each row is ``{title, time_label, venue, url}``. Deduped by URL (a day_groups
    node exposes its rows both flat and split into subgroups, so we collapse the
    two). Honest-omit → ``[]`` when the center has nothing on ``day``.
    """
    groups = events_views.day_groups(db, day=day, seniors=True, now=now)
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for r in _walk(groups):
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        if not title or not url or url in seen:
            continue
        seen.add(url)
        tl = (r.get("time_label") or "").strip()
        out.append(
            {
                "title": title,
                "time_label": "" if "TBD" in tl.upper() else tl,
                "venue": (r.get("venue") or "").strip(),
                "url": url,
            }
        )
    return out[:limit]
