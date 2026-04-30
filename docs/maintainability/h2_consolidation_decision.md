<!--
PURPOSE: H2 design decision document. Single-source for the consolidation
design — duplication map, helper API, mock-seam constraints, commit plan,
gates, monitoring. Filed alongside h1_router_decision.md.

AUDIENCE: Future Claude sessions and humans reading the repo. Read in full
before any H2 implementation work.

DO NOT paste this file into a new chat as a kickoff document — use
h2_session2_handoff.md for that.
-->

# H2 Investigation: LLM-call infrastructure consolidation — Decision Recommendation

**Status:** Shipped as a seven-commit stack — see **§ Status — completed** at end of this document for hashes, gates, and deferred backlog.

**Bundle reviewed:** `h2_investigation_bundle.txt` (36,689 bytes, 992 lines, 6 sections).

**Verification pass (2026-04-29):** confirmed pytest baseline (942 passing / 8 known seed-fixture failures); `app/core/` inventory (16 files; `llm_http.py` is 11 lines containing only `LLM_CLIENT_READ_TIMEOUT_SEC`); test mock surface (see §Findings); identified one additional Anthropic caller outside the original five files (`scripts/run_voice_audit.py`).

---

## Findings (the actual picture)

### Duplication map

Four production files in `app/chat/` call Anthropic and reproduce the same boilerplate:

- `tier2_parser.py` (135 lines)
- `tier2_formatter.py` (132 lines, duplication is in `_format_via_llm` only — the deterministic events path bypasses LLM)
- `llm_router.py` (217 lines)
- `tier3_handler.py` (188 lines)

The fifth file the review flagged, `hint_extractor.py` (110 lines), uses OpenAI; treated separately below.

**Genuinely identical across all four:**

- Empty/missing-API-key check + early return with sentinel
- System block construction: `[{"type": "text", "text": ..., "cache_control": {"type": "ephemeral"}}]`
- `_extract_text_from_message` — `llm_router`'s version is a stylistic variant only (one-pass loop instead of save-then-loop); behavior identical
- Client construction `anthropic.Anthropic(api_key=api_key, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)` plus `client.messages.create(model=, max_tokens=, temperature=, system=, messages=)` wrapped in try/except

**Identical in two files (parser + llm_router):**

- `_coerce_llm_text_to_json_object` — modulo trivial variable renames (`first_nl` vs `first`); same logic, same return shape

**Same intent, two function shapes:**

- `_usage_in_out(msg)` in parser/formatter/llm_router; `_split_usage(usage)` in tier3. Tier3's wrapper takes the unwrapped `usage` object; the others extract `usage` from `msg` internally. Arithmetically equivalent — both compute `(input_tokens + cache_read_input_tokens + cache_creation_input_tokens, output_tokens)`. The review's claim that `_split_usage` is "the most complete" is misleading; they're the same calculation. Either shape can host the helper.

**Subtly different across files (matters for design):**

- `import anthropic` is **lazy** (inside the function body) in tier2_parser, tier2_formatter, tier3_handler. **Module-level** in llm_router. Resolved by the helper having one import site.
- Prompt loading: parser/formatter/llm_router each have a `_load_*_system_prompt` that raises `FileNotFoundError` on missing file. tier3_handler returns a hardcoded inline fallback string. This is intentional difference — tier3 wants graceful fallback on missing prompt — not a drift bug.

**Stays at the call site (not consolidable):**

- `max_tokens`, `temperature`, model strings — caller-specific
- Return shapes: tier2_parser `(Optional[Tier2Filters], int | None, int | None)` (i.e. `(filters | None, in | None, out | None)`); tier2_formatter `(text, in, out)`; llm_router `RouterDecision | None`; tier3 `(text, total, in, out)` — caller-specific
- `llm_router`'s latency timing + structured log line — caller-specific
- `tier2_formatter`'s deterministic-events bypass — never calls the LLM for all-event rows

### Test mock surface (the key constraint)

The mock seam picture is the single most important refactor-safety input. Two patterns in use:

**Pattern 1 — public-function patches at the importing module's path.** Tests don't patch `app.chat.tier2_parser.parse`; they patch `app.chat.tier2_handler.tier2_parser.parse`. Same for `format` (patched as `app.chat.tier2_handler.tier2_formatter.format`), `route` (`app.chat.unified_router.llm_router.route`), `answer_with_tier3` (`app.chat.unified_router.answer_with_tier3`), `extract_hints` (`app.chat.unified_router.extract_hints`). Standard "patch where used, not where defined" practice. **Refactor-invisible** as long as public function names and locations don't change.

