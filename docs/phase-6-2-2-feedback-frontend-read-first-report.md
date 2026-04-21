# Phase 6.2.2 — Feedback frontend (read-first report)

**Date:** 2026-04-21  
**Scope:** Read-only inspection of `app/static/index.html` before implementation. **Paused** until owner says `proceed`.

**References:** Handoff §5 Phase 6.2; backend `POST /api/chat/feedback` (Phase 6.2.1). This document captures items **1–3** from the Phase 6.2.2 prompt (read-first).

---

## 1. `app/static/index.html` structure

### How chat messages are rendered

- **`#log`** (`<div id="log" role="log" …>`) is the scroll container; rows use **`display: flex`**, **`flex-direction: column`**, **`gap: 12px`** in the surrounding layout.
- **`addRow(role, text, extraClass)`** (main chat IIFE) builds each line:

```376:386:app/static/index.html
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

- Structure: **`div.row`** (`row user` or `row bot`) → single child **`div.bubble`** (optional **`loading`** for pending “…”).
- Welcome copy uses **`addRow("bot", …)`** plus a **`div.chips-wrap`** appended to `#log` (not inside `.row`).

**Per-message anchor:** The logical unit is **`.row.bot`** with one **`.bubble`**. **`addRow` returns only the `bubble`**, not the row. Thumb UI would attach via **`bubble.parentElement`** (the row) or by extending **`addRow`** to return row + bubble.

### After `fetch("/api/chat", …)`

```556:571:app/static/index.html
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
            pending.textContent = data.response || "(no response)";
            attachShareButtons();
            scrollToBottom();
            if (data && data.data && data.data.open_calendar && window.havasuChatCalendar) {
              window.havasuChatCalendar.open();
            }
          })
```

- **Used:** `data.response`, optional `data.data.open_calendar`.
- **`chat_log_id`:** not read — **discarded** client-side.
- **`tier_used`:** not read — **discarded**.

### Existing feedback / thumb UI

Grep for `thumb`, `feedback`, `chat_log`, `tier_used` in `index.html`: **no matches**. No prior scaffold.

---

## 2. Styling conventions

- **CSS:** Single **`<style>`** block in the same HTML file (no separate chat CSS file).
- **JS:** **Plain DOM** + **IIFE**; no framework; **`addRow`** uses **`textContent`** only.
- **Interactive patterns:** Filled blue **`#send`**, pill **`.chip`** (min-height 44px), bordered **`.calendar-btn`** with **emoji 📅**, **`.event-share-btn`** pill. Emoji already appears in chrome; assistant bubbles are text-only via **`textContent`** on the concierge path.

---

## 3. Visual check

No live browser was opened from the automation environment. From CSS:

- Assistant: **light grey** bubble (`#e9ecef`), dark text, **large radius**, **max-width 85%**, left-aligned.
- **12px** gap between `#log` children.
- Room for thumbs: plausible **below** `.bubble` inside **`.row.bot`** if that row uses **column** flex and align-start (small layout tweak).

---

## STOP / implementation notes

- Re-verify **`chat_log_id`** still present on **`POST /api/chat`** JSON in production before ship if desired (repo + OpenAPI still include it).
- Compare **`tier_used`** with **`=== "3"`** (string), not numeric `3`, unless wire format changes.

---

*Implementation + `docs/phase-6-2-2-feedback-frontend-report.md` + commit deferred until owner sends **`proceed`**.*
