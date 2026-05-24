"""Per-request chat signals (Phase 7): boat mode, heat bias, multi-domain slugs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from app.core.ranking import HEAT_BIAS_THRESHOLD_F, STUB_CURRENT_TEMPERATURE_F

BOAT_MODE_QUERY_PARAM = "boat"
BOAT_MODE_HEADER = "x-boat-mode"

BOAT_MODE_TIER3_PREAMBLE = (
    "The user is in boat-access mode. Prefer waterfront / dock-accessible entities. "
    "Mention boat-access details when relevant."
)

EVENT_INTENT_TIER3_PREAMBLE = (
    "The user is asking about events. Surface upcoming events chronologically; "
    "mention venue name and time prominently."
)


def heat_bias_tier3_preamble(temperature_f: float) -> str:
    temp = int(round(temperature_f))
    return (
        f"Current temperature is {temp}°F; user comfort favors indoor venues."
    )


@dataclass(frozen=True)
class ChatRequestContext:
    """Optional signals threaded through tier 2 / tier 3 (defaults = off)."""

    boat_mode: bool = False
    temperature_f: float | None = None
    multi_domain_category_slugs: tuple[str, ...] = field(default_factory=tuple)
    event_intent_when: str | None = None

    def effective_temperature_f(self) -> float:
        if self.temperature_f is not None:
            return self.temperature_f
        return STUB_CURRENT_TEMPERATURE_F

    def heat_bias_active(self) -> bool:
        return self.effective_temperature_f() > HEAT_BIAS_THRESHOLD_F

    def tier3_context_preambles(self) -> list[str]:
        parts: list[str] = []
        if self.boat_mode:
            parts.append(BOAT_MODE_TIER3_PREAMBLE)
        if self.heat_bias_active():
            parts.append(heat_bias_tier3_preamble(self.effective_temperature_f()))
        if self.event_intent_when:
            parts.append(EVENT_INTENT_TIER3_PREAMBLE)
        return parts


def parse_chat_request_context(
    *,
    query_params: Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
    preferred_mode: str | None = None,
) -> ChatRequestContext:
    """Resolve boat mode from query param, header, or logged-in user preference."""
    boat = False
    if preferred_mode and preferred_mode.strip().lower() == "boat":
        boat = True
    if query_params:
        v = (query_params.get(BOAT_MODE_QUERY_PARAM) or "").strip().lower()
        if v in ("1", "true", "yes", "on"):
            boat = True
    if headers:
        norm = {k.lower(): v for k, v in headers.items()}
        v = (norm.get(BOAT_MODE_HEADER.lower()) or "").strip().lower()
        if v in ("1", "true", "yes", "on"):
            boat = True
    return ChatRequestContext(boat_mode=boat)


__all__ = [
    "BOAT_MODE_HEADER",
    "BOAT_MODE_QUERY_PARAM",
    "BOAT_MODE_TIER3_PREAMBLE",
    "EVENT_INTENT_TIER3_PREAMBLE",
    "ChatRequestContext",
    "heat_bias_tier3_preamble",
    "parse_chat_request_context",
]