**Pattern 2 — package-level patches on the Anthropic SDK class.** Many tests do `patch.object(anthropic, "Anthropic", ...)` where `anthropic` is imported at the test-file top level. This patches `Anthropic` on the package itself. Any code in the process doing `import anthropic; anthropic.Anthropic(...)` picks up the fake. Hits across:

- `tests/test_tier2_parser.py`, `test_tier2_parser_date_extraction.py`
- `tests/test_tier2_formatter.py`
- `tests/test_llm_router.py`
- `tests/test_tier3_handler.py`, `test_tier3_local_voice_injection.py`, `test_tier3_user_text_context.py`
- `tests/test_tier2_routing.py`, `test_phase2_integration.py`

**Survey gap (resolved in commit 4.5, `b79d000`):** `tests/test_ask_mode.py` and `tests/test_api_chat_e2e_ask_mode.py` were outside this original enumeration. They used `sys.modules["anthropic"]` substitution, which worked with legacy tier3's lazy `import anthropic` but not with the helper's import-time binding to `anthropic`. Commit 4.5 aligned both files with the standard seam via `monkeypatch.setattr("app.core.llm_messages.anthropic", ...)`.

**No tests patch module-scoped imports** (e.g., `app.chat.tier2_parser.anthropic`). **No tests patch the private helpers** (`_extract_text_from_message`, `_coerce_llm_text_to_json_object`, `_usage_in_out`, `_split_usage`). **Import exception:** `tests/test_llm_router.py` imports `_load_router_system_prompt` directly (for prompt-text assertions), which is why a thin delegate remains in `app/chat/llm_router.py` post-migration until that test switches to `load_prompt`.

**Implication**: the helper module is mock-safe iff it preserves the exact `anthropic.Anthropic(api_key=..., timeout=...)` and `client.messages.create(model=, max_tokens=, temperature=, system=, messages=)` call shapes. The helper must `import anthropic` (not `from anthropic import Anthropic`) so package-level `patch.object(anthropic, "Anthropic", ...)` continues to take effect. Do not pass **additional** keyword arguments to `messages.create` unless the change is deliberate and tests are updated accordingly. Private helpers move freely.

Two ancillary patterns also confirmed safe:

- `tests/test_prior_entity_router.py` injects `answer_with_tier3=` and `extract_hints=` as callable parameters — refactor-invisible.
- `tests/test_confabulation_*.py` reassigns `tier2_formatter.format` directly (not via `patch()`) — survives so long as the symbol stays at that path.

### Other Anthropic callers

`grep` for `anthropic.Anthropic` and `client.messages.create` outside the four chat modules and outside tests turned up exactly one match: **`scripts/run_voice_audit.py`** (lines ~855, ~868, ~1081). No matches in `app/eval/` or `app/api/`. Maintenance script; out of H2 scope (see §4).

### Pytest baseline

Confirmed: 942 passing / 8 known seed-fixture failures (collection: 950 tests). Matches documented baseline; gates every commit.

---

## Decisions

### 1. Helper shape

Single bundled-result API, not three independent extractors:

```python
@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int

    @property
    def billable_input(self) -> int:
        """Same token arithmetic as legacy (input + cache_read + cache_creation, output).

        Matches observability tuples used today; not a claim about Anthropic invoice semantics.
        """
        return (
            self.input_tokens
            + self.cache_read_input_tokens
            + self.cache_creation_input_tokens
        )

@dataclass(frozen=True)
class AnthropicResult:
    text: str
    usage: Usage
    raw: Any  # SDK message; exposed for caller-specific needs

def call_anthropic_messages(
    *,
    system_prompt: str,
    user_text: str,
    max_tokens: int,
    temperature: float,
    model: str | None = None,
) -> AnthropicResult | None:
    """Returns None on any failure: missing key, import failure, API exception, empty response."""

def coerce_llm_text_to_json_object(raw: str) -> dict[str, Any] | None:
    """Strip leading/trailing triple-backtick fences. Return None if not a JSON object."""

def load_prompt(name: str) -> str:
    """Read prompts/<name>.txt at repo root. Raise FileNotFoundError if missing.

    Strict behavior only — no optional fallback parameter. tier3 graceful fallback on
    missing prompt stays at the tier3 call site, not inside load_prompt.
    """
```

