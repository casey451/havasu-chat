# Phase 8.0.6 — Operator UX polish (read-first report)

**Date:** 2026-04-22  
**Scope:** Issue A (`POST /api/chat` validation / 422 UX), Issue B (admin HTML nav inconsistency). **Read-only; no code edits, no commit.**

---

## Pre-flight

| Check | Result |
|--------|--------|
| `git log --oneline -1` | `dc4ac14` Phase 8.0.5 (matches spec) |
| `git status` | Clean; only untracked `docs/phase-9-scoping-notes-2026-04-22.md` before this file was added |
| `pytest -q` | **754 passed**, 3 subtests passed |

---

## 1. Issue A — Where 422 is handled (server)

### 1.1 `POST /api/chat` endpoint

- **File:** `app/api/routes/chat.py`  
- **Handler:** `post_concierge_chat` — parameter `payload: ConciergeChatRequest` (`app/schemas/chat.py`).  
- **Behavior:** FastAPI validates the body **before** the route body runs. Missing/invalid fields raise **`RequestValidationError`**.

### 1.2 Pydantic model

- **File:** `app/schemas/chat.py`  
- **`ConciergeChatRequest`:** `query: str = Field(min_length=1)`, optional `session_id: str | None = None`.  
- Missing **`query`** or **`query: ""`** triggers validation errors.

### 1.3 Global exception handler (not default FastAPI 422 body)

- **File:** `app/main.py` **lines 300–305**

```python
@app.exception_handler(RequestValidationError)
async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"message": friendly_errors(exc.errors())},
    )
```

- **Effect:** Clients receive **`{"message": "<single string>"}`**, not the default FastAPI **`{"detail":[...]}`** array. **`Content-Type: application/json`**.

### 1.4 `friendly_errors` implementation

- **File:** `app/core/event_quality.py` **lines 218–228**  
- **Logic:** Walks Pydantic error dicts; returns inner **`ValueError`** strings, strips **`Value error, `** prefixes, else falls through to a **generic default:**  
  **`"Some event details are not valid. Please check and try again."`**  
- **Issue:** That default string is **event-create–centric**. For **`ConciergeChatRequest`** validation (missing/empty **`query`**), none of the specialized branches match, so **chat validation 422s reuse the event copy** — misleading for API consumers and unrelated to the 8.0.1 triage assumption of a raw Pydantic blob (the app **already wraps** validation).

---

## 2. Issue A — Reproduced 422 (same spirit as 8.0.1 triage)

| Request body | HTTP | Response body | `Content-Type` |
|----------------|------|-----------------|----------------|
| `{"session_id": "x"}` (missing `query`) | **422** | `{"message":"Some event details are not valid. Please check and try again."}` | `application/json` |
| `{"query":""}` (empty `query`, violates `min_length=1`) | **422** | **Same** `message` string as above | `application/json` |

---

## 3. Issue A — Frontend (`app/static/index.html`)

### 3.1 Main concierge `POST /api/chat` (lines ~767–807)

- Uses **`fetch("/api/chat", …)`** then **`.then(function (res) { if (!res.ok) throw new Error("Request failed"); return res.json(); })`**.  
- **Any non-2xx (including 422)** throws before `res.json()` is used for assistant text.  
- **`.catch`** sets the pending bubble to:  
  **`"Hmm, that didn’t go through — check your connection and try again."`**  
- **The 422 JSON body is never read** for this path. Users **do not** see the generic `"message"` string (wrong “event details” copy) in the main chat UI today.

### 3.2 Feedback thumbs `POST /api/chat/feedback` (lines ~499–527)

- Parses JSON on error; uses **`result.body.message`** or **`result.body.error`** for inline error text — **appropriate** for validation-shaped responses.

### 3.3 Conclusion for “opaque blob” hypothesis

- **Server:** Not a raw Pydantic **detail** blob; it is a **single-field JSON** with a **misleading message string** for chat.  
- **In-browser main chat:** Problem is **not** “validation blob in the bubble” — it is **over-broad copy** on the server for **API/direct clients**, plus **frontend** showing a **connection** heuristic for **all** `!res.ok` errors (including validation), which can mislead on true validation failures.

