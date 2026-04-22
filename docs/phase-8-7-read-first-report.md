# Phase 8.7 — Privacy review (read-first report)

**Date:** 2026-04-22  
**HEAD:** `6a57657` (Phase 8.3)  
**Scope:** Inspection only — no commits, no edits under `app/`, `tests/`, `alembic/`, `scripts/`, `prompts/`.

---

## Pre-flight

| Check | Result |
|--------|--------|
| `git log --oneline -5` / HEAD | **PASS** — HEAD is `6a57657` |
| `git status` | **PASS** — only `?? docs/phase-9-scoping-notes-2026-04-22.md` before this report; after saving this file, expect `?? docs/phase-8-7-read-first-report.md` as well |
| `.\.venv\Scripts\python.exe -m pytest -q` | **PASS** — **772 passed**, 3 subtests passed |
| Production DB (read-only) | **PASS** — `railway run` with venv `python.exe` reached Postgres; aggregates and row-shape samples below |

---

## 1. Logging and persistence write paths

### 1.1 PostgreSQL — `chat_logs`

| Location | Function / caller | Destination | What is written |
|----------|-------------------|---------------|-------------------|
| `app/db/chat_logging.py` L12–62 | `log_unified_route` | `chat_logs` | One row per unified concierge turn (`POST /api/chat` → `unified_router.route`). See §2.1. |
| `app/db/chat_logging.py` L65–82 | `log_chat_turn` | `chat_logs` | Track A `POST /chat`: user line then assistant line; `tier_used='track_a'`. Full `message` text for both roles. |
| `app/api/routes/chat.py` L104–110 | `post_chat_feedback` | `chat_logs.feedback_signal` | Updates existing row by `chat_log_id`; no new row. |

### 1.2 PostgreSQL — `contributions`

| Location | Destination | What is written |
|----------|-------------|-----------------|
| `app/db/contribution_store.py` `create_contribution` L54–79 | `contributions` | Entity submission fields, optional **plaintext** `submitter_email`, **`submitter_ip_hash`** (SHA-256 of raw IP from request), URL metadata, optional `google_place_id` / `google_enriched_data`, `llm_source_chat_log_id`, etc. |
| `app/api/routes/contribute.py` | Inserts via `create_contribution` | Same; IP → `_ip_hash` (SHA-256 hex) L42–44, L282. |
| `app/contrib/enrichment.py` | `contributions` | Updates URL fetch + Places JSON columns (`google_enriched_data`, etc.). |
| `app/db/contribution_store.py` (review helpers) | `contributions` | Status / review fields on approve-reject flows (see admin routes). |

### 1.3 PostgreSQL — `llm_mentioned_entities`

| Location | Destination | What is written |
|----------|-------------|-----------------|
| `app/db/llm_mention_store.py` `create_mention` L19–38 | `llm_mentioned_entities` | `chat_log_id`, `mentioned_name` (≤300), `context_snippet` (≤500), default `status`, timestamps. |
| `app/contrib/mention_scanner.py` `scan_and_save_mentions` L103–117 | (calls `create_mention`) | Background task after Tier 3 unified turn; scans **assistant** response text for title-case phrases. |

### 1.4 PostgreSQL — catalog entities (user-derived / operator)

These are not “chat logs” but persist **user- or operator-supplied** text:

| Location | Tables | Notes |
|----------|--------|------|
| `app/contrib/approval_service.py` | `providers`, `programs`, `events` | Promotion from approved contributions; copies structured fields into catalog. |
| `app/chat/router.py` (event suggest / community flows) | `events` | `db.add(event)` + commit in suggest paths (see grep `db.commit` ~L861+). |
| `app/main.py` | `events` | Public event submission path (`db.add` ~L321). |
| `app/programs/router.py` | `programs` | Community program submissions. |
| `app/admin/router.py` | various | Admin edits/commits (programs, contributions, mentions, etc.). |

### 1.5 `field_history`

- **Runtime app:** No grep hits for inserting `FieldHistory` outside **`app/db/seed_field_history_baseline.py`** (operator/seed script). **No active app request path** found that appends correction rows in this pass.
- **Model:** `app/db/models.py` `FieldHistory` exists for Phase 5 tracking; operational writes are script-driven unless a path was missed.

### 1.6 Files on disk (application)

