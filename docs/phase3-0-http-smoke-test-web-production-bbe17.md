# Phase 3.0 — HTTP smoke test (live production)

**Host:** `https://web-production-bbe17.up.railway.app`  
**Scope:** read-only `curl` GET/POST only — no `railway run`, no database writes.

PowerShell mangled inline `curl -d` JSON; POST bodies 3–5 used temporary JSON files with `curl --data-binary @file`, then files were removed.

---

## 1. Home page — `GET /`

**Command:**

```bash
curl.exe -sS -o NUL -w "HTTP %{http_code}\n" "https://web-production-bbe17.up.railway.app/"
```

**Result:**

```text
HTTP 200
```

Home page loads without HTTP error.

---

## 2. Health — `GET /health`

**Command:**

```bash
curl.exe -sS "https://web-production-bbe17.up.railway.app/health"
```

**Full JSON response:**

```json
{"status":"ok","db_connected":true,"event_count":27}
```

| Field | Value | Note |
|--------|--------|------|
| `status` | `ok` | As expected |
| `db_connected` | `true` | As expected |
| `event_count` | **27** | **Not** `43` — this deployment’s DB still reports 27 events (same as prior `GET /events` checks). If Phase 3.0 targeted a different Railway service/DB, align public URL ↔ `DATABASE_URL`. |

---

## 3. Concierge — `POST /api/chat` (greeting)

**Body:**

```json
{"query":"hey","session_id":"phase3-smoke-test"}
```

**Full JSON response:**

```json
{"response":"Hey.","mode":"chat","sub_intent":"GREETING","entity":null,"tier_used":"chat","latency_ms":1}
```

| Field | Value |
|--------|--------|
| `mode` | `chat` |
| `sub_intent` | `GREETING` |
| `tier_used` | `chat` |
| `response` | `"Hey."` |

---

## 4. Concierge — `POST /api/chat` (Altitude hours)

**Body:**

```json
{"query":"what time does altitude open"}
```

**Full JSON response:**

```json
{"response":"Ask mode: intent=TIME_LOOKUP, entity=Altitude Trampoline Park — Lake Havasu City. Retrieval will be implemented in Phase 3.","mode":"ask","sub_intent":"TIME_LOOKUP","entity":"Altitude Trampoline Park — Lake Havasu City","tier_used":"placeholder","latency_ms":1}
```

| Field | Value |
|--------|--------|
| `mode` | `ask` |
| `sub_intent` | `TIME_LOOKUP` |
| `entity` | `Altitude Trampoline Park — Lake Havasu City` |
| `tier_used` | `placeholder` |
| `response` | Placeholder ask copy; Phase 3 retrieval still deferred |

---

## 5. Track A — `POST /chat` (weekend listing)

**Body:**

```json
{"message":"what's happening this weekend","session_id":"phase3-smoke-test"}
```

**Full JSON response:**

```json
{"response":"Nothing on for that time. Want to peek at what's coming up later?","intent":"LISTING_INTENT","data":{"count":0,"search":{"slots":{"date_range":{"start":"2026-04-25","end":"2026-04-26"},"activity_family":null,"audience":null,"location_hint":null},"recent_utterances":["what's happening this weekend"],"last_result_set":{"ids":[],"query_signature":"what's happening this weekend"},"listing_mode":true,"snapshot_stack":[],"last_date_range":{"start":"2026-04-25","end":"2026-04-26"}}}}
```

| Field | Value |
|--------|--------|
| `intent` | `LISTING_INTENT` |
| `data.count` | **0** |
| Parsed `date_range` | `2026-04-25` — `2026-04-26` |

Zero results are valid if no events fall in that weekend window for this DB snapshot.

---

## Summary

| Step | Outcome |
|------|---------|
| 1 `GET /` | **200** |
| 2 `GET /health` | OK, DB connected, **`event_count`: 27** (≠ 43) |
| 3 `POST /api/chat` “hey” | Greeting path OK |
| 4 `POST /api/chat` Altitude time | `TIME_LOOKUP`, entity + placeholder tier |
| 5 `POST /chat` weekend | Track A shape OK; **`data.count`: 0** for parsed range |