---

## 4. Issue A — Proposed fix shape (implement not in this pass)

| Option | Fit |
|--------|-----|
| **A. Extend `friendly_errors`** | Map `loc` containing **`query`** / **`ConciergeChatRequest`** (or detect chat-only error types) to a **short chat-specific sentence**; keep event default for event routes. **Small**, localized; **no** new global behavior beyond clearer copy. |
| **B. Split helpers** | e.g. `friendly_chat_request_errors` vs `friendly_errors` — **clearer** ownership, slightly more code. |
| **C. Per-route handler** | Duplicate or override validation handling for `/api/chat` only — usually **worse** than fixing **`friendly_errors`** or a small router-specific wrapper. |
| **D. Frontend-only** | Parse 422 JSON and show `message` — would surface **current wrong** “event details” text until server copy is fixed; **pair with A/B** if done. |
| **E. Do nothing** | **Not** ideal: **curl/API** clients still get wrong message; in-app copy still blames “connection” for validation errors. |

**Recommendation:** **A or B** (server-side accurate message for chat validation). **Optional:** tighten **`index.html`** to branch on **`res.status === 422`** and show a **neutral** line (and optionally `message` once it is chat-correct).  

**Owner question (voice):** If chat validation gets a dedicated user-facing string, should it align with **§3.11** Tier-3 graceful-error tone (“Something went sideways…”) vs a shorter **form-style** line? Read-first does not decide.

**Tests:** `tests/test_api_chat.py::test_post_api_chat_validation_empty_query` asserts **`status_code == 422` only** — **no** assertion on body text today; changing **`message`** is **unlikely** to break tests unless new assertions pin copy.

**STOP triggers:** None — handler is already centralized; extending **`friendly_errors`** (or a chat-specific path) does **not** require changing FastAPI defaults app-wide beyond the existing single handler.

---

## 5. Issue B — Admin nav rendering (HTML modules)

Inline HTML in Python (**handoff §2.8** — no Jinja2). Each module embeds its own **`<nav class="nav">`** block (or uses **`_nav_shell`** in contributions).

### 5.1 `app/admin/contributions_html.py`

- **`_nav_shell`** (approx. lines **154–214**): wraps pages with:

```html
<nav class="nav">
  <a href="/admin?tab=queue">Admin home</a>
  <a href="/admin/contributions">Contributions</a>
</nav>
```

- **Links present:** **Admin home**, **Contributions** only — **no** Mentioned entities, Categories, Analytics, Feedback.

### 5.2 `app/admin/mentions_html.py`

- **List shell** (approx. lines **134–138**):

```html
<nav class="nav">
  <a href="/admin?tab=queue">Admin home</a>
  <a href="/admin/contributions">Contributions</a>
  <a href="/admin/mentioned-entities">Mentioned entities</a>
</nav>
```

- **Missing vs categories page:** **Categories** link.

### 5.3 `app/admin/categories_html.py`

- **Nav** (approx. lines **53–57**): **Admin home**, **Contributions**, **Mentioned entities**, **Categories** — **full cross-link set** among those four.

### 5.4 `app/admin/feedback_html.py`

- **Nav** (approx. lines **97–103**): **Admin home**, **Analytics**, **Feedback**, **Contributions**, **Mentioned entities**, **Categories** — **richest** set (adds **`/admin/analytics`** and **`/admin/feedback`**).

### 5.5 Confirmation vs 8.0.1 triage

Triage observation **holds:** nav **differs by entry page**; **contributions** is minimal; **mentions** adds self; **categories** adds Categories; **feedback** further adds Analytics + Feedback.

---

## 6. Issue B — Other admin surfaces (`app/admin/` + `router.py`)