| Location | Destination | Content |
|----------|-------------|---------|
| `app/core/search_log.py` L10–16, L28–59 | **`search_debug.log`** at repo root (path resolved from `app/core/`) | `logging.FileHandler`; **`RAW INPUT`** = full user message, slots JSON, DB params including `query_message`, candidate titles/scores. |
| `.gitignore` | — | `search_debug.log` is ignored for git, but the file is still created on any host that runs the Track A search path. |

**Callers:** `app/chat/router.py` `_run_search_core` L351–352 calls `search_log.log_query` / `log_db_params`; `app/core/search.py` L625–627 calls `log_candidates`. **Unified router does not import `search_log`.**

### 1.7 Stdout / platform logs (Railway)

| Location | Destination | Content |
|----------|-------------|---------|
| `app/core/search.py` L554–563 | **stdout** | `[search_diag]` prints `flags_text` (query-derived), embedding flags, candidate event **titles**. |
| Widespread `logging.*` | stderr / process log stream | Mostly errors + operational messages; **exception** traces may include framework context. **`hint_extractor`** can log **first 200 chars of model JSON** (may echo user-age/location hints). See §2.3. |

### 1.8 In-process session store (not Postgres)

| Location | Store | Content |
|----------|-------|---------|
| `app/core/session.py` | Global `sessions` dict | Search slots, **`recent_utterances`**, `query_signature` prefixes, onboarding hints, flow state. **Ephemeral** per deploy; not replicated SQL. |

### 1.9 Scripts (operator / dev; not production request path)

| Script | Writes |
|--------|--------|
| `scripts/build_complete_handoff.py` | Markdown file |
| `scripts/extract_tier3_queries.py` | Text file of queries |
| `scripts/run_voice_spotcheck.py`, `scripts/run_voice_audit.py` | JSON / text reports |
| `scripts/diagnose_search.py` | Output file + reads `search_debug.log` |
| `app/db/seed*.py`, `backfill*.py`, `populate*.py` | DB + stdout | One-off / CI seeding |

`scripts/analyze_chat_costs.py` — **read-only** on `chat_logs`; stdout aggregates only (per file docstring).

### 1.10 Sentry

| Location | Behavior |
|----------|----------|
| `app/main.py` L41–60 `_init_sentry` | If `SENTRY_DSN` set: `sentry_sdk.init` with `FastApiIntegration`, `StarletteIntegration`, `traces_sample_rate=0.1`. **No custom PII scrubbing** in-repo. |

---

## 2. Data classification by destination

### 2.1 Table `chat_logs` (model `app/db/models.py` L134–154)

| Column | Classification | Notes |
|--------|------------------|-------|
| `id` | Identifier | UUID string PK |
| `session_id` | Identifier | Client-supplied string truncated to 128 (`ChatRequest.session_id` required; `ConciergeChatRequest.session_id` optional → server `uuid4().hex[:24]` if absent). **Not** cryptographically tied to auth; client could choose guessable values (edge case). |
| `message` | **Content** | **Plaintext.** Unified path: **assistant reply** (up to 48k). Track A: **user and assistant** full text. |
| `role` | Metadata | `user` / `assistant` |
| `intent` | Metadata | Legacy intent / sub_intent echo (unified) |
| `created_at` | Metadata | Server timestamp |
| `query_text_hashed` | Identifier (hash of content) | **SHA-256 hex** of **raw** query (64 chars observed in prod); code stores `[:128]` (`unified_router` L237, `chat_logging` L41). **Null** on Track A rows. |
| `normalized_query` | **Content / potentially sensitive** | **Plaintext** normalized query (up to 48k), unified rows only. **Not hashed.** |
| `mode`, `sub_intent` | Metadata | |
| `entity_matched` | Metadata / content | Catalog entity name if matched |
| `tier_used` | Metadata | `1`/`2`/`3`/`chat`/… or **`track_a`** or **NULL** (~2% legacy per 8.0.5 notes) |
| `latency_ms` | Metadata | |
| `llm_tokens_used`, `llm_input_tokens`, `llm_output_tokens` | Metadata | |
| `feedback_signal` | Metadata | Thumbs signal from feedback API |

**Production sample (read-only, 2026-04-22):** Recent rows are overwhelmingly `role='assistant'` with `message` = concierge prose; `query_text_hashed` **present** (len 64); `normalized_query` **plaintext** snippets (e.g. questions about kids, hours). `tier_used` counts include `(null, 6)` legacy rows — **not PII**; analytics completeness only.

