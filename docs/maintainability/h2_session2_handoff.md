<!--
PURPOSE: Kickoff document for Session 2 of the H2 ship. Paste the body of
this file (everything below the header comment) into a new Claude chat to
begin Session 2. Mirrors the pattern used by the H2 Session 1 handoff that
bootstrapped this design work.

AUDIENCE: A fresh Claude chat with no prior H2 context. The handoff orients
that chat and points it at h2_consolidation_decision.md for the design.

DO NOT treat this file as the design itself — it is intentionally thin.
The canonical design lives in h2_consolidation_decision.md.
-->

> **Status:** completed; this kickoff doc is preserved as a record of how Session 2 was bootstrapped.
> **H2 stack:** `b47ada6..f7b28df`
> **Current truth:** `docs/maintainability/h2_ship_complete_handoff.md`

# H2 — LLM-call infrastructure consolidation: Session 2 ship handoff

**You are Session 2.** Session 1 completed a read-only design pass and filed the canonical decision document. Your job is to implement the five-commit migration (helpers first, then four callers) with pytest gates after each commit.

## Read this first (mandatory)

Open and read **in full**:

- `docs/maintainability/h2_consolidation_decision.md`

That file contains the duplication map, `AnthropicResult` / `Usage` API, **mock-seam constraints** (`import anthropic`, `anthropic.Anthropic(...)`, `client.messages.create(...)` keyword arguments only), commit plan, pre-push protocol, and post-deploy monitoring. Do not skip the section on the test mock surface.

This handoff file is intentionally thin; it does not duplicate the design.

## What to ship

Execute the **five-commit plan** in `h2_consolidation_decision.md` §6:

1. Introduce `app/core/llm_messages.py` + `tests/test_llm_messages.py` — **no production callers yet**.
2. Migrate `tier2_formatter._format_via_llm`.
3. Migrate `tier2_parser.parse`.
4. Migrate `llm_router.route`.
5. Migrate `tier3_handler.answer_with_tier3`.

Cleanup of removed helpers happens **inside** each migration commit (not a separate cleanup-only commit).

## Gates (every commit)

1. `pytest --collect-only -q` — collection succeeds with no errors. After
   commit 1, the collected total rises by N (the size of `tests/test_llm_messages.py`)
   and remains stable for commits 2–5.
2. `pytest -q` — passing count is `942 + N` from commit 1 onward (N stable
   across commits 2–5); 8 known seed-fixture failures (missing
   `HAVASU_CHAT_MASTER.md`) remain unchanged; any other delta is a halt
   condition.

## Working agreement

- **Halt-and-report** between commits for owner review unless instructed otherwise.
- **BOM-free** commit messages via temp file (`UTF8Encoding` without BOM), per the decision doc.
- **Do not push** unless Casey authorizes.

## Optional context

- `docs/maintainability/h1_router_decision.md` — prior maintainability ship pattern (router).
- Verification snapshot (2026-04-29): **950** tests collected; full run **942 passed / 8 failed**.

---

**End of handoff.**