| Module / area | Role | Nav pattern |
|-----------------|------|-------------|
| **`app/admin/router.py`** | Main **`/admin`** queue, programs, login, analytics routes | Uses **`<nav class="tabs">`** with **Analytics** / **Feedback** on major queue views — **different component** from **`class="nav"`** on Phase 5 HTML modules |
| **`app/admin/auth.py`** | Cookie helpers | No list HTML |
| **`contributions_html` / `mentions_html` / `categories_html` / `feedback_html`** | Scoped HTML UIs | **`nav.nav`** as above |

**No additional `*_html.py` files** under `app/admin/` beyond the four above. **Issue B scope** for “align nav across HTML admin pages” = **those four files** + awareness that **main `/admin`** uses a **separate tabs nav** (design consistency is a **broader** polish item if desired later).

---

## 7. Issue B — Proposed fix shape (implement not in this pass)

| Option | §2.8 | Effort |
|--------|------|--------|
| **1. Shared Python helper** | **Compliant** — returns an HTML **string** fragment, e.g. `admin_nav_links(include_analytics=False)`, imported by each `*_html.py` (and optionally **`_nav_shell`**). **~20–40 lines** helper + **2–4 line** replacement per file. |
| **2. Copy-paste identical `<nav>` block** | Compliant | **~6 lines × 3 edits** (bring contributions + mentions up to categories; optionally align feedback separately). **Lowest risk**, highest drift if pages diverge again. |
| **3. Minimum viable** | Compliant | Add **only** the missing links to contributions + mentions to match categories (feedback already superset). **Smallest diff**. |

**Recommendation:** **1 (shared helper)** for maintainability, **or 3** if the team wants the smallest possible 8.0.6-implement diff. **Do not introduce Jinja2** unless owner explicitly overrides §2.8.

**Tests:** Grep found **no** assertions on **`nav`** HTML strings in `tests/` for these pages; **`test_admin_contributions_html.py`** hits URLs and status codes, not nav markup — **low** risk of test breakage from nav edits.

---

## 8. Item 7 — Test grep (`tests/`)

### 8.1 `/api/chat` and 422

| File | Line | What is asserted |
|------|------|------------------|
| `tests/test_api_chat.py` | 69 | **`r.status_code == 422`** for empty `query` — **no** body shape |
| `tests/test_api_chat_onboarding.py` | 55 | **422** on bad onboarding payload |
| `tests/test_feedback_endpoint.py` | 99–115 | **422** on invalid feedback — **no** reliance on default FastAPI **`detail`** |
| Other **422** hits | various | Event/program/contributions API — unrelated to chat nav |

**None** assert the literal **`"Some event details are not valid"`** string for `/api/chat`.

### 8.2 Admin nav HTML

- **No** matches for **`nav class="nav"`** or **“Admin home”** in **`tests/`** as content assertions.  
- Admin HTML tests use **routes and redirects**, not nav copy.

---

## 9. STOP triggers (this read-first)

- **None** for prod access / schema / Jinja creep.  
- **Issue A:** Default 422 body is **already wrapped**; remaining work is **copy correctness** (+ optional frontend status branch), not replacing FastAPI’s default **`detail`** globally.  
- **Issue B:** Inconsistency is **duplicated inline `<nav>`** (and one richer page), not a hidden shared template — fix is **small** if §2.8 is respected.

---

## 10. Executive summary (for 8.0.6-implement approval)

1. **Issue A:** Global **`RequestValidationError`** handler already returns **`{"message": …}`**; chat validation falls through to the **event-form default string**, which is **wrong for `/api/chat`**. The **static UI** does **not** display that string for the main send path; it shows a **generic connection** message on any **`!res.ok`**. **Recommend** server-side **chat-aware** messages (and optionally **422-specific** UI copy).  
2. **Issue B:** **Four** HTML admin modules; **nav link sets differ** as triage described; **`feedback_html`** is the superset; **contributions** / **mentions** are missing links. **Recommend** shared **string helper** or **minimal link additions**, **no Jinja2**.

**Report path (uncommitted):** `docs/phase-8-0-6-read-first-report.md`