**Why bundled, not three separate `extract_*` functions**: once you have the SDK message you almost always want both text and usage. Splitting them adds boilerplate at every call site without giving anything back. `raw` is exposed on `AnthropicResult` for the rare caller that needs SDK fields outside text/usage (none today; nearly free to expose).

**Why `Usage` as a typed object with `billable_input`**: replaces both the `_usage_in_out` (msg → tuple) and `_split_usage` (usage → tuple) shapes with one object. Callers reproduce the current `(in, out)` tuple via `usage.billable_input, usage.output_tokens` — clearer at the call site and unambiguous about cache-token attribution.

**Why include `coerce_llm_text_to_json_object` and `load_prompt`**: both are duplicated (coerce: 2 callers, prompt loading: 4 callers) and trivially testable. The review's three-helper suggestion was a candidate shape; consolidating these two extends the same logic without expanding API confusion.

**Model resolution**: helper accepts optional `model`; if `None`, falls back to `os.getenv("ANTHROPIC_MODEL")` then to `DEFAULT_MODEL` defined in the helper module. All four current callers use the same default (`claude-haiku-4-5-20251001`) — document `DEFAULT_MODEL` to match this explicitly so env drift does not slip in during refactors. Per-caller overrides via the optional parameter remain possible.

### 2. Helper location

New module `app/core/llm_messages.py`. `app/core/llm_http.py` keeps its single timeout constant; the new module imports from it.

*For extending `llm_http.py`*: single anchor; one fewer import per caller; timeout is the closest existing relative.

*For new module*: `llm_http` reads as transport-level (timeouts, HTTP behavior); message-shape helpers are a distinct abstraction. The new module will be ~100-150 lines once written; mixing into the current 11-line `llm_http.py` makes the timeout constant a footnote in a module ostensibly named for HTTP. "messages" matches the Anthropic API noun. Tests get a clean target (`tests/test_llm_messages.py`). Future vendor expansion (see §3) follows module-per-abstraction pattern.

New-module side wins on naming clarity at the cost of one extra import per caller. Worth it.

### 3. OpenAI hint_extractor

Defer. Out of H2 scope.

The review suggested moving it to its own helper "for consistency" — but consistency-with-what is the question. Today it's a single OpenAI caller with no duplication. The helper-extraction pattern only pays off when there are multiple callers drifting; one caller is just abstraction debt. If a second OpenAI caller emerges, a parallel `app/core/llm_chat.py` (OpenAI's API noun) follows the same pattern this ship establishes.

Backlog: "extract OpenAI client into `app/core/llm_chat.py` if/when a second OpenAI caller appears."

### 4. scripts/run_voice_audit.py

Defer. Note as known sixth Anthropic caller that remains a copy of the boilerplate after H2.

Out of `app/chat/` scope; scripts run manually, not on production critical path; expanding scope adds risk to a refactor already touching four production files. After H2 ships, `run_voice_audit.py` can opportunistically migrate as a one-commit follow-on (low risk: no test coverage requirements, run on demand).

Backlog: "migrate scripts/run_voice_audit.py to app.core.llm_messages helpers."

### 5. Mock-seam preservation (hard constraint)

The helper MUST:

- Use `import anthropic` (not `from anthropic import Anthropic`) so package-level `patch.object(anthropic, "Anthropic", ...)` continues to take effect.
- Call `anthropic.Anthropic(api_key=api_key, timeout=LLM_CLIENT_READ_TIMEOUT_SEC)` with no additional kwargs. Timeout from `app.core.llm_http`.
- Call `client.messages.create(model=, max_tokens=, temperature=, system=, messages=)` with exactly these kwargs and no others unless the change is deliberate and tests are updated.

These constraints come directly from the test mock surface. Deviating breaks `tests/test_tier2_parser.py`, `tests/test_tier2_formatter.py`, `tests/test_llm_router.py`, `tests/test_tier3_handler.py`, and several integration tests. Document in the helper module's docstring so future edits don't regress this.

### 6. Commit plan

