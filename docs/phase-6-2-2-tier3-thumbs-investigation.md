# Phase 6.2.2 — Tier 3 thumbs not rendering (consolidated investigation)

**Date:** 2026-04-20  

This file merges **Task 1** (API / wire format) and **Round 2** (served HTML vs repo, handler review, schema, harness). Split copies still exist as `phase-6-2-2-tier3-thumbs-diagnosis-622.md` and `phase-6-2-2-tier3-thumbs-round2-report.md` if you prefer smaller docs.

---

## Executive summary

- **Production `POST /api/chat`** (curl sample) returned **`tier_used` as JSON string `"3"`**, a **non-empty `chat_log_id`**, and **long-form Tier 3** prose (not a short Tier 1 template). So the symptom “Tier 3 answer, no thumbs” is **not** explained by wrong tier on the wire for that sample.
- **Frontend** only calls `attachFeedbackThumbs` when `data.tier_used === "3"` **and** `data.chat_log_id` is truthy (`app/static/index.html` ~748–749).
- **Served `/` HTML** matches **`app/static/index.html` at `HEAD`** after normalizing line endings — **not** a stale/wrong `index.html` on Railway.
- **Remaining lead:** a **JavaScript runtime error** inside the success `.then` (or elsewhere after the bubble updates), or an environmental factor (extension, etc.). **DevTools Console** on a Tier 3 send is the fastest next check.

---

# Round 1 — API / wire format (Task 1)

**Scope:** Read-only. No code changes.

## R1 — Summary

For the captured production JSON, **wire format matches** the static UI’s expectations for the thumb gate. Missing thumbs are **not** explained by field naming or string-vs-number in that reproduction.

## R1 — Production curl (verbatim response body)

```powershell
Set-Location <repo>
'{"session_id":"diagnose-622-001","query":"whats fun for kids this weekend"}' |
  Out-File -Encoding utf8 -NoNewline .\diag.json
curl.exe -sS -X POST "https://havasu-chat-production.up.railway.app/api/chat" `
  -H "Content-Type: application/json" `
  --data-binary "@diag.json"
```

**Full JSON response (verbatim, single line as returned):**

```json
{"response":"Altitude Trampoline Park's open this weekend — 90-minute jump sessions are $19 and they're open 9am–9pm Saturday, 11am–7pm Sunday. If your kids need something more structured, Flips for Fun Gymnastics opens at 3pm weekdays, or check out the dance studios (Arizona Coast Performing Arts, Ballet Havasu, Footlite) for classes.","mode":"ask","sub_intent":"OPEN_ENDED","entity":null,"tier_used":"3","latency_ms":3124,"llm_tokens_used":2962,"chat_log_id":"2fb91062-5283-4473-be29-e3087488ace7"}
```

## R1 — Field notes

| Field | Notes |
|--------|--------|
| **`tier_used`** | Present. JSON **string** `"3"`. |
| **`chat_log_id`** | Present, non-empty, truthy in JS (UUID string). |
| **Prose style** | Long editorial Tier 3 list — not “hours-only Tier 1” style. |

## R1 — Frontend references (`app/static/index.html`)

| Concern | Lines |
|--------|--------|
| `tier_used === "3"` | **748** |
| `chat_log_id` / `data-chat-log-id` | **738–741** |
| `data-tier-used` | **743–746** |
| `attachFeedbackThumbs` call | **749** |
| `attachFeedbackThumbs` definition / early return | **439–440** |

```javascript
if (data.chat_log_id != null && data.chat_log_id !== "") {
  pendingRow.setAttribute("data-chat-log-id", String(data.chat_log_id));
} else {
  pendingRow.removeAttribute("data-chat-log-id");
}
if (data.tier_used != null && data.tier_used !== "") {
  pendingRow.setAttribute("data-tier-used", String(data.tier_used));
} else {
  pendingRow.removeAttribute("data-tier-used");
}
if (data.tier_used === "3" && data.chat_log_id) {
  attachFeedbackThumbs(pendingRow, String(data.chat_log_id));
}
```

