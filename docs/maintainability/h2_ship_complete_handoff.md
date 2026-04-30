# H2 consolidation — ship complete (handoff)

**Status:** Functionally complete. Seven commits on `main` (local until pushed).

---

## Final stack

```
f7b28df  H2 commit 5: migrate tier3_handler.answer_with_tier3 to llm_messages helper
b79d000  H2 commit 4.5: align integration tests with the helper-bound Anthropic seam
a4bf866  H2 commit 4: migrate llm_router.route to llm_messages helper
cf59fbb  H2 commit 3: migrate tier2_parser.parse to llm_messages helper
2152c5a  H2 commit 2: migrate tier2_formatter._format_via_llm to llm_messages helper
e489c48  H2 commit 1.5: preserve usage on empty-text responses
b47ada6  H2 commit 1: introduce app/core/llm_messages.py + tests
```

Gate held at **970 passed / 8 failed** across the stream; **§5** mock seam preserved; four caller migrations + helper + tests. Deviations from a literal five-commit plan (**1.5**, **4.5**) are documented in their commit messages.

---

## Where things stand

- **Remote:** Not pushed. Push when owner authorizes; the handoff policy is explicit go-ahead only.
- **Session-note files:** Some `h2_commit_5_*.md` (and similar) may remain untracked. **Git history is canonical**; keep or delete local session copies per preference, or add a single docs commit if the team wants them versioned.
- **Commit 5 message — historical nuance (no amend):** One sentence conflates “tier3 predates §1.5” with “tier3 doesn’t preserve usage on empty text.” The **correct** story: **legacy tier3** already returned `(FALLBACK_MESSAGE, None, None, None)` on empty extract; **legacy formatter** could preserve usage on empty text, and **commit 1.5** let the helper express that. Tier3’s behavior is **byte-identical to legacy tier3**, not a §1.5 exception. The **parity table** in the commit body is authoritative; the one-line “predates §1.5” framing is loose wording only.

---

## What’s left, in order

### 1. Push

All **seven** commits in **one** push is the recommended story; gates have been stable across the stack.

### 2. Post-deploy monitoring (24–48h) — §8

| Bucket | Baseline (last 30d) | Alert on |
|--------|---------------------|----------|
| `tier_used = '2'` | latency ~3103ms, tokens ~2158 | \>5% drift either way |
| `tier_used = '3'` | latency ~2806ms, tokens ~2902 | \>5% drift either way |
| `tier_used = NULL` | ~6 rows / 30d (~0.2/day) | \>2/day sustained |
| Error rate by tier | rare for `'2'` and `'3'` | any sustained uptick |

`tests/test_llm_messages.py` four-token-field checks guard arithmetic; production validates end-to-end.

**Fix-forward:** Per-caller revert — Tier 2 drift → `2152c5a` / `cf59fbb`; Tier 3 → `f7b28df`. Helper-wide issues would roll further back (unlikely). One-caller-per-commit enables this.

### 3. Post-H2 cleanup commit (after monitoring if possible)

**Concrete (worth one commit):**

- **`docs/maintainability/h2_consolidation_decision.md`:** parser return shape (**3-tuple**, not `Tier2Filters | None`); §Findings note tests may **import** private helpers (`_load_router_system_prompt`); §Findings note `test_ask_mode.py` / `test_api_chat_e2e_ask_mode.py` were outside the original survey, aligned in **4.5**.
- **`tests/test_llm_router.py`:** import **`load_prompt`** directly; remove **`_load_router_system_prompt`** delegate from **`app/chat/llm_router.py`**.

**Optional / defer:**

- Rename **`_mock_anthropic_sys_modules`** in `test_ask_mode.py` to a seam-accurate name (cosmetic).
- **`AnthropicResult.model`** (or similar) — only if a second caller needs it; defer indefinitely otherwise.

**Timing:** After the monitoring window shows stability; doc fixes matter most once production has validated the ship.

---

## Cleanup commit prompt

Can be drafted on request when the team is ready for the post-H2 pass.

---

*Stream halted from implementation side; push and cleanup are owner-driven.*
