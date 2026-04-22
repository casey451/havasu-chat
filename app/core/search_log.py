"""Diagnostic logging for search pipeline. Gated by ``SEARCH_DIAG_VERBOSE``."""

from __future__ import annotations

import json
import logging
import os
from datetime import date

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "search_debug.log")
_log = logging.getLogger("search_diag")
_log.setLevel(logging.DEBUG)


def is_search_diag_verbose() -> bool:
    """True when ``SEARCH_DIAG_VERBOSE`` is ``true`` / ``1`` / ``yes`` (case-insensitive)."""
    v = (os.getenv("SEARCH_DIAG_VERBOSE") or "").strip().lower()
    return v in ("true", "1", "yes")


def _diag_file_handler_present() -> bool:
    return any(isinstance(h, logging.FileHandler) for h in _log.handlers)


def _ensure_file_handler() -> None:
    if not is_search_diag_verbose():
        return
    if _diag_file_handler_present():
        return
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _log.addHandler(fh)


def _j(obj) -> str:
    def _default(o):
        if isinstance(o, date):
            return o.isoformat()
        return str(o)

    return json.dumps(obj, default=_default)


def log_query(raw: str, intent: str, slots: dict, strategy: str) -> None:
    if not is_search_diag_verbose():
        return
    _ensure_file_handler()
    _log.info("=== SEARCH QUERY ===")
    _log.info("RAW INPUT   : %s", raw)
    _log.info("INTENT      : %s", intent)
    _log.info("SLOTS       : %s", _j(slots))
    _log.info("STRATEGY    : %s", strategy)


def log_db_params(date_ctx, activity: str | None, keywords: list, audience: str | None, query_message: str) -> None:
    if not is_search_diag_verbose():
        return
    _ensure_file_handler()
    _log.info(
        "DB PARAMS   : date=%s  activity=%s  keywords=%s  audience=%s  query_msg=%r",
        _j(date_ctx),
        activity,
        keywords,
        audience,
        query_message,
    )


def log_candidates(query_text: str, scored: list) -> None:
    if not is_search_diag_verbose():
        return
    _ensure_file_handler()
    _log.info("CANDIDATES  : %d results for %r", len(scored), query_text)
    for i, (event, score) in enumerate(scored[:10]):
        _log.info(
            "  [%02d] score=%.4f  id=%s  title=%r  date=%s",
            i + 1,
            score,
            event.id,
            event.title,
            event.date.isoformat() if event.date else "?",
        )
    if not scored:
        _log.info("  (no scored candidates)")
    _log.info("=== END ===")