## R1 — Cross-reference

- **`tier_used`:** string `"3"` → `data.tier_used === "3"` is **true**.
- **`chat_log_id`:** non-empty string → **truthy** for the gate.

**Fragility (not seen in sample):** JSON **number** `3` would set `data-tier-used` via `String(3)` but fail **`=== "3"`**, so thumbs would not attach.

## R1 — Hypothesis (Task 1)

Gate is **line 748**; for the sampled JSON it **should** pass. If thumbs still missing with equivalent payload, look at **cache**, **JS errors**, **other tabs/builds**, or **different responses** (missing `chat_log_id`, etc.).

---

# Round 2 — HTML parity, handler, schema, harness

**Scope:** Diagnose only — no edits to `app/static/index.html` or production code.

## R2 — Task 1 vs “incognito”

The Task 1 check was **`curl` to `/api/chat`**, not an incognito browser. The body was **long-form Tier 3**, not a short Tier 1 hours blurb.

## R2 — Part A: Served `index.html` vs repo

| Check | Result |
|--------|--------|
| Raw byte size prod vs Windows working tree | Can **differ** (LF on wire vs CRLF locally). |
| `git diff --no-index` (with Git newline handling) | **No diff**. |
| Normalize CRLF→LF on both | **Byte-identical** (e.g. 33012 chars). |

**Conclusion:** Production **`/`** matches **`app/static/index.html` at `HEAD`** in content. Avoid comparing via `git show | Set-Content` alone (BOM/CRLF skew).

## R2 — Part B: `/api/chat` success handler (verbatim)

```javascript
        fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, query: text }),
        })
          .then(function (res) {
            if (!res.ok) throw new Error("Request failed");
            return res.json();
          })
          .then(function (data) {
            pendingBubble.classList.remove("loading");
            pendingBubble.textContent = data.response || "(no response)";
            if (data.chat_log_id != null && data.chat_log_id !== "") {
              pendingRow.setAttribute("data-chat-log-id", String(data.chat_log_id));
            } else {
              pendingRow.removeAttribute("data-chat-log-id");
            }
            if (data.tier_used != null && data.tier_used !== "") {
              pendingRow.setAttribute("data-tier-used", String(data.tier_used));
            } else {
              pendingRow.removeAttribute("data-tier-used");
            }
            if (data.tier_used === "3" && data.chat_log_id) {
              attachFeedbackThumbs(pendingRow, String(data.chat_log_id));
            }
            attachShareButtons();
            scrollToBottom();
            if (data && data.data && data.data.open_calendar && window.havasuChatCalendar) {
              window.havasuChatCalendar.open();
            }
          })
          .catch(function () {
            pendingBubble.classList.remove("loading");
            pendingBubble.textContent = "Hmm, that didn’t go through — check your connection and try again.";
            scrollToBottom();
          })
          .finally(function () {
            setLoading(false);
            input.focus();
          });
```

- **`pendingRow`:** closed over from `var pendingOut = addRow(...); var pendingRow = pendingOut.row;` — **in scope** at thumb attach.
- **`addRow`:** returns **`{ row, bubble }`** (line ~436).
- **`res.json()` failure:** goes to **`.catch`** — user normally sees error bubble, not a full Tier 3 paragraph.

## R2 — Part C: `attachFeedbackThumbs` (full verbatim, `index.html` ~439–554)

Early exit: **`if (!chatLogId || row.querySelector(".msg-feedback")) return;`**