### 2.2 Table `contributions`

| Column | Classification |
|--------|----------------|
| `submitter_email` | **Potentially sensitive** (PII) — optional, plaintext |
| `submitter_ip_hash` | Identifier (hash of PII) — **not** raw IP in DB |
| `submission_name`, `submission_notes`, URLs | Content / potentially sensitive |
| `google_enriched_data` | Content + metadata (Places payload / errors) |
| `llm_source_chat_log_id` | Identifier — links to `chat_logs` |

### 2.3 Table `llm_mentioned_entities`

| Column | Classification |
|--------|----------------|
| `chat_log_id` | Identifier |
| `mentioned_name` | Content (often business-ish; could be person names) |
| `context_snippet` | **Content / potentially sensitive** — excerpt from **assistant** text |
| `status`, `detected_at`, review fields | Metadata |

### 2.4 `search_debug.log` + stdout `[search_diag]`

| Field | Classification |
|-------|----------------|
| Raw user message, slots, `query_message`, synonyms | **Content / potentially sensitive** |
| Event titles | Content (catalog + user context) |

### 2.5 Python `logging` — user-adjacent

| File | Pattern | Risk |
|------|---------|------|
| `app/chat/hint_extractor.py` L96 | `logging.info(..., raw[:200])` on validation failure | **Up to 200 chars of OpenAI JSON** — can mirror extracted hints sourced from user text. |
| Other `logging.exception` | Stack traces | May include URL paths / framework data; default Sentry may attach request context (see §4). |

---

## 3. Retention posture

| Destination | TTL / cleanup | Finding |
|-------------|---------------|---------|
| **`chat_logs`** | No app-level prune, no Alembic migration matched (`delete`/`prune`/`retention` grep in `alembic/versions` **empty**) | **Indefinite retention** in Postgres unless operator runs external maintenance. |
| **`contributions`**, **`llm_mentioned_entities`**, catalog tables | Same | **Indefinite** unless manual SQL / future policy. |
| **`search_debug.log`** | None in code | Grows with Track A search volume on each container filesystem; **gitignored**, not shipped in repo. |
| **Railway logs** | Platform policy (not defined in repo) | Stdout `[search_diag]` and uvicorn lines follow Railway retention. |
| **Sentry** | Provider policy | Not codified in-repo. |
| **In-memory `sessions`** | `IDLE_SESSION_RESET_SEC` / flow TTLs in `session.py` | Ephemeral; not durable audit. |
| **`events` pending_review** | `run_expired_review_cleanup` in `main.py` L66–80 | Marks **expired pending_review events** `deleted` — **events only**, not chat_logs. |

**Honest summary:** Durable chat and contribution data **accumulates without automated deletion** in this codebase.

---

## 4. External data flows

### 4.1 Anthropic (Messages API)

| Use | Payload includes | Identifiable? |
|-----|------------------|---------------|
| **Tier 3** `tier3_handler.answer_with_tier3` | System prompt (cached), **`User query:\n{query}`**, classifier line, optional onboarding bias line, optional “Local voice” blurbs, **`build_context_for_tier3`** catalog block (provider/program/event text) | **Yes** — full **verbatim user query** |
| **Tier 2 parser** `tier2_parser.parse` | Parser system prompt + **`User query:\n{query}`** | **Yes** |
| **Tier 2 formatter** `tier2_formatter.format` | Formatter prompt + **`Query: {query}`** + JSON **catalog rows** | **Yes** |

**Retention:** Anthropic’s enterprise/data policies are **not** duplicated in this repo — **documentation gap** for `docs/privacy.md`.

### 4.2 OpenAI

| Use | Payload | Notes |
|-----|---------|-------|
| **Hint extraction** `hint_extractor.extract_hints` | `gpt-4.1-mini` (or `OPENAI_MODEL`) with **`User message:\n{q}`** | Full user message for hint JSON |
| **Search embeddings** `search.generate_query_embedding_with_source` | `text-embedding-3-small` with **`input=text.strip()`** (`query_message` / flags text in search pipeline) | Full query string when API key present |

### 4.3 Google Places (HTTP)

| Use | Payload | Notes |
|-----|---------|-------|
| `places_client.lookup_provider` | **POST** `places.googleapis.com/v1/places:searchText` with `textQuery` = **`{submission_name} Lake Havasu City, AZ`** (default context) | Business discovery for contributions; response stored in `google_enriched_data` |

