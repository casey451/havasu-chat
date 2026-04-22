# Phase 6.4.1 — Manual (a) live verification (2026-04-22)

Saved from the implementation chat.

---

## What was done

1. **Stopped the old listener** — `Get-NetTCPConnection` showed **PID 27112** on port **8765**; `Stop-Process` killed it; port was free.

2. **Started a new uvicorn** — From `c:\Users\casey\projects\havasu-chat` with  
   `.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765`  
   - **New worker PID:** **29820** (not 27112).  
   - **8765** was in **Listen** on `127.0.0.1`.  
   - Log showed **new** `hint_extractor` warnings on the two chat turns (this process handled the manual run).

3. **Manual scenario (a)** — Fresh `session_id` `man-a-live-d3e11d281d25`, `POST /api/chat` to `http://127.0.0.1:8765`.

---

## Manual (a) result — **PASS**

**Turn 1** — `what should i do tomorrow`

- **tier_used:** `3`
- **sub_intent:** `OPEN_ENDED`
- **entity:** `null`
- **Response (summary):** Single clear recommendation — **Altitude Trampoline Park** for tomorrow (Wednesday), 11am–7pm, $19 open jump, etc.

**Turn 2** — `what time does it open`

- **tier_used:** `3`
- **sub_intent:** `TIME_LOOKUP`
- **entity:** **`Altitude Trampoline Park`** (bound from session / prior; **not** the “which place?” dead-end).
- **Response (summary):** Hours-style answer for **Altitude** (e.g. 10am / Tuesday window — model wording; important part is **no disambiguation prompt**).

On a **restarted** server with **current tree (6.4.1 + uncommitted changes)**, (a) behaved as intended: Tier 3 names one catalog provider, then the pronoun follow-up **resolves** to that provider instead of asking for a name.

---

## Next step

**No commit** from that verification step alone. When ready to land on `main`, use **`approved, commit and push`** (or commit locally).

**Note:** A uvicorn process may still be running on **8765** (e.g. PID **29820**). Stop it when finished, or leave it for further checks.
