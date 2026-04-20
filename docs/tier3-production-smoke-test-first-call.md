# Tier 3 production smoke test — first real `curl` (report for Claude)

**Context:** One controlled `POST /api/chat` to live Railway production **before** Phase 3.2 was deployed there. Command run **exactly once** (no second query).

**Command:**

```bash
curl.exe -X POST https://havasu-chat-production.up.railway.app/api/chat \
  -H "Content-Type: application/json" \
  --data-binary "@tier3_test.json"
```

**Payload file `tier3_test.json`:**

```json
{"query":"what's a good place for my 6-year-old to burn off some energy?", "session_id":"tier3-first-real-call"}
```

---

## Full JSON response body

```json
{"response":"Ask mode: intent=OPEN_ENDED, entity=none. Retrieval will be implemented in Phase 3.","mode":"ask","sub_intent":"OPEN_ENDED","entity":null,"tier_used":"placeholder","latency_ms":34}
```

---

## Approximate latency

| Metric | Value |
|--------|--------|
| Wall time around `curl.exe` (client-side stopwatch) | ~**314 ms** |
| `latency_ms` in response body (server-reported) | **34** |

---

## `tier_used`

**`"placeholder"`** — **not** `"3"`.

The copy matches **pre–Phase 3.2** behavior (placeholder ask path: “Retrieval will be implemented in Phase 3”). So this hit did **not** exercise Tier 3 or a real Anthropic call on the server that was live at that URL.

---

## `llm_tokens_used`

**Field absent** from the JSON (older API shape). No token count from this response.

---

## Anthropic Console (console.anthropic.com)

- Automated agents **cannot** authenticate to your Anthropic account; usage dashboard must be checked **manually**.
- Given the response above, **no Tier 3 / Anthropic usage is implied** for this specific request. Expect **no new line item** from this curl alone; anything visible would be other traffic or prior runs.

---

## Bottom line

**Production** at `https://havasu-chat-production.up.railway.app` **did not** appear to have **Phase 3.2** (Tier 3 + `llm_tokens_used`) deployed at the time of this test.

**Next step to validate Tier 3 for real:** deploy the Phase 3.2 commit to that Railway service, then repeat **one** controlled `curl` with the same payload. Expected after deploy: `tier_used: "3"`, a real concierge `response`, and `llm_tokens_used` populated when the API returns usage.

---

## Local artifacts (repo)

| File | Purpose |
|------|--------|
| `tier3_test.json` | Request body for the documented `curl` |
| `tier3_prod_response.json` | Raw response body saved from the single run |

Remove or gitignore these if you do not want them in the working tree long-term.
