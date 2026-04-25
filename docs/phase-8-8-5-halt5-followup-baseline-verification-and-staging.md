# Phase 8.8.5 — HALT 5 Follow-up

> **Status update (2026-04-25, post-validation):** The 8.8.5 approach
> subsequently failed validation. Rich-row confabulation persisted
> deterministically across 6/6 runs (3 flag-on, 3 flag-off). Commits
> `297086d` and `f8afb81` referenced in §3 were reverted by `c3562c9`
> and `d1fef0f`. The git log in §4 reflects pre-revert state. The
> "holding for push approval" status in §5 is superseded.
>
> This doc is retained as the historical record of the baseline-
> verification methodology (§1), which is reusable for any future
> phase that needs to confirm a test failure is pre-existing on a
> known-good baseline. Phase 8.8.6 step 0 (eval harness) is the
> follow-on phase that builds the measurement instrument 8.8.5's
> 12-query gate lacked.

Date: 2026-04-25  
Scope: Verify failing Phase 3 test is pre-existing on baseline `fedf0a8`, then proceed with Step 5 commit staging.

---

## 1) Baseline verification outcome

Result: **Outcome A confirmed** — the failing test is pre-existing and not introduced by 8.8.5 Step 3/4 changes.

### Procedure executed

1. Stashed all uncommitted work with:

```powershell
git stash push -u -m "8.8.5 step 3+4 wip"
```

2. Checked out baseline:

```powershell
git checkout fedf0a8
```

3. Ran the failing test under both flag states:

```powershell
$env:USE_LLM_ROUTER="false"; .venv/Scripts/python -m pytest tests/test_phase3.py::Phase3SearchTests::test_weekend_search_asks_activity_then_returns_grouped_results -v
$env:USE_LLM_ROUTER="true"; .venv/Scripts/python -m pytest tests/test_phase3.py::Phase3SearchTests::test_weekend_search_asks_activity_then_returns_grouped_results -v
```

4. Returned to `main`, restored stash, and verified Step 3/4 changes were restored:

```powershell
git checkout main
git stash pop
git status --short --branch
```

### Baseline test outcomes

- `USE_LLM_ROUTER=false`: **FAILED** (`1 failed`)
- `USE_LLM_ROUTER=true`: **FAILED** (`1 failed`)
- Failing test in both cases:
  - `tests/test_phase3.py::Phase3SearchTests::test_weekend_search_asks_activity_then_returns_grouped_results`
  - Expected `"Basketball Clinic"` in response
  - Actual response: `"Nothing on for that time. Want to peek at what's coming up later?"`

Conclusion: failure reproduces on unmodified baseline `fedf0a8`, therefore it is pre-existing.

---

## 2) Known-issues note update

Added a non-blocking persistence note in `docs/known-issues.md`:

- Entry title: **Phase 3 legacy test failure persists post-8.8.5 (`test_weekend_search_asks_activity_then_returns_grouped_results`)**
- Notes that it reproduces on `fedf0a8` under both flag states and remains non-blocking for 8.8.5 staging.

---

## 3) Step 5 commit staging (completed)

Commits were created in the requested order:

1. `297086d`  
   `feat(tier2): description richness classifier with featured-description precedence (Phase 8.8.5)`

2. `f8afb81`  
   `feat(tier2): formatter prompt sparse-row grounding rule (Phase 8.8.5)`

No push performed.

---

## 4) git log --oneline -10

- `f8afb81 feat(tier2): formatter prompt sparse-row grounding rule (Phase 8.8.5)`
- `297086d feat(tier2): description richness classifier with featured-description precedence (Phase 8.8.5)`
- `3b2f571 docs(8.8.5): pre-implementation spec drafts (v1 and v2)`
- `fedf0a8 feat(router): LLM router module behind USE_LLM_ROUTER flag (Phase 8.8.4)`
- `9b765b3 feat(tier2): recurring-dedupe selection fix for broad windows (Phase 8.8.4)`
- `fbf5d6c feat(tier2): Tier2Filters v2 schema with structured temporal fields (Phase 8.8.4)`
- `6aad4ab docs(8.8.4): pre-implementation working artifacts (audit, spec, diagnostics)`
- `6a99f4a feat(tier2): harden formatter grounding and reorder gap-template (Phase 8.8.3)`
- `26bdc32 Revert "feat(tier3): surface unlinked future events in context"`
- `88556bb feat(tier3): surface unlinked future events in context`

---

## 5) Hold status

Holding for owner push approval. No push executed.
