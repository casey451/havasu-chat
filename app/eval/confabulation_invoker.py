"""Invocation strategies for confabulation eval harness.

- ``InProcessInvoker``: installs evidence monkeypatch, calls ``unified.route``, consumes
  last captured evidence snapshot, restores patch in ``finally``.
- ``HttpInvoker``: calls ``POST /api/chat`` and returns degraded result (no evidence rows).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import requests

from app.chat import unified_router as unified
from app.db.database import SessionLocal
from app.eval import confabulation_evidence
from app.eval.confabulation_query_gen import Probe


@dataclass(slots=True)
class InvocationResult:
    response_text: str
    evidence_row_dicts: list[dict[str, Any]]
    tier_used: str | None
    latency_ms: int
    raw_log: dict[str, Any]
    error: str | None = None


class Invoker(Protocol):
    def invoke(self, probe: Probe, flag_state: str) -> InvocationResult: ...


def _set_router_flag(flag_state: str) -> str | None:
    prior = os.environ.get("USE_LLM_ROUTER")
    if flag_state == "on":
        os.environ["USE_LLM_ROUTER"] = "1"
    elif flag_state == "off":
        os.environ["USE_LLM_ROUTER"] = "0"
    else:
        raise ValueError("flag_state must be 'on' or 'off'")
    return prior


def _restore_router_flag(prior: str | None) -> None:
    if prior is None:
        os.environ.pop("USE_LLM_ROUTER", None)
    else:
        os.environ["USE_LLM_ROUTER"] = prior


class InProcessInvoker:
    """Call ``unified.route`` in-process with evidence capture enabled."""

    def __init__(self, *, session_id: str = "confab-eval") -> None:
        self.session_id = session_id

    def invoke(self, probe: Probe, flag_state: str) -> InvocationResult:
        prior = _set_router_flag(flag_state)
        t0 = time.perf_counter()
        confabulation_evidence.install()
        try:
            with SessionLocal() as db:
                try:
                    res = unified.route(probe.query_text, self.session_id, db)
                except Exception as exc:
                    ms = max(1, int((time.perf_counter() - t0) * 1000))
                    return InvocationResult(
                        response_text="",
                        evidence_row_dicts=[],
                        tier_used=None,
                        latency_ms=ms,
                        raw_log={"probe": probe.query_text, "flag_state": flag_state},
                        error=f"route_error:{type(exc).__name__}: {exc}",
                    )

                snapshot = confabulation_evidence.consume_last_evidence()
                rows = snapshot[1] if snapshot else []
                ms = max(1, int((time.perf_counter() - t0) * 1000))
                return InvocationResult(
                    response_text=res.response,
                    evidence_row_dicts=rows,
                    tier_used=res.tier_used,
                    latency_ms=ms,
                    raw_log={
                        "probe": probe.query_text,
                        "flag_state": flag_state,
                        "chat_log_id": getattr(res, "chat_log_id", None),
                    },
                )
        finally:
            confabulation_evidence.restore()
            _restore_router_flag(prior)


class HttpInvoker:
    """Call deployed API endpoint; degraded mode (no evidence rows)."""

    def __init__(self, *, base_url: str, timeout_sec: float = 30.0, session_id: str = "confab-eval") -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self.session_id = session_id

    def invoke(self, probe: Probe, flag_state: str) -> InvocationResult:
        prior = _set_router_flag(flag_state)
        t0 = time.perf_counter()
        try:
            try:
                r = requests.post(
                    f"{self.base_url}/api/chat",
                    json={"query": probe.query_text, "session_id": self.session_id},
                    timeout=self.timeout_sec,
                )
                ms = max(1, int((time.perf_counter() - t0) * 1000))
            except Exception as exc:
                ms = max(1, int((time.perf_counter() - t0) * 1000))
                return InvocationResult(
                    response_text="",
                    evidence_row_dicts=[],
                    tier_used=None,
                    latency_ms=ms,
                    raw_log={"probe": probe.query_text, "flag_state": flag_state},
                    error=f"http_error:{type(exc).__name__}: {exc}",
                )

            try:
                body: dict[str, Any] = r.json()
            except Exception:
                body = {"raw": r.text}

            if r.status_code >= 400:
                return InvocationResult(
                    response_text="",
                    evidence_row_dicts=[],
                    tier_used=None,
                    latency_ms=ms,
                    raw_log={"status_code": r.status_code, "body": body},
                    error=f"http_status:{r.status_code}",
                )

            return InvocationResult(
                response_text=str(body.get("response", "") or ""),
                evidence_row_dicts=[],
                tier_used=(str(body.get("tier_used")) if body.get("tier_used") is not None else None),
                latency_ms=ms,
                raw_log={"status_code": r.status_code, "body": body},
            )
        finally:
            _restore_router_flag(prior)
