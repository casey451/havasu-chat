# Tech-Direction Decision — havasu-chat

**Date:** 2026-06-04 · **Mode:** read-only audit (no code changed) · **Method:** dynamic fan-out across agent-friendliness and memory/resource-leak hunts, synthesized with the three prior audits (`RUST_MIGRATION_AUDIT`, `SECURITY_AUDIT`, and the optimization pass). All key claims verified against code.

**Question asked:** what's the best technical direction for this codebase optimizing for (1) safe future additions by AI coding agents, (2) security, (3) memory leaks, (4) speed — Rust suspected, open to anything.

---

## The decision in one paragraph

**Do not rewrite in Rust. Adopt a "typed Python core" instead.** Every one of the four goals points to the same small set of cheap, low-risk changes — and away from a language migration. The headline reason is counterintuitive but solid: the thing that would most help *agents* write safe future code is **compile-time type checking**, and you can get ~80% of that benefit by turning on `mypy` (the code is already 76% annotated and uses modern SQLAlchemy 2.0 `Mapped[]` types) — in the language agents are most fluent in. Rust's signature advantage is memory-*corruption* safety, which Python already provides, so on three of your four axes (security, memory leaks, speed) Rust barely moves the needle, while on the fourth (agent throughput) a rewrite would actively *hurt* in the near term by pushing agents off FastAPI/SQLAlchemy — where their training is deep — onto axum/sqlx, where it's thin.

---

## Scorecard: the realistic options against your four goals

Scale: ++ strong help, + some, 0 neutral, − hurts.

| Option | Agent-safety | Security | Memory leaks | Speed | Migration risk | Net |
|---|---|---|---|---|---|---|
| **A. Typed Python core** (mypy strict incrementally + TypedDicts on payloads + branch protection + pre-commit) | **++** | + | + | 0 | **very low** | **Recommended** |
| B. Typed core **+ one PyO3 Rust crate** for fuzzy matching | ++ | + | + | + (batch only) | low–med | Optional add-on |
| C. Sidecar Rust service (matching/dedup) | 0 | 0 | 0 | + | med–high | Rejected |
| D. Full Rust rewrite (axum + sqlx) | − (near term) | 0 | + (RAII) | + | **extreme** | Rejected |

Why the Rust columns are so weak is the whole story — walked through below, goal by goal.

---

## Goal 1 — Safe future additions by coding agents (this is the real lever)

This is where the biggest unrealized win is, and it's a config change, not a language. Findings (all verified):

- **No static type checking exists at all.** No `mypy`, no `pyright`, no config anywhere — yet **1,430 / 1,884 functions (76%) already have return annotations**, `models.py` has 574 typed `Mapped[]` columns and zero legacy `Column()`, and there are 41 Pydantic models. The annotations are written; nothing is *checking* them. Turning on mypy is days of work, not weeks.
- **The #1 place agents will introduce silent bugs is stringly-typed output.** There are **467 `dict[str, Any]` sites**; `component_builders.py` (1,203 LOC) returns bare `dict[str, Any]` component payloads, and the chat router threads a raw `session: dict` of conversational state. An agent that renames a key or reshapes a nested dict gets **zero** compile-time feedback and may not trip a test. This is exactly the class a type checker catches.
- **Lint is enforced but minimal** — ruff runs only `["F","I","W","E402"]` (verified), so it catches typos and import order, not logic or missing annotations.
- **CI gate exists but the floor is missing.** `ci.yml` runs ruff + pytest on every PR (good), but per CLAUDE.md there is **no branch protection on `main`** — and `main` auto-deploys to prod. For bypass-permission agent sessions, "the agent was told not to push to main" is honored, not enforced. One GitHub setting closes this.
- **Strengths worth preserving:** CLAUDE.md is unusually good (leads with the prod-deploy hazard, clear approval gates); timezone hygiene is excellent (only 1 naive `datetime.now()` vs 145 tz-aware sites); golden/snapshot tests exist (the disclosure regression golden is the model to copy); package boundaries are clean with no circular-import tangle.

**Would Rust help agents more than mypy?** In principle a compiler rejects bad code harder. In practice, for *this* project it's the wrong trade: agents are far more fluent in Python/FastAPI than in the niche Rust web/ORM crates, so a rewrite *lowers* near-term agent code quality; and `mypy --strict` + Pydantic + `TypedDict` payloads recover most of the compile-time-safety benefit while keeping agents in their strongest language. The compiler-safety argument is real — it just argues for **mypy**, not Rust.

## Goal 2 — Security

The security audit's findings are **all** in categories Rust does not address: the `changeme` default password/session-secret fallback (a default-value choice — equally writable in Rust), missing CSRF tokens (a framework feature you add either way), the SSRF DNS-rebinding gap (a logic flaw; `reqwest` re-resolves too), the unbounded chat-query length (Pydantic actually gives you `max_length` for *free*; Rust would need a validator crate). Memory-corruption CVEs — Rust's one categorical security win — don't exist here because Python is memory-safe and the binary parsing is delegated to mature C libs. A rewrite would also *temporarily reduce* security by reimplementing authentication (the worst thing to hand-roll) and discarding 2,827 tests' coverage during cutover. **Verdict: Rust is security-neutral-to-negative here; the wins are the cheap fixes already documented.**

