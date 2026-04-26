"""Tests for :mod:`app.eval.confabulation_invoker` (spec §5.2 smoke)."""

from __future__ import annotations

from types import SimpleNamespace

from app.chat import tier2_formatter
from app.eval import confabulation_evidence
from app.eval.confabulation_invoker import InProcessInvoker
from app.eval.confabulation_query_gen import Probe


def test_inprocess_invoker_smoke(monkeypatch):
    """Full install -> route -> read evidence -> restore cycle, with non-empty evidence_set."""

    real_format = tier2_formatter.format

    # Make formatter deterministic and cheap; install() will wrap this object.
    def fake_format(_q: str, _rows: list[dict]):
        return "formatted", 1, 2

    monkeypatch.setattr(tier2_formatter, "format", fake_format, raising=True)

    # Route path that triggers patched formatter call and returns ChatResponse-like object.
    def fake_route(query: str, session_id: str | None, db):
        _ = session_id
        _ = db
        rows = [{"type": "provider", "name": "Smoke Provider", "description": "desc", "category": "test"}]
        tier2_formatter.format(query, rows)
        return SimpleNamespace(response="stub response", tier_used="2", chat_log_id=None)

    import app.eval.confabulation_invoker as mod

    monkeypatch.setattr(mod.unified, "route", fake_route, raising=True)

    inv = InProcessInvoker(session_id="t-smoke")
    probe = Probe(
        query_text="tell me about Smoke Provider",
        row_id="provider:smoke",
        row_type="provider",
        template_id="provider_tell_me_about",
    )

    out = inv.invoke(probe, "off")

    assert out.error is None
    assert out.response_text == "stub response"
    assert out.tier_used == "2"
    assert out.evidence_row_dicts
    assert out.evidence_row_dicts[0]["name"] == "Smoke Provider"

    # ensure monkeypatch was restored by invoker finally block
    assert tier2_formatter.format is fake_format
    confabulation_evidence.restore()  # idempotent cleanup
    assert tier2_formatter.format is fake_format

    # and our local monkeypatch fixture restores module state after test
    monkeypatch.setattr(tier2_formatter, "format", real_format, raising=True)


def test_inprocess_invoker_no_stale_evidence_between_calls(monkeypatch):
    """First call captures Tier 2 rows; second non-Tier-2 call must not reuse stale rows."""

    def fake_format(_q: str, _rows: list[dict]):
        return "formatted", 1, 2

    monkeypatch.setattr(tier2_formatter, "format", fake_format, raising=True)

    calls = {"n": 0}

    def fake_route(query: str, session_id: str | None, db):
        _ = session_id
        _ = db
        calls["n"] += 1
        if calls["n"] == 1:
            rows = [
                {
                    "type": "provider",
                    "name": "First Provider",
                    "description": "desc",
                    "category": "test",
                }
            ]
            tier2_formatter.format(query, rows)
            return SimpleNamespace(response="tier2 response", tier_used="2", chat_log_id=None)
        # Simulate Tier 1/3 path: no formatter call.
        return SimpleNamespace(response="non-tier2 response", tier_used="1", chat_log_id=None)

    import app.eval.confabulation_invoker as mod

    monkeypatch.setattr(mod.unified, "route", fake_route, raising=True)

    inv = InProcessInvoker(session_id="t-leak-check")
    probe = Probe(
        query_text="tell me about Provider",
        row_id="provider:x",
        row_type="provider",
        template_id="provider_tell_me_about",
    )

    out1 = inv.invoke(probe, "off")
    assert out1.evidence_row_dicts
    assert out1.evidence_row_dicts[0]["name"] == "First Provider"

    out2 = inv.invoke(probe, "off")
    assert out2.tier_used == "1"
    assert out2.evidence_row_dicts == []
