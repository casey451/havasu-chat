# Frontend Markdown rendering — inspection — 2026-04-19

**Scope:** Read-only review of how bot `response` text is shown at `https://havasu-chat-production.up.railway.app/` (served from `app/static/index.html`). No prompt changes, no extra Tier 3 calls.

---

## 1. Where chat is rendered

- **Single asset:** `app/static/index.html` — all chat UI logic is **inline** in one `<script>` block. There are **no** separate JS files under `app/static/` for message rendering.

---

## 2. Pipeline for bot responses

1. User submits the form; the client `POST`s to **`/chat`** with JSON `{ session_id, message }`.
2. On success, the handler sets the assistant text from **`data.response`** onto the pending bubble.

**Mechanism:** DOM **`textContent`**, not `innerHTML` and not a Markdown library.

`addRow` (used for user lines, welcome text, and bot lines) assigns:

```javascript
bubble.textContent = text;
```

After fetch, the bot reply is applied as:

```javascript
pending.textContent = data.response || "(no response)";
```

**Implication:** The string is shown **literally**. Markdown syntax (e.g. `**bold**`, `*italic*`) is **not** interpreted; users see the asterisks unless the model avoids them.

There is no `marked`, `markdown-it`, or similar in this page.

---

## 3. Calendar overlay (separate path)

The calendar builds **structured** HTML for day-detail event rows (`innerHTML`) with a minimal escape for `<` in titles/locations. That is **not** the main chat transcript.

When an event is pushed into the chat log (`pushEventToChat`), the bubble again uses **`textContent`**.

---

## 4. Conclusion vs product need

| Question | Answer |
|----------|--------|
| Does the web frontend **render** Markdown in bot responses? | **No.** |
| What do users see if the model emits `**` / `*`? | **Raw characters** (asterisks, etc.). |

**Recommended direction (for sign-off alignment):** Either **tune the system prompt** (or post-process) so replies are **plain text** without Markdown, **or** add a client-side Markdown renderer and switch to safe HTML if emphasis in the UI is desired later.

---

## 5. Code references

`addRow` uses `textContent` for every bubble (including bot):

```364:374:app/static/index.html
      function addRow(role, text, extraClass) {
        var row = document.createElement("div");
        row.className = "row " + (role === "user" ? "user" : "bot");
        var bubble = document.createElement("div");
        bubble.className = "bubble" + (extraClass ? " " + extraClass : "");
        bubble.textContent = text;
        row.appendChild(bubble);
        log.appendChild(row);
        scrollToBottom();
        return bubble;
      }
```

Chat `POST /chat` success handler assigns the API `response` the same way:

```553:559:app/static/index.html
          .then(function (data) {
            pending.textContent = data.response || "(no response)";
            attachShareButtons();
            scrollToBottom();
            if (data && data.data && data.data.open_calendar && window.havasuChatCalendar) {
              window.havasuChatCalendar.open();
            }
          })
```