## Goal 3 — Memory leaks

The leak hunt found the resource discipline is **already good** — DB sessions, file handles, PDFs, Playwright browsers, and most HTTP clients are properly context-managed. Two real issues, both verified:

- **HIGH — `_LAST_SEEN_MONO` grows unbounded forever** (`app/auth/session.py:30,69`): a module-level dict keyed by session id, written on every authenticated request, **never pruned** (no eviction on logout/expiry/timer). Slow (~100 bytes/entry) but genuinely unbounded over a multi-day process. **Rust would NOT prevent this** — a `HashMap` you only `insert()` into leaks identically in safe Rust. It's a logic bug; fix is eviction (a `TTLCache` / prune-on-write), one small change.
- **MEDIUM — per-call `OpenAI()` clients never closed** (`hint_extractor.py:67`, `llm_cache.py:86`, +4 sites): each builds an httpx connection pool and relies on GC to release sockets — FD/socket churn on the chat hot path. **This is the one class Rust's RAII would tighten** (deterministic drop on scope exit). But a process-wide singleton client fixes it equally in Python *and* cuts latency — the better fix regardless of language.

So: the only *unbounded* leak is one Rust would reproduce verbatim; the one Rust-helped case has a one-line Python fix that's also faster. **Neither is a memory-corruption bug — the only thing Rust categorically prevents. Memory leaks are not an argument for Rust here.**

## Goal 4 — Speed

Covered in depth in the optimization and Rust audits: latency is dominated by LLM API calls (seconds) and Postgres, and the one CPU hot spot (fuzzy matching) already runs on rapidfuzz's C++ core — Python is just the loop driver. The real waste is **algorithmic** (O(N) brute-force dedup in `events/dedup.py`, N+1 queries on category pages, missing composite indexes), all fixable in Python in days. A Rust matcher would shave ~10ms → ~1–3ms on a path that often includes a 1,000ms+ LLM call — real but invisible. Plus the OpenAI-singleton fix above removes per-request client construction. **Speed argues for the algorithmic fixes, not a rewrite.**

---

## Recommended roadmap (ranked by ROI, all low-risk, no prod DB writes)

**Tier 1 — do these first (days each, highest ROI for agent-driven dev):**
1. **Turn on mypy incrementally.** Add `[tool.mypy]` + the SQLAlchemy plugin to `pyproject.toml`; start non-strict tree-wide, then enforce `disallow_untyped_defs` module-by-module beginning with `app/chat/` and `app/db/`. Add a mypy job to `ci.yml`. Directly kills the top agent-bug classes.
2. **Enable GitHub branch protection on `main`** (require PR + passing CI, block direct push). Converts every CLAUDE.md "never push to main" from advisory to physically enforced — the correct floor for agent sessions.
3. **Fix the security top items:** verify `ADMIN_PASSWORD` + a separate `HAVA_SESSION_SECRET` are set in prod and make the app fail-closed when unset; add `max_length` to the chat query; add CSRF tokens.

**Tier 2 — type the boundaries + close the leaks (1–2 weeks):**
4. Replace `component_builders.py`'s `dict[str, Any]` returns with `TypedDict`/Pydantic shapes, and define a `SessionState` type for the router's `session` dict. This is where mypy pays off most for agents.
5. Add eviction to `_LAST_SEEN_MONO`; make `OpenAI` a process-wide singleton.
6. Add `pytest-xdist` (`pytest -n auto`) for a faster, shardable inner loop; add a `pre-commit` config running ruff + mypy so agents get the gate locally.

**Tier 3 — performance + hygiene (opportunistic):**
7. Fix the O(N) dedup (index/prefilter), category-page N+1s, and add composite indexes (alembic migration → PR → your approval).
8. Split the god-files when you next touch them: `admin/router.py` (2,245 LOC), `models.py` (1,831 LOC, imported by 106 modules), `component_builders.py`. Smaller files = smaller blast radius for agent edits.
9. Clean up the ~25 stale root `.md`/`.cmd`/`.log` files so agents orient on CLAUDE.md, not decoys (see the dead-code audit).

**Optional, only if a future CPU-bound workload justifies it:**
10. One PyO3 crate (`havasu_match`) for fuzzy scoring, shadow-tested behind a flag, Python kept as permanent fallback (full plan in `RUST_MIGRATION_AUDIT_2026-06-04.md`). This is the *entire* defensible Rust footprint, and it's optional.

---

## Bottom line

You came in suspecting Rust; the evidence says the honest answer is **"typed Python, enforced."** Rust's one categorical advantage — memory-corruption safety — is moot in a memory-safe language, and your actual goals (agent-safe additions, security, leak-prevention, speed) are each better served by mypy + branch protection + a handful of targeted fixes than by a 6–12 month rewrite that would *raise* risk on a solo-operated, main-auto-deploys-to-prod codebase. Keep Rust in your pocket for exactly one optional fuzzy-matching crate. Spend the effort on the type checker and the guardrails — that's what makes the next hundred agent edits safe.
