# Phase 6.2.2 — Tier 3 thumbs Round 2 diagnostic report

**Date:** 2026-04-20  
**Scope:** Diagnose only — no edits to `app/static/index.html` or production code.

## Clarification: Task 1 response style (not incognito browser)

The earlier production check used **server-side `curl.exe`**, not an incognito browser session. The returned body was **long-form Tier 3** copy (Altitude Trampoline Park weekend hours/pricing, Flips for Fun, dance studios) — not a short Tier 1 “hours template only” blurb. So the anomaly “Tier 3 prose, no thumbs” remains unexplained by “actually Tier 1.”

---

## Part A — Served `index.html` vs repo

### Commands used

- Downloaded: `curl.exe -sS https://havasu-chat-production.up.railway.app/ -o prod-index.html`
- Compared to: `app/static/index.html` (working tree, which **matches `HEAD`** — `git diff HEAD -- app/static/index.html` is empty).

### Findings

| Check | Result |
|--------|--------|
| Raw byte size | **Differs** (e.g. prod ~33067 bytes vs local ~34096 bytes on Windows) — consistent with **LF on the wire vs CRLF in the git working tree**, not a semantic HTML drift. |
| `git diff --no-index prod-index.html app/static/index.html` | **No diff** (Git newline normalization). |
| Normalized comparison | After collapsing CRLF→LF on both files, **lengths match (33012) and content is byte-identical** (`NORMALIZED: IDENTICAL`). |

**Conclusion:** Production is serving the **same HTML content as repo `HEAD`** for `app/static/index.html` (aside from line-ending storage on the dev machine). This is **not** a “stale deploy / wrong index on Railway” class bug.

**Note:** `git show HEAD:... | Set-Content` in PowerShell can change bytes (BOM/CRLF); comparing **curl output vs `app/static/index.html`** with newline normalization is the reliable check.

---

## Part B — `/api/chat` success handler (verbatim excerpt)

Source: `app/static/index.html` — `fetch("/api/chat", …)` chain.

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

### Error paths

- **`.then(res => …)`:** Throws if `!res.ok` → skipped second `.then`, handled by **`.catch`** (generic error bubble). No silent swallow inside success path.
- **`res.json()`:** If it rejects (invalid JSON, etc.), the **second `.then` never runs** → **`.catch`** runs. User would see the connection-style message, not a normal Tier 3 paragraph — so this path **does not** match “full Tier 3 text, no thumbs” unless something else is wrong (e.g. partial mock).
- **`.catch`:** Replaces bubble text; does **not** rethrow. That is intentional UX, not a hidden failure after thumbs.

### `pendingRow` scope

`pendingRow` is declared in the **same** `submit` handler as `fetch`, **before** `setLoading` / `fetch`:

```javascript
        var pendingOut = addRow("bot", "…", "loading");
        var pendingBubble = pendingOut.bubble;
        var pendingRow = pendingOut.row;
```

It is **closed over** by the `.then(function (data) { … })` callback — **in scope** at `attachFeedbackThumbs(pendingRow, …)`.

### `addRow` return value

`addRow` **always** returns `{ row: row, bubble: bubble }` (see Part C / repo line 436). The pending assistant row uses **`pendingOut.row`** — not a bubble-only return.

---

## Part C — `attachFeedbackThumbs` (full function, verbatim)

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

### Early returns

- **Line 440:** `if (!chatLogId || row.querySelector(".msg-feedback")) return;`  
  - Skips attach if `chatLogId` is falsy **or** a `.msg-feedback` node already exists under `row`.

### “Silent” failure modes

- If **`row` were null/undefined**, `row.querySelector` would **throw** before return — not silent; would break the `.then` unless caught (it is not wrapped in try/catch inside the `.then`). So a bad `row` would likely surface as a **console error** and abort the rest of that handler (including `attachShareButtons` / `scrollToBottom`).
- If **`row` is valid** and `chatLogId` truthy and no pre-existing `.msg-feedback`, the function **appends** the thumb strip — no further silent exit.