```javascript
      function attachFeedbackThumbs(row, chatLogId) {
        if (!chatLogId || row.querySelector(".msg-feedback")) return;
        var wrap = document.createElement("div");
        wrap.className = "msg-feedback";
        var btnRow = document.createElement("div");
        btnRow.className = "msg-feedback-btns";
        var errEl = document.createElement("span");
        errEl.className = "msg-feedback-err";
        errEl.setAttribute("aria-live", "polite");

        var up = document.createElement("button");
        up.type = "button";
        up.className = "thumb-btn";
        up.setAttribute("aria-label", "Thumbs up");
        up.textContent = "👍";

        var down = document.createElement("button");
        down.type = "button";
        down.className = "thumb-btn";
        down.setAttribute("aria-label", "Thumbs down");
        down.textContent = "👎";

        var inflight = false;
        var lockedSignal = null;

        function clearError() {
          errEl.textContent = "";
          errEl.style.display = "none";
        }

        function showError(msg) {
          errEl.textContent = msg;
          errEl.style.display = "block";
        }

        function setLockedUI(signal) {
          lockedSignal = signal;
          up.classList.remove("thumb-selected", "thumb-dim");
          down.classList.remove("thumb-selected", "thumb-dim");
          if (signal === "positive") {
            up.classList.add("thumb-selected");
            down.classList.add("thumb-dim");
          } else {
            down.classList.add("thumb-selected");
            up.classList.add("thumb-dim");
          }
        }

        function unlockUI() {
          lockedSignal = null;
          up.classList.remove("thumb-selected", "thumb-dim");
          down.classList.remove("thumb-selected", "thumb-dim");
        }

        function postSignal(signal) {
          if (inflight) return;
          clearError();
          inflight = true;
          up.disabled = true;
          down.disabled = true;
          fetch("/api/chat/feedback", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ chat_log_id: chatLogId, signal: signal }),
          })
            .then(function (res) {
              return res.text().then(function (t) {
                var body = {};
                try {
                  body = t ? JSON.parse(t) : {};
                } catch (ignore) {
                  body = {};
                }
                return { ok: res.ok, status: res.status, body: body };
              });
            })
            .then(function (result) {
              inflight = false;
              up.disabled = false;
              down.disabled = false;
              if (result.ok && result.body && result.body.ok === true) {
                setLockedUI(signal);
                return;
              }
              unlockUI();
              var msg = "Couldn't save that — try again";
              if (result.body && result.body.error) msg = String(result.body.error);
              else if (result.body && result.body.message) msg = String(result.body.message);
              showError(msg);
            })
            .catch(function () {
              inflight = false;
              up.disabled = false;
              down.disabled = false;
              unlockUI();
              showError("Couldn't save that — try again");
            });
        }

        up.addEventListener("click", function () {
          if (inflight) return;
          if (lockedSignal === "positive") return;
          postSignal("positive");
        });
        down.addEventListener("click", function () {
          if (inflight) return;
          if (lockedSignal === "negative") return;
          postSignal("negative");
        });

        btnRow.appendChild(up);
        btnRow.appendChild(down);
        wrap.appendChild(btnRow);
        wrap.appendChild(errEl);
        row.appendChild(wrap);
      }
```

## R2 — Part D: Pre-submit throw candidates

If `#log` / `#form` / `#msg` / `#send` were missing, the first IIFE would throw **before** `submit` is registered — user could not chat. If chat works, favor a **throw inside the success `.then`** after `textContent` is set (Console will show it).

## R2 — Part E: Schema (`app/schemas/chat.py`)

```python
class ConciergeChatResponse(BaseModel):
    response: str
    mode: str
    sub_intent: str | None = None
    entity: str | None = None
    tier_used: str
    latency_ms: int
    llm_tokens_used: int | None = None
    chat_log_id: str | None = None
```

**`tier_used: str`** — not `int` / `Any`.

## R2 — Part F: Local harness (not in repo)

- **File:** `%LocalAppData%\Temp\havasu-thumb-test.html` (Windows example: `C:\Users\casey\AppData\Local\Temp\havasu-thumb-test.html`).
- **Do not commit.** Open in a browser; `#status` reports PASS if `.msg-feedback` appears.

## R2 — STOP triggers (checklist)

| Trigger | Result |
|---------|--------|
| Served HTML ≠ `HEAD` | **No** (normalized match). |
| `tier_used` not `str` in schema | **No**. |
| `addRow` returns only bubble | **No**. |

## R2 — Recommended next step

Desktop **DevTools → Console** while sending a Tier 3 query; capture **any red errors** after the reply renders.
