# LLM-mock pattern for tests

This is the project-wide policy for tests that need an OpenAI-shaped response. It locks in the pattern that's already de facto in use across `test_disclosure_render_integration.py`, `test_confidence_tier_integration_tier2.py`, `test_llm_cache.py`, `test_llm_cache_raw_storage.py`, `test_llm_messages.py`, `test_ask_mode.py`, `test_api_chat_e2e_ask_mode.py`, and `test_tier3_handler.py`. Authored alongside the BACKLOG #63 ship that closes the deferred chat-route integration coverage.

**Audience:** authors of new integration tests that need to mock OpenAI; reviewers checking that a new test follows the project pattern.

**Read time:** ~2 minutes.

---

## §1 — The pattern

Tests that need a fake OpenAI Chat Completions response use one of these two equivalent forms, depending on whether the test's setup uses `unittest.mock.patch` or `pytest`'s `monkeypatch`:

**Context-manager form** (used in 7+ files; preferred for new tests):

```python
from unittest.mock import patch

import app.core.llm_messages as llm_messages
from tests._llm_mocks import patched_openai_client

def test_something(db, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    fake = patched_openai_client("expected LLM voice text")
    with patch.object(llm_messages, "OpenAI", return_value=fake):
        # exercise code under test
        ...
```

**Monkeypatch form** (used in `test_ask_mode.py`, `test_api_chat_e2e_ask_mode.py`):

```python
from tests._llm_mocks import patched_openai_client

def test_something(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    fake = patched_openai_client("expected LLM voice text")
    monkeypatch.setattr("app.core.llm_messages.OpenAI", lambda **_kwargs: fake)
    # exercise code under test
    ...
```

The patch target is the `OpenAI` symbol bound inside `app.core.llm_messages` — the production module that constructs the OpenAI client. Patching the class on the module replaces the constructor that production code reaches for, so the rest of the call path is real.

**Always set `OPENAI_API_KEY` to a non-empty test value before patching.** `app/core/llm_messages.py:118-120` returns `None` when `OPENAI_API_KEY` is unset; without the env var the patched class is never reached and the test asserts the *fallback* shape rather than the LLM-coupled contract you meant to pin.

## §2 — Shared helpers in `tests/_llm_mocks.py`

The `_resp()` and `_patched_openai()` helpers were re-implemented in 4+ test files before this codification. They now live in `tests/_llm_mocks.py` (private module — leading-underscore convention signals "test-internal, not for app code"):

- **`build_chat_completion_response(text, *, prompt_tokens=10, completion_tokens=5) -> SimpleNamespace`** — builds the `SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=...))], usage=...)` shape that `app.core.llm_messages` reads. Mirrors the OpenAI Chat Completions SDK shape.
- **`patched_openai_client(text, *, prompt_tokens=10, completion_tokens=5) -> MagicMock`** — returns a configured `MagicMock` whose `.chat.completions.create.return_value` is the response above. Drop directly into `return_value=` of a `patch.object(llm_messages, "OpenAI", ...)`.

Older helper names (`_resp`, `_patched_openai`) remain in some test files for now; they're aliases of the shared helpers and can be migrated opportunistically. New tests should import from `tests._llm_mocks`.

## §3 — When to deviate

The shared helpers cover the dominant case (Chat Completions, single response, default token counts). Three legitimate deviations:

1. **Different patch target.** `test_llm_cache.py` patches `llm_cache.OpenAI` (not `llm_messages.OpenAI`) because the cache module imports `OpenAI` directly for the cache-key embedding path. The shared helpers still apply — the response shape is the same — but the patch target is module-local. Don't try to consolidate; the divergence is intentional.
2. **Multi-call test.** If the test exercises code that calls OpenAI twice (e.g., classification + generation), use `MagicMock(side_effect=[resp1, resp2])` directly with the shared `build_chat_completion_response` helper for each response. Don't extend `patched_openai_client` to take a list — keep the simple case simple.
3. **Custom usage / token counts.** Pass `prompt_tokens=` and `completion_tokens=` to either helper.

If you find yourself wanting a fourth deviation, propose extending the shared helper rather than redefining it locally; the redefinition pattern is what this policy is fixing.

## §4 — What we considered and rejected

**Project-wide `llm_mock` autouse fixture in `conftest.py`.** Rejected for two reasons. First, real implicit-coupling risk: a test that forgets to opt out gets a default LLM response and silently asserts the wrong contract — exactly the failure mode the chat-route integration deferral was already trying to avoid (`app/core/llm_messages.py` returning `None` when `OPENAI_API_KEY` is unset is the same shape of bug). Second, `test_llm_cache.py`'s patch-target divergence (it patches `llm_cache.OpenAI`, not `llm_messages.OpenAI`) means a single fixture can't cover all callers anyway. Per-test patches with shared response-shape helpers gives DRY without coupling.

**Env-variable-controlled stubbing in production code** (e.g., `LLM_STUB_RESPONSE=...` honored by `app/core/llm_messages.py`). Rejected — leaks test concerns into production code paths. Also creates a sharp edge: any production deploy that accidentally sets the env var becomes a silent stub. The `OPENAI_API_KEY=""` short-circuit at line 118 already exists for the "no key configured" case; that's the right boundary.

## §5 — Where the pattern shows up in existing tests

For new tests, look at these as canonical examples:

- **`test_disclosure_render_integration.py`** — full Tier-3 path with sponsor injection. The cleanest example of the pattern in context.
- **`test_confidence_tier_integration_tier2.py`** — Tier-2 formatter path with confidence-tier hints. Multiple parametrized tests, each with its own `with patch.object(...)` block.
- **`test_chat_route_integration.py`** (post-#63 ship) — HTTP-boundary tests at `/api/chat`, the most recent additions. Closest model for new chat-route integration coverage.
- **`test_llm_cache.py`** — note the `llm_cache.OpenAI` patch target divergence.

## §6 — Related references

- `docs/BACKLOG.md` #63 — the ticket this policy resolves; spec for the deferred coverage that ships alongside.
- `docs/maintainability/phase2_midweek_coverage_audit.md` "Recommended follow-ups" §2 — the audit finding that surfaced the project-wide-LLM-mock-policy gap.
- `docs/maintainability/dispatch_protocol.md` Rule 1 — anchored Edit on shared files. When extending `tests/_llm_mocks.py`, anchored Edit applies; the file is shared by all integration tests.
- `app/core/llm_messages.py:118-120` — the `OPENAI_API_KEY` short-circuit that makes the env-var setup load-bearing.
