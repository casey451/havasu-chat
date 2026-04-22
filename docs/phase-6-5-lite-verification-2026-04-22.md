# Phase 6.5-lite — verification report (2026-04-22)

Post-implementation gates: pytest, local uvicorn, voice spot-check, manual Local voice payload check. **No commit** — awaiting explicit `approved, commit and push`.

---

## 1) Full test suite

**Command:** `.\.venv\Scripts\python.exe -m pytest -q`

**Result:** **742 passed**, **0 failed** (~6m37s).

Baseline **726** + **16** new tests = **742** (matches the 6.5-lite additions on top of the post–6.4.1 baseline).

---

## 2) Local uvicorn (current tree)

- **First run (empty `LOCAL_VOICE`, spot-check):** `netstat` showed **`LISTENING … 31864`** on `127.0.0.1:8765` (shell parent **29940**). Root returned **HTTP 200**.
- **Restart after adding test blurb:** **`LISTENING … 29520`** — used for the first `/api/chat` POST.
- **Restart after stderr print for capture:** **`LISTENING … 2448`** — used for the second POST that printed the Local voice block.

---

## 3) Voice spot-check

**Command:** `.\.venv\Scripts\python.exe scripts/run_voice_spotcheck.py --base http://127.0.0.1:8765`

**Script:** exit **0**, smoke **OK**, report **`scripts/output/voice_spotcheck_2026-04-22T01-38.md`**.

**Score (manual, same convention as prior gates — 20-query battery):** **19 / 1 / 0** (PASS / MINOR / FAIL).

- **MINOR — Query 17** (*Boat rentals on the lake?*): **`tier_used: chat`** with the usual OOS line ending in *“Want me to point you to anything else?”* — same class of MINOR as in `docs/phase-6-4-pre-commit-gates-report.md`.
- **FAIL:** **0**

The markdown report also notes a **chat_logs row count mismatch** (expected 20 rows, got **0**) for local runs without Railway DB correlation — process-level metadata, not a query-level FAIL.

---

## 4) Manual verification (temp blurb → POST → capture → revert)

1. **Temp blurb** (not committed): added the specified dict to **`LOCAL_VOICE`** in `app/data/local_voice.py`.
2. **Restart** uvicorn so the module reloaded.
3. **POST** `http://127.0.0.1:8765/api/chat` with  
   `{"query": "what's happening Saturday night with BMX", "session_id": "test-6-5-lite"}`  
   **First response:** **`tier_used": "3"`** (Tier 3 path; `answer_with_tier3` ran).
4. **Payload logging:** `logging.info` for the Local voice slice did **not** appear in the uvicorn terminal (logger level). A **temporary `print(..., file=sys.stderr, flush=True)`** was used for one restart + repeat POST so the block appeared in server output. **That print was removed** afterward.

**Verbatim Local voice section** (as included in Tier 3 `user_text` before the catalog `Context` block):

```text
Local voice:
- The Saturday night BMX race at Sara Park is the one thing locals actually show up for.
```

5. **Cleanup:** test blurb **removed**; temporary **print removed**; `tier3_handler.py` restored to production-only behavior (no debug instrumentation).

---

## 5) `LOCAL_VOICE` before commit

**Confirmed:** `app/data/local_voice.py` again has **`LOCAL_VOICE: list[dict[str, Any]] = []`** (empty list).

---

## Commit status

**No commit** — waiting for **`approved, commit and push`**.
