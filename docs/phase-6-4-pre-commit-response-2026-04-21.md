# Phase 6.4 pre-commit response — 2026-04-21

Status after completing the requested work (**no commit**).

## 1. System prompt (`Now:`)

Replaced the old “Now” line with the authoritative paragraph, then added one more sentence so the model cannot use **“locked in”** to pretend the calendar anchor is missing when **`Now:`** is present (that was still happening on **Q6** in a local run).

Current block (end of `prompts/system_prompt.txt`):

```text
If a "Now" line appears before the Context block, treat it as the authoritative current date and time in Lake Havasu City. Do not hedge about not knowing the date — use the "Now" value directly to resolve relative temporal references in the user's query (today, tomorrow, tonight, this weekend, next week). It is not a source of catalog facts, but it IS the source of truth for what "today" means right now. Never respond with phrases like "I don't have tomorrow's date" or "let me know the date" when a "Now" line is present. Do not use "locked in" (or similar) to imply you lack the calendar anchor when Now is present — if nothing in Context matches that window, say the catalog has no matching entries for those dates instead of implying the date or weekend is unknown. The Context block remains the only factual source for catalog claims.
```

## 2. `.env` loading (gates 2–3)

- **`scripts/measure_hint_extractor_tokens.py`** — calls `ensure_dotenv_loaded()` at the start of `main()` before reading `OPENAI_API_KEY`.
- **`tests/test_classifier_hint_extraction_integration.py`** — inserts repo root on `sys.path`, then calls `ensure_dotenv_loaded()` before any `OPENAI_API_KEY` checks.

**`.env` check:** File exists at repo root and includes an `OPENAI_API_KEY=` line. In the environment where this was verified, that line had **no value after `=`** (so the key was not actually available to Python after `load_dotenv`). That matches gate behavior below.

## 3. Voice spot-check

`scripts/run_voice_spotcheck.py` **defaults to production**. A run that used only that default still hit **Railway**, which does **not** include uncommitted `prompts/system_prompt.txt`, so it is **not** a valid check of the new wording until deploy.

### Production run

Report: `scripts/output/voice_spotcheck_2026-04-21T20-27.md`

**Q6 / Q9 verbatim:**

- **Q6:** I don't have this weekend's specific date locked in, so I can't pull what's on yet. Try https://www.golakehavasu.com/events for what's posted, or let me know the date and I'll tell you what's in the catalog.
- **Q9:** I don't have tomorrow's date locked in, so I can't tell you what's on yet. Try https://www.golakehavasu.com/events for what's posted.

### Local server

Uvicorn + `--base http://127.0.0.1:8765` with **current repo** prompt. Latest report: `scripts/output/voice_spotcheck_2026-04-21T20-32.md`

**Q6 / Q9 verbatim:**

- **Q6:** This weekend (April 25–26) doesn't have events in the catalog yet. Altitude Trampoline Park is open Saturday 9am–9pm and Sunday 11am–7pm with 90-minute open jump sessions at $19 if you need something active — try https://www.golakehavasu.com/events for what else might be posted locally.
- **Q9:** The catalog has no events scheduled for tomorrow, April 22. Try https://www.golakehavasu.com/events for what's posted locally.

**Takeaway:** After deploy (or any production run), re-run the default script to close t3-01 on the production URL. Locally, the problematic “tomorrow’s date locked in” line is **gone**; Q6 no longer uses “locked in” for the weekend **date** (it still correctly separates “no catalog events” vs “things that are open”).

**Voice score:** The markdown report does **not** include an automatic pass/fail tally (no single “19/1/0” line in the file). No new numeric score was assigned in this pass.

**Surprise:** **Q20** (“live music tonight”) on the local report still said **“locked in”** for the *schedule*, not the calendar — if that should be gone too, the prompt may need a slightly broader rule, or a separate line for “tonight” non-catalog answers.

## 4. Gates 2–3 (integration + token measure)

| Gate | Result |
|------|--------|
| **Integration** (`pytest tests/test_classifier_hint_extraction_integration.py -m integration`) | **5 skipped** — `OPENAI_API_KEY` still unset after `ensure_dotenv_loaded()` (empty value in `.env` in that environment). **STOP:** not 4/5 or 5/5 passes. |
| **`measure_hint_extractor_tokens.py`** | **Exit code 2**, `OPENAI_API_KEY not set`. **STOP.** |

**Mean tokens:** Not produced (script did not run successfully).

## Process note

If a gate depends on a secret and the secret is missing after the agreed `.env` path, treat that as **STOP** and surface the missing dependency; do not imply “pre-commit complete” with unrun gates.

## What to do next

Put a real key on `OPENAI_API_KEY=` in repo-root `.env`, then re-run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_classifier_hint_extraction_integration.py -m integration -q
.\.venv\Scripts\python.exe scripts/measure_hint_extractor_tokens.py
.\.venv\Scripts\python.exe scripts/run_voice_spotcheck.py
```

(After deploy if you care about production for the default spot-check.)

**No commit** unless you send explicit approval to commit and push.