---

## Part D — Code that runs before the submit handler (throw candidates)

The chat UI lives in an IIFE starting ~line 414. Before `form.addEventListener("submit", …)` (~714), this runs synchronously:

| Area | Risk |
|------|------|
| `getElementById("log" \| "form" \| "msg" \| "send")` | If IDs were missing, **`null` dereference** on later use (e.g. `addRow` → `log.appendChild`) would throw **before** the listener is registered — user could not send at all. |
| `showWelcome` / `showWelcomeReturning` | Uses `addRow`, `log`, `form`, `input` — same as above. |
| `setTimeout(..., 150)` | Only schedules work; inner failures run later. |
| `input.focus()` (after listener, ~768) | If `#msg` missing, could throw **after** listener is registered. |
| Second IIFE (calendar, ~774+) | **Separate** IIFE; failure there does **not** prevent the first IIFE from registering `submit` unless the first IIFE already threw. |

**Practical note:** If the user can send messages and see assistant replies, the **submit listener is almost certainly registered** and `log` / `form` / `input` / `send` are present. A **runtime error inside** the success `.then` (after text is set) remains the best single-threaded explanation for “bubble updated, thumbs skipped” — e.g. **`attachShareButtons`** or **`scrollToBottom`** throwing, or **`attachFeedbackThumbs`** throwing on an unexpected `row` type (unlikely if `addRow` built it).

---

## Part E — `ConciergeChatResponse.tier_used` (schema)

From `app/schemas/chat.py`:

```python
class ConciergeChatResponse(BaseModel):
    """Unified router response (``app.chat.unified_router.route``)."""

    response: str
    mode: str
    sub_intent: str | None = None
    entity: str | None = None
    tier_used: str
    latency_ms: int
    llm_tokens_used: int | None = None
    chat_log_id: str | None = None
```

- **`tier_used` is typed as `str`**, not `int` or `Any`.
- Serialization for JSON should therefore emit a **JSON string** for `tier_used` under normal FastAPI/Pydantic behavior, matching `data.tier_used === "3"` in the browser.

---

## Part F — Minimal harness (not committed)

- **Path:** `%LocalAppData%\Temp\havasu-thumb-test.html` (full path on this machine: `C:\Users\casey\AppData\Local\Temp\havasu-thumb-test.html`).
- **Purpose:** Copies **thumb-related CSS**, **`addRow`**, **`attachFeedbackThumbs`** (trimmed: no network on thumb click), and the **same gate** as production (`tier_used === "3"` && `chat_log_id`), then sets `#status` to PASS/FAIL based on `.msg-feedback` under the bot row.
- **Not in git** — do not commit.

### Automated browser execution

This environment did **not** open a GUI browser or run Playwright. **Expected** outcome when a human opens the file: **PASS** (thumbs strip present) — the harness logic mirrors the production gate and `attachFeedbackThumbs` structure.

**Interpretation:**

- If **PASS** in a real browser but production fails with the same JSON shape → suspect **full-page integration** (error later in the same `.then`, extension, or something mutating the DOM).
- If **FAIL** in browser → inspect harness vs production differences (here they are intentionally minimal).

---

## STOP trigger checklist (from prompt)

| Trigger | Outcome |
|---------|---------|
| Served HTML diverges from repo `HEAD` | **No** — normalized content matches. |
| `tier_used` not typed `str` | **No** — it is `str`. |
| `addRow` returns only bubble | **No** — returns `{ row, bubble }`. |
| Harness fails | **Not executed in browser here** — harness file supplied for manual check. |

---

## Recommended next step (owner / desktop)

Open DevTools **Console** on a Tier 3 send and note **any uncaught exception** after the response arrives. That directly tests hypothesis **(a)** — a throw in the success handler after `textContent` is set but before or after thumb attach — without further code changes.