Five commits. Pytest baseline (942/8) gated after each. Halt-and-report between every commit. BOM-free messages via temp file.

**Commit 1 — Introduce helpers, no callers.**

- Add `app/core/llm_messages.py` with `Usage`, `AnthropicResult`, `call_anthropic_messages`, `coerce_llm_text_to_json_object`, `load_prompt`, `DEFAULT_MODEL`.
- Add `tests/test_llm_messages.py` with isolated coverage: text extraction (empty content, single block, multiple blocks, non-text blocks ignored); usage extraction (none, all four token fields, missing fields default to 0); JSON coerce (plain object, fenced block, fenced + language tag, non-object returns None, malformed returns None); load_prompt (existing file, missing file raises); `call_anthropic_messages` happy path with `patch.object(anthropic, "Anthropic", ...)`; failure paths (no key, no anthropic package, exception during create, empty response).
- Suite: 942 + N passing / 8 known (collection **succeeds with no errors**; total collected count **increases by N** after this commit — do not treat "950" as a fixed cap forever).

**Commit 2 — Migrate `tier2_formatter._format_via_llm`.**

Smallest call site (text-only return, no JSON parse). Helper shakedown. Replace inline boilerplate with `call_anthropic_messages`; remove now-dead local `_extract_text_from_message`, `_usage_in_out`, `_load_formatter_system_prompt`.

**Commit 3 — Migrate `tier2_parser.parse`.**

Adds JSON parse path via `coerce_llm_text_to_json_object`. Remove now-dead local helpers.

**Commit 4 — Migrate `llm_router.route`.**

Module-level `import anthropic` goes away (helper handles it). Latency timing wrapper stays at call site (`t0 = time.perf_counter()` ... `(time.perf_counter() - t0) * 1000.0`). Structured log line stays at call site. Remove now-dead local helpers.

**Commit 5 — Migrate `tier3_handler.answer_with_tier3`.**

Most complex caller (4-tuple return, biggest user_text construction). Tier3's prompt-loading wrapper (try/except → fallback string) stays at call site since the fallback is specific behavior, not boilerplate. Remove now-dead local helpers.

Cleanup happens **within each migration commit** rather than as a separate final commit. Self-contained migrations; easier to revert one in isolation if production drifts post-deploy. The ship has no separate "cleanup commit."

### 7. Pre-push discipline (the `--collect-only` question)

Keep `pytest --collect-only` as pre-push backstop, same as H1.

Reasoning differs from H1 (which used it because deletion can break import-time references): H2 doesn't delete public functions, but it adds a new module and new test file. `--collect-only` catches import errors in the new test file before runtime — cheaper than waiting for full pytest to fail at collection. Cost ~3 seconds; benefit non-zero on every commit that touches imports. Discipline already established from H1; carrying forward costs nothing.

Pre-push protocol per commit:

1. `pytest --collect-only -q` — collection succeeds with no errors. After
   commit 1 (which adds `tests/test_llm_messages.py`), the collected total
   rises by N and remains stable across commits 2–5.
2. `pytest -q` — passing count is `942 + N` from commit 1 onward, where N
   is stable across commits 2–5. The 8 known seed-fixture failures (missing
   `HAVASU_CHAT_MASTER.md`) remain unchanged. Any other delta is a halt
   condition.
3. Git push only after both pass.

### 8. Production verification

Pre-deploy: full pytest baseline confirmed (item 7).

Post-deploy monitoring window: 24-48h. Watch `chat_logs`:

| Bucket | Baseline (last 30d) | Watch threshold |
|---|---|---|
| `tier_used = '2'` | latency ~3103ms, tokens ~2158 | >5% drift either direction |
| `tier_used = '3'` | latency ~2806ms, tokens ~2902 | >5% drift either direction |
| `tier_used = NULL` | 6 rows / 30d (~0.2/day) | >2/day sustained |
| Error rate by tier | `'2'` and `'3'` failures rare | any sustained uptick |

The most likely subtle regression is **token-count drift**: if `Usage.billable_input` math is off by even one term (e.g., missing `cache_creation_input_tokens`), tokens shift visibly even when latency and user-facing behavior look fine. The helper's unit tests cover all four token fields explicitly to prevent this.

Fix-forward strategy: per-commit revert. Each migration commit is small enough to revert in isolation — Tier 2 drift → revert commit 2 or 3; Tier 3 drift → revert commit 5. This is the main argument for one-caller-per-commit migration over batching.

