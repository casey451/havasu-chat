"""Diagnostic logging for search pipeline. Read-only side effect — no logic changes."""

from __future__ import annotations

import json
import logging
import os
from datetime import date

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "search_debug.log")
logging.basicConfig(level=logging.DEBUG)
_log = logging.getLogger("search_diag")
_fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
_log.addHandler(_fh)


def _j(obj) -> str:
    def _default(o):
        if isinstance(o, date):
            return o.isoformat()
        return str(o)

    return json.dumps(obj, default=_default)


def log_query(raw: str, intent: str, slots: dict, strategy: str) -> None:
    _log.info("=== SEARCH QUERY ===")
    _log.info("RAW INPUT   : %s", raw)
    _log.info("INTENT      : %s", intent)
    _log.info("SLOTS       : %s", _j(slots))
    _log.info("STRATEGY    : %s", strategy)


def log_db_params(date_ctx, activity: str | None, keywords: list, audience: str | None, query_message: str) -> None:
    _log.info(
        "DB PARAMS   : date=%s  activity=%s  keywords=%s  audience=%s  query_msg=%r",
        _j(date_ctx),
        activity,
        keywords,
        audience,
        query_message,
    )


def log_candidates(query_text: str, scored: list) -> None:
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
