# Phase 3-close — completion handoff (for Claude)

## Summary

Phase 3-close delivered two items in **one commit**, pushed to **`main`**:

1. **§1a addendum** in `HAVASU_CHAT_CONCIERGE_HANDOFF.md` — new subsection *LLM-inferred facts as a contribution source* immediately after *What this does NOT change* and before the `---` that precedes §2.
2. **Read-only cost analytics script** — `scripts/analyze_chat_costs.py` (stdout only, no DB writes, no query text).

---

## Commit

- **SHA:** `04f6c65`
- **Message (exact):** `Phase 3-close: §1a addendum (LLM-inferred facts) + cost analytics script`
- **Remote:** pushed to `origin/main`
- **Files changed in commit only:**
  - `HAVASU_CHAT_CONCIERGE_HANDOFF.md`
  - `scripts/analyze_chat_costs.py`

---

## §1a — before / after (modified region only)

### Before (parent `8601c4e`)

```text
### What this does NOT change

- Phase 3.2 and 3.2.1 as currently shipped are correct and stay.
- The seven locked decisions stay.
- Phase 3.3 (end-to-end ask-mode tests) proceeds as planned.
- This vision informs Phase 4+ design; it is not a Phase 3 change.

---

## 2. The Seven Locked Decisions
```

### After (current)

```markdown
### What this does NOT change

- Phase 3.2 and 3.2.1 as currently shipped are correct and stay.
- The seven locked decisions stay.
- Phase 3.3 (end-to-end ask-mode tests) proceeds as planned.
- This vision informs Phase 4+ design; it is not a Phase 3 change.

### LLM-inferred facts as a contribution source

In addition to user contributions, Tier 3 LLM responses can surface factual claims that aren't yet in the catalog (e.g., "Rotary Park has a gymnastics program Tuesdays"). Phase 4's review queue should accept these as a distinct source type ("LLM-inferred") alongside user contributions ("user-submitted"). LLM-inferred facts never bypass review — they are treated as unverified contributions with no URL backing until an operator confirms and either links a URL or marks them as "community tip — unverified." This preserves §1a's URL-evidence policy while allowing the catalog to learn from usage patterns. Concrete design deferred to Phase 4 scoping.

---

## 2. The Seven Locked Decisions
```

---

## Script

- **Path:** `scripts/analyze_chat_costs.py`
- **Behavior:** Uses existing app DB session (`SessionLocal`) + `ChatLog`; filters `chat_logs` on `created_at` for last 30 days (UTC cutoff); aggregates tier, `llm_tokens_used` NULL vs non-NULL, Tier 3 token stats + Haiku-style USD bounds (input $1/M, output $5/M) with notes that combined tokens / split not stored; mode distribution; top 10 `sub_intent` for `tier_used == '1'` only. No file writes; no raw `query` / message text printed.
- **Env:** Works with `DATABASE_URL` (Postgres) or local SQLite fallback per app DB wiring; docstring at top of script documents this.

### Local verification command

```powershell
.\.venv\Scripts\python.exe scripts/analyze_chat_costs.py
```

### Verbatim stdout (local SQLite sample)

```text
=== Chat log cost / usage analytics ===
Window: last 30 days (created_at >= cutoff UTC)
Total queries (rows): 78
Date range (rows): 2026-04-18T22:12:09.408985 -> 2026-04-18T22:12:11.613197

--- Tier distribution (tier_used) ---
  (null): 78 (100.0%)

--- llm_tokens_used ---
  NULL (no LLM billable row): 78
  non-NULL: 0
  Note: Tier 1 paths typically have NULL tokens; Tier 3 stores a combined token total (input + output + cache-related) per tier3_handler - input vs output split is not captured in chat_logs.

--- Tier 3 token usage (tier_used == '3', llm_tokens_used NOT NULL) ---
  No Tier 3 rows with token counts in this window.

--- Mode distribution ---
  (null): 78 (100.0%)

--- Top sub_intent (tier_used == '1' only) ---
  No Tier 1 rows in this window.
```

### Tests

- `pytest -q`: **465 passed** (no test files modified in this work).

---

## Divergences / notes

1. **Windows console:** Script uses ASCII `->` and `-` in a couple of printed lines to avoid `UnicodeEncodeError` on `cp1252`; handoff body keeps supplied punctuation.
2. **Cost estimate when Tier 3 rows exist:** Script prints worst-case all-output, worst-case all-input, and a 50/50 illustrative line (combined `llm_tokens_used` has no input/output split in `chat_logs`).

---

## Scope confirmation (per original prompt)

- No `app/` production code changes in the commit (script only imports existing DB layer).
- No `requirements.txt`, tests, `prompts/`, `app/static/`, `HAVASU_CHAT_MASTER.md`, or seed doc changes in the commit.
- Production Railway DB was **not** queried for verification; local-only script run.