### 9. Effect on the maintainability findings

H2's disposition was "fix now"; this design implements it. After H2 shipped:

- The H2 finding is closed.
- `scripts/run_voice_audit.py` remains a noted residual copy of the boilerplate (visible, not migrated by H2).
- `app/chat/hint_extractor.py` remains on its own helper-less path (not closed by H2; opened as a backlog item).
- H3 (hardcoded entity list) is independent and unaffected.

The original maintainability priority order (H1 → H2 → H3) still describes sequencing intent. H1 (router investigation) and H2 (LLM infra) are complete; H3 follows.

---

## Proposed Session 2

Session 2 runs in a **fresh chat** bootstrapped from **`docs/maintainability/h2_session2_handoff.md`** (paste the body of that file below its HTML header comment). That handoff is intentionally thin; this decision document remains canonical.

Session 2's first commit is "introduce helpers, no callers" (commit 1 above); each subsequent commit migrates one caller. Halt-and-report between every commit, BOM-free messages via temp file, full pytest gate per commit.

---

## Session 2 kickoff (operational checklist)

Use this section when starting Session 2 (or paste **`h2_session2_handoff.md`** into a new chat instead of this full document — see HTML header at top).

1. **Read first:** `docs/maintainability/h2_consolidation_decision.md` (this file) — mandatory full read; especially §Findings (mock surface) and §Decisions §1, §5, §6.
2. **Canonical kickoff paste:** `docs/maintainability/h2_session2_handoff.md` — body only, below its HTML comment.
3. **First commit scope:** Add `app/core/llm_messages.py` + `tests/test_llm_messages.py` only; **zero** changes to `tier2_parser`, `tier2_formatter`, `llm_router`, `tier3_handler`.
4. **Gates after every commit:** `pytest --collect-only -q` (no errors); `pytest -q` → **942 passed / 8 failed** baseline.
5. **Working agreement:** halt-and-report between commits unless Casey directs otherwise; BOM-free commit messages; push only when authorized.
6. **Residuals (do not block Session 2):** `hint_extractor` OpenAI path; `scripts/run_voice_audit.py` — see §3–4.

---

**End of decision document (Session 1 filing).**

---

## Status — completed

H2 shipped as a seven-commit stack:

| Hash | Commit |
|------|--------|
| `b47ada6` | Commit 1: introduce `app/core/llm_messages.py` + tests |
| `e489c48` | Commit 1.5: preserve usage on empty-text responses |
| `2152c5a` | Commit 2: migrate `tier2_formatter._format_via_llm` |
| `cf59fbb` | Commit 3: migrate `tier2_parser.parse` |
| `a4bf866` | Commit 4: migrate `llm_router.route` |
| `b79d000` | Commit 4.5: align integration tests with helper-bound seam |
| `f7b28df` | Commit 5: migrate `tier3_handler.answer_with_tier3` |

The two “.5” commits were not in the original five-commit plan; rationale is in their commit messages.

**Gate:** 970 tests passed / 8 failed from commit 1.5 onward (seed/master fixtures). Commit 1 alone gated at 969 passed / 8 failed before commit 1.5 added one test.

**Backlog deferred** (unchanged from §3–4 and migration notes):

- `scripts/run_voice_audit.py` — sixth Anthropic caller; out of chat scope; opportunistic migration.
- `app/chat/hint_extractor.py` — OpenAI caller; deferred per §3.
- `tests/test_llm_router.py` refactor + `_load_router_system_prompt` delegate removal — small follow-on.
- Optional helper widening (`AnthropicResult`-level resolved model for logs) — defer until a second caller needs it.

### Documentation audit (post-ship)

A read-only sweep on **2026-04-29** inventoried stale references to pre-merge helpers and code excerpts across `docs/`. Outcomes are captured in this documentation commit: canonical corrections live in this file (§Findings above and this section); investigation/spelunk markdown files carry top-of-file **Status** banners pointing here instead of rewriting historical excerpts; two product specs receive one-line call-shape updates (`tier3-option-b-unlinked-events-spec.md`, `tier2-grounding-and-gap-fix-spec-v2.md`); `h1_router_decision.md` notes H2 completion. Per-commit session halt reports were removed from the tree — their substance is in **git log**.
