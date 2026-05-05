from __future__ import annotations

from typing import Any

# POST /api/chat (ConciergeChatRequest) — distinct from Tier 3 runtime graceful errors (handoff §3.11).
CHAT_CONCIERGE_QUERY_VALIDATION_MESSAGE = (
    "That request didn't parse — the 'query' field is required and can't be empty."
)


def _errors_touch_concierge_query_field(errors: list[dict[str, Any]]) -> bool:
    """True when validation errors target ``query`` on the JSON body (unified chat request)."""
    for err in errors:
        loc = err.get("loc")
        if not isinstance(loc, (list, tuple)) or not loc:
            continue
        if loc[-1] != "query":
            continue
        # FastAPI wraps body fields as ``('body', 'query')``; direct ``model_validate`` uses ``('query',)``.
        if len(loc) == 1 or (len(loc) >= 2 and loc[0] == "body"):
            return True
    return False


def friendly_errors(errors: list[dict[str, Any]]) -> str:
    if _errors_touch_concierge_query_field(errors):
        return CHAT_CONCIERGE_QUERY_VALIDATION_MESSAGE
    for err in errors:
        ctx = err.get("ctx")
        if ctx:
            inner = ctx.get("error")
            if isinstance(inner, ValueError):
                return str(inner)
        msg = err.get("msg", "")
        if isinstance(msg, str) and msg.startswith("Value error, "):
            return msg.replace("Value error, ", "", 1)
    return "Some event details are not valid. Please check and try again."
