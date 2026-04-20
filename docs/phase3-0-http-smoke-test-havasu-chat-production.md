# Phase 3.0 — HTTP smoke test (canonical production URL)

**Host:** `https://havasu-chat-production.up.railway.app`  
**Not:** `https://web-production-bbe17.up.railway.app` (separate deployment; see investigation below)

**Scope:** Read-only `curl` GET/POST. Temp JSON bodies lived under `%TEMP%` as `havasu_smoke_*.json` and were **removed after** the POSTs.

---

## 1. `GET /`

**Command:**

```bash
curl.exe -sS "https://havasu-chat-production.up.railway.app/" -o NUL -w "HTTP %{http_code}\n"
```

**Output:**

```text
HTTP 200
```

---

## 2. `GET /health`

**Command:**

```bash
curl.exe -sS "https://havasu-chat-production.up.railway.app/health"
```

**Output:**

```json
{"status":"ok","db_connected":true,"event_count":43}
```

`event_count` **43** matches the database populated via Phase 3.0 / `railway run`.

---

## 3. `POST /api/chat` — greeting

**Body file:** `{"query":"hey","session_id":"phase3-smoke-test"}`  
**Command:** `curl.exe -sS -X POST "https://havasu-chat-production.up.railway.app/api/chat" -H "Content-Type: application/json; charset=utf-8" --data-binary "@…greeting.json"`

**Output:**

```json
{"response":"Hey.","mode":"chat","sub_intent":"GREETING","entity":null,"tier_used":"chat","latency_ms":28}
```

- `mode`: `chat`  
- `sub_intent`: `GREETING`  
- `tier_used`: `chat`  
- `response`: `"Hey."` (allowed greeting variant)

---

## 4. `POST /api/chat` — Altitude hours

**Body file:** `{"query":"what time does altitude open"}`  
**Command:** `curl.exe … --data-binary "@…altitude.json"`

**Output:**

```json
{"response":"Ask mode: intent=TIME_LOOKUP, entity=Altitude Trampoline Park — Lake Havasu City. Retrieval will be implemented in Phase 3.","mode":"ask","sub_intent":"TIME_LOOKUP","entity":"Altitude Trampoline Park — Lake Havasu City","tier_used":"placeholder","latency_ms":1}
```

- `mode`: `ask`  
- `sub_intent`: `TIME_LOOKUP`  
- `entity`: `Altitude Trampoline Park — Lake Havasu City`  
- `tier_used`: `placeholder`

---

## 5. `POST /chat` — Track A weekend

**Body file:** `{"message":"what's happening this weekend","session_id":"phase3-smoke-test"}`  
**Command:** `curl.exe … --data-binary "@…weekend.json"`

**Output:**

```json
{"response":"Nothing on for that time. Want to peek at what's coming up later?","intent":"LISTING_INTENT","data":{"count":0,"search":{"slots":{"date_range":{"start":"2026-04-25","end":"2026-04-26"},"activity_family":null,"audience":null,"location_hint":null},"recent_utterances":["what's happening this weekend"],"last_result_set":{"ids":[],"query_signature":"what's happening this weekend"},"listing_mode":true,"snapshot_stack":[],"last_date_range":{"start":"2026-04-25","end":"2026-04-26"}}}}
```

- `intent`: `LISTING_INTENT`  
- `data.count`: **0** for parsed weekend **2026-04-25**–**2026-04-26** (valid if nothing falls in that window)

---

## Investigation — `web-production-bbe17` and Railway CLI

### `railway environment list`

From the linked `havasu-chat` repo:

```text
Environments

production (linked)
  └ updated 3 days ago
```

Only **production** appeared in that listing for this link context.

### `railway service list`

```text
Service "list" not found.
```

**Railway CLI 4.40.0** treats `railway service list` as a **service named `list`**, not a list command. There was **no** successful non-interactive service inventory from this invocation.

### `railway list` (account projects)

```text
casey451's Projects
  Havasu chat
  insightful-embrace
```

The account has **at least two** projects. The hostname **`web-production-bbe17.up.railway.app`** is **not** resolved to a specific project or service by these CLI outputs alone.

### What we can say about **bbe17**

- **`havasu-chat-production`** `/health` reported **43** events; **bbe17** reported **27** on the same endpoint earlier — **different databases / deployments**.  
- HTTP response headers for both hosts are generic (`railway-edge`, Fastly) and **do not** expose project or service IDs.  
- **Dashboard follow-up:** search Railway **networking / domains** for `web-production-bbe17` (and check **insightful-embrace** or any legacy Havasu deployments) to see which **service + environment** owns that URL before keep / decommission / ignore.

---

## Related docs

- `docs/railway-production-url-and-db-diagnosis.md` — canonical URL, variable redaction notes, bbe17 vs linked DB  
- `docs/phase3-0-http-smoke-test-web-production-bbe17.md` — historical smoke on **bbe17** (wrong host for current build)
