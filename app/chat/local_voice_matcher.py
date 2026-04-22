"""Match curated local-voice blurbs to the user query and session hints (Phase 6.5-lite)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Mapping

from app.data import local_voice as _local_voice_data


def _keyword_boundary_pattern(keyword: str) -> str:
    return r"\b" + re.escape(keyword.strip()) + r"\b"


def _keyword_hits(query: str, keywords: list[str]) -> int:
    return sum(
        1 for kw in keywords if re.search(_keyword_boundary_pattern(kw), query, re.IGNORECASE)
    )


def _season_includes_date(season: str | None, d: date) -> bool:
    if season is None:
        return True
    if season == "year_round":
        return True
    m, day = d.month, d.day
    if season == "winter":
        return m in (12, 1, 2)
    if season == "summer":
        return m in (5, 6, 7, 8, 9)
    if season == "spring_fall":
        return m in (3, 4, 10, 11)
    if season == "holiday":
        if m == 11 and day >= 20:
            return True
        if m == 12:
            return True
        if m == 1 and day <= 5:
            return True
        return False
    return True


def _passes_session_filters(
    entry: dict[str, Any],
    session_hints: Mapping[str, Any] | None,
) -> bool:
    tags = set(entry.get("context_tags") or [])
    hints = dict(session_hints) if session_hints else {}
    hk = hints.get("has_kids")
    vs = hints.get("visitor_status")

    if "adults_only" in tags and hk is True:
        return False
    if vs == "visiting" and "local_focused" in tags:
        return False
    if vs == "local" and "visitor_friendly" in tags:
        return False

    return True


def find_matching_blurbs(
    query: str,
    session_hints: Mapping[str, Any] | None,
    current_date: date,
    max_results: int = 3,
    *,
    blurbs: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return up to ``max_results`` blurbs ordered by keyword score (desc), stable within ties."""
    src = blurbs if blurbs is not None else _local_voice_data.LOCAL_VOICE
    q = query.strip()
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for idx, entry in enumerate(src):
        season = entry.get("season")
        if not _season_includes_date(season, current_date):
            continue
        if not _passes_session_filters(entry, session_hints):
            continue
        kws = entry.get("keywords") or []
        if not isinstance(kws, list):
            continue
        score = _keyword_hits(q, [k for k in kws if isinstance(k, str)])
        if score <= 0:
            continue
        scored.append((-score, idx, entry))
    scored.sort()
    out: list[dict[str, Any]] = []
    for _, _, entry in scored[: max(0, max_results)]:
        out.append(entry)
    return out
