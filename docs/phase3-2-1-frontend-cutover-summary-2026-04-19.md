# Phase 3.2.1 — frontend cutover + plain-text system prompt — summary — 2026-04-19

## Scope

Single consolidated change: static UI calls the concierge API; Tier 3 system prompt forbids markdown. **No** legacy `POST /chat` removal; **no** backend router/schema edits.

---

## 1. `app/static/index.html`

| Change | Detail |
|--------|--------|
| Fetch URL | `fetch("/chat", …)` → **`fetch("/api/chat", …)`** |
| Request body | `{ session_id, message }` → **`{ session_id, query }`** — matches `ConciergeChatRequest` in `app/schemas/chat.py` (`query` required, `session_id` optional). |
| Response handling | Still uses **`data.response`** for the bot bubble. Optional **`data.data.open_calendar`** remains guarded (`data && data.data && data.data.open_calendar`); safe when absent on concierge responses. |

---

## 2. `prompts/system_prompt.txt`

**Added** a **`Response style:`** block (same heading pattern as **`Hard rules:`**) with:

- Respond in plain text only. Do not use markdown formatting — no asterisks, bold, italics, or headers.

**Note:** Before this edit, the file had **no** pre-existing “Response style” section (only intro, Hard rules, then the context instruction). The new heading was introduced so the plain-text rule lives under an explicit **Response style** section per Phase 3.2.1 spec.

---

## 3. Verification (pre-commit)

| Check | Result |
|--------|--------|
| Full test suite | **`pytest -q`** — **385 passed** (count unchanged). |
| Tracked changes | Only **`app/static/index.html`** and **`prompts/system_prompt.txt`**. |
| Diff review | `/api/chat`, `query`, `data.response` path; prompt addition only as above. |

---

## 4. Git

| Item | Value |
|------|--------|
| Commit | `41deff3` |
| Message | `chat: Phase 3.2.1 — frontend cutover to /api/chat + plain-text system prompt` |
| Push | `8819059..41deff3` → **`origin/main`** (Railway auto-deploy expected). |

---

## 5. Owner follow-up (not automated here)

After deploy:

1. Wait for Railway deploy to finish.
2. Open `https://havasu-chat-production.up.railway.app/`.
3. Ask: *“what's the phone number for altitude?”* — expect **Tier 1** concierge answer (not Track A “no altitude in the system”).
4. Ask: *“what's good for a date night?”* — expect **Tier 3** reply **without** markdown asterisks.
5. Anthropic Console → Usage: confirm new requests as appropriate.