### 4.4 Sentry

- Initialized from **`SENTRY_DSN`** with default FastAPI/Starlette integrations.
- **Default behavior** can attach **request data** and **exception context** to events. **No in-repo scrubber** for query bodies on `/api/chat` or `/chat`.
- **Risk:** If an exception occurs with request body in frame or SDK breadcrumbs, **user query could appear in Sentry**. Treat as **HIGH visibility** for privacy page + optional hardening in a later phase.

### 4.5 Railway / stdout

- **`[search_diag]`** prints query-derived strings → **Railway log retention** applies.
- **`search_debug.log`** on container disk — same deployment boundary; not user-downloadable from app.

---

## 5. Gap analysis (vs Phase 8.7 intent + common practice)

**Normative text from owner prompt (Phase 8.7):** *Confirm what's logged … Query text is hashed in `chat_logs` — do not log PII plaintext.*

| ID | Finding | Severity |
|----|-----------|----------|
| G1 | **`query_text_hashed`** stores **SHA-256 of raw query** (confirmed in code **and** prod). **However**, **`normalized_query` stores the full normalized user query in plaintext** (up to 48k). If “query text” includes normalized form, this **contradicts** a strict reading of “hashed only.” | **HIGH** |
| G2 | **Track A** `log_chat_turn` persists **full user message and assistant reply** in **`message`** with **no** `query_text_hashed` / `normalized_query`. Legacy path still **plaintext user content** in DB. | **HIGH** (for product paths that still hit `POST /chat`) |
| G3 | **`search_debug.log`** + **`search_log`** write **raw user query** and expanded `query_message` to disk on Track A search. | **MEDIUM** (disk + operator access; gitignored) |
| G4 | **`[search_diag]` stdout** prints query text and event titles → **Railway logs**. | **MEDIUM** |
| G5 | **Sentry** without scrubbing → potential **third-party** storage of request/exception details. | **MEDIUM** |
| G6 | **`hint_extractor`** logs **`raw[:200]`** on envelope validation failure → possible **user-content leakage** to log stream. | **MEDIUM** |
| G7 | **No documented retention / TTL** for `chat_logs` or related tables; **no automated deletion** in app or migrations. | **LOW** for code drift (expected at this stage); **NOTE** as required **transparency** for `docs/privacy.md` |
| G8 | **Anthropic / OpenAI / Google** subprocessors: **no in-repo user-facing policy** text. | **LOW**–**MEDIUM** (documentation; subprocessor listing) |
| G9 | **`chat_logs.message`** = **assistant plaintext** for unified rows — aligns with 8.0.5 “message = response text” correction; **not** a hash column. If any doc still says “message is hashed query,” that is **wrong**. | **LOW** (doc clarity) |
| G10 | **`query_text_hashed` column** is **real** in ORM and prod; not handoff-only drift. | **NOTE** |
| G11 | **Legacy NULL `tier_used`** — not privacy-sensitive. | **NOTE** |
| G12 | **Test fixtures / seeds** — synthetic catalog and queries; no production user linkage in-repo. | **NOTE** |

### STOP-trigger note (owner prompt)

- **Encountered:** **G1 + G2** — **plaintext query representations** persist (`normalized_query`, Track A `message` for user role) while Phase 8.7 text states query text is **hashed** and **not** logged as plaintext.
- **Recommendation:** Owner confirms intended posture: (a) **hash or drop `normalized_query`**, (b) **Track A retirement / alignment** with unified logging, (c) **narrowing the privacy claim** to “raw query fingerprint = `query_text_hashed`” if normalized plaintext is intentionally retained for analytics.
- **Third-party policy depth (Anthropic/OpenAI/Google/Sentry):** Larger legal/compliance surface than one implement pass — **flag for `docs/privacy.md` + links**, not a code STOP unless owner mandates scrubbers.

---

## 6. Proposed scope for **8.7-implement**

### 6.1 `docs/privacy.md` (primary deliverable)

**Recommendation:** **Draft the full page in 8.7-implement** using this report as the source of truth; include in this read-first only a **skeleton** (below) so implement is “fill + owner edits,” not rediscovery.

**Skeleton outline**

