"""Harness-only evidence capture for the confabulation eval harness.

Install monkeypatches ``app.chat.tier2_formatter.format`` with a wrapper that stores
``(query, [dict(r) for r in rows])`` into ``tier2_evidence`` while the inner call runs,
then resets the contextvar in ``finally``.

``restore()`` is idempotent (no-op if not installed).

Because the wrapper resets ``tier2_evidence`` before returning, invokers read a durable
single-slot buffer via :func:`consume_last_evidence` after ``unified.route(...)`` returns.
The buffer is module-local and last-write-wins for the current invocation.
It is cleared on ``install()``, ``restore()``, and after each ``consume_last_evidence()``
read to prevent evidence leakage between invocations.
"""

from __future__ import annotations

import contextvars
from collections.abc import Callable
from typing import Any, Dict, List, Optional, cast

from app.chat import tier2_formatter


tier2_evidence: contextvars.ContextVar[
    tuple[str, list[dict[str, Any]]] | None
] = contextvars.ContextVar("tier2_evidence", default=None)

_OriginalFormat = Callable[[str, List[Dict[str, Any]]], tuple[Optional[str], int | None, int | None]]
_original_format: _OriginalFormat | None = None
_format_restoration_ref: _OriginalFormat | None = None
_installed: bool = False
_last_captured: tuple[str, list[dict[str, Any]]] | None = None


def consume_last_evidence() -> tuple[str, list[dict[str, Any]]] | None:
    """Return and clear the last wrapper-captured evidence snapshot (or ``None``)."""
    global _last_captured
    out = _last_captured
    _last_captured = None
    return out


def _format_wrapper(
    query: str, rows: List[Dict[str, Any]]
) -> tuple[Optional[str], int | None, int | None]:
    global _last_captured
    copy_rows = [dict(r) for r in rows]
    token = tier2_evidence.set((query, copy_rows))
    _last_captured = (query, copy_rows)
    try:
        if _original_format is None:
            raise RuntimeError("confabulation_evidence: _original_format not set; bug in install()")
        return _original_format(query, rows)
    finally:
        tier2_evidence.reset(token)


def install() -> None:
    """Replace ``tier2_formatter.format`` with the evidence wrapper. Idempotent."""
    global _original_format, _format_restoration_ref, _installed, _last_captured
    if _installed:
        return
    pre = cast(_OriginalFormat, tier2_formatter.format)
    _format_restoration_ref = pre
    _original_format = pre
    _last_captured = None
    tier2_formatter.format = _format_wrapper
    _installed = True


def restore() -> None:
    """Restore original ``tier2_formatter.format``. Idempotent."""
    global _original_format, _format_restoration_ref, _installed, _last_captured
    if not _installed:
        return
    if _format_restoration_ref is not None:
        tier2_formatter.format = _format_restoration_ref
    _format_restoration_ref = None
    _original_format = None
    _last_captured = None
    _installed = False