1. **What we collect (summary table)** — chat_logs, contributions, mentions, session memory, logs.  
2. **How we use it** — analytics, quality, abuse prevention (IP hash), operator review.  
3. **What we share (subprocessors)** — Anthropic, OpenAI, Google Places, hosting logs, Sentry — with “see their policies” links.  
4. **Retention** — current posture: **no automatic deletion** of `chat_logs`; event cleanup for pending_review only.  
5. **Your choices** — feedback API, session IDs client-generated, contribute optional email.  
6. **Contact** — placeholder for owner legal contact.

### 6.2 Code changes (only if owner wants behavior to match strict §8.7 wording)

| Change | Closes | Tests | Risk |
|--------|--------|-------|------|
| **Hash or remove `normalized_query`** (or store truncated hash only) | G1 | Router/logging tests, any admin/report SQL that reads column | **Medium** — analytics / debugging loss |
| **Track A:** stop logging raw user `message` OR migrate Track A to unified logging / hash | G2 | `test_phase2`, router integration | **Medium** — depends on product sunsetting `POST /chat` |
| **Disable or gate `search_log` + `[search_diag]` in production** (env flag) | G3, G4 | Search tests; ensure diagnostics still available in dev | **Low–medium** |
| **Sentry `before_send` / `before_breadcrumb` scrubbing** for `/api/chat` and `/chat` bodies | G5 | Smoke / unit with mocked SDK | **Medium** — could hide useful debug |
| **Remove or downgrade `hint_extractor` `raw[:200]` log** | G6 | Hint extractor tests | **Low** |

### 6.3 Out-of-scope for 8.7-implement (suggested)

- Full **ToS** (8.5).  
- **Legal review** of subprocessor DPAs.  
- **Building a retention job** (unless owner explicitly expands scope — would push toward **large**).

### 6.4 Estimated implement size

- **Docs-only** (privacy page + known-issues cross-link if desired): **small**.  
- **Docs + 1–3 targeted code changes** (e.g., gate `search_log`, scrub Sentry, redact hint log): **medium**.  
- **Docs + broad schema change** (`normalized_query` + Track A overhaul): **large** — **split** or separate phase unless owner accepts migration + read path risk.

**This read-first’s recommendation:** Treat **8.7-implement** as **medium** if owner wants **HIGH** items (G1/G2) addressed with **minimal** code (e.g., document reality first, then one behavioral fix owner selects). If owner mandates **all** HIGH items with schema migrations, escalate to **large** and split.

---

## 7. Code citations (ground truth)

Unified hash + logging call:

```233:270:app/chat/unified_router.py
def route(query: str, session_id: str | None, db: Session) -> ChatResponse:
    t0 = time.perf_counter()
    sid = _stable_session_bucket(session_id)
    q_raw = query or ""
    q_hash = hashlib.sha256(q_raw.encode("utf-8")).hexdigest()
    ...
            chat_log_id = log_unified_route(
                db,
                session_id=sid,
                query_text_hashed=q_hash,
                normalized_query=nq_safe,
                ...
                response_text=response,
```

Persisted row shape:

```36:52:app/db/chat_logging.py
        row = ChatLog(
            session_id=session_id[:128],
            message=(response_text or "")[:48000],
            role="assistant",
            intent=legacy_intent,
            query_text_hashed=query_text_hashed[:128],
            normalized_query=(normalized_query or "")[:48000] if normalized_query else None,
            ...
        )
```

Track A persistence:

```65:74:app/db/chat_logging.py
        row = ChatLog(
            session_id=session_id[:128],
            message=(text or "")[:48000],
            role=role if role in ("user", "assistant") else "user",
            intent=intent[:64] if intent else None,
            tier_used=TRACK_A_TIER_USED,
        )
```

File logger for search:

```10:31:app/core/search_log.py
LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "search_debug.log")
logging.basicConfig(level=logging.DEBUG)
_log = logging.getLogger("search_diag")
_fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
...
def log_query(raw: str, intent: str, slots: dict, strategy: str) -> None:
    _log.info("=== SEARCH QUERY ===")
    _log.info("RAW INPUT   : %s", raw)
```

Tier 3 user message to Anthropic:

```161:172:app/chat/tier3_handler.py
    user_text = f"User query:\n{query.strip()}\n\n{mid}\n\n{context}"
    ...
        msg = client.messages.create(
            ...
            messages=[{"role": "user", "content": user_text}],
        )
```

---

**End of report.** Do **not** commit this file until owner runs 8.7-implement workflow.
