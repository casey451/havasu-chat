# Tier 3 production testing — Round 2 — 2026-04-19

Four controlled `POST https://havasu-chat-production.up.railway.app/api/chat` calls (no others). Request/response JSON files were deleted after capture.

---

## Query 1 — Out of scope (restaurants)

**Request:**

```json
{"query":"any good restaurants in Havasu?","session_id":"tier3-round2-1"}
```

**Full JSON response:**

```json
{
  "response": "That's outside what I cover right now — I stick to things-to-do, local businesses, and events. Want me to point you to anything else?",
  "mode": "chat",
  "sub_intent": "OUT_OF_SCOPE",
  "entity": null,
  "tier_used": "chat",
  "latency_ms": 15,
  "llm_tokens_used": null
}
```

| Field | Value |
|--------|--------|
| `tier_used` | `chat` |
| `llm_tokens_used` | `null` |
| Server `latency_ms` | 15 |
| Wall time (curl `time_total`) | ~0.20 s |

**Observations:** `mode` = `chat`, `OUT_OF_SCOPE`, no Tier 3 spend (`llm_tokens_used` null). Voice is clear and on-policy (declines restaurants, offers pivot). Server latency under 100 ms; total curl time higher due to network TLS/RTT.

---

## Query 2 — Tier 1 phone lookup

**Request:**

```json
{"query":"what's the phone number for altitude?","session_id":"tier3-round2-2"}
```

**Full JSON response:**

```json
{
  "response": "Altitude Trampoline Park — Lake Havasu City: (928) 436-8316.",
  "mode": "ask",
  "sub_intent": "PHONE_LOOKUP",
  "entity": "Altitude Trampoline Park — Lake Havasu City",
  "tier_used": "1",
  "latency_ms": 28,
  "llm_tokens_used": null
}
```

| Field | Value |
|--------|--------|
| `tier_used` | `1` |
| `llm_tokens_used` | `null` |
| Server `latency_ms` | 28 |
| Wall time (curl) | ~0.18 s |

**Observations:** `PHONE_LOOKUP`, Tier 1, no LLM tokens. `(928) 436-8316` matches seeded Altitude provider data. Short, direct. Server latency under 300 ms.

---

## Query 3 — Date night (Tier 3)

**Request:**

```json
{"query":"what's good for a date night?","session_id":"tier3-round2-3"}
```

**Full JSON response:**

```json
{
  "response": "For a fun, active date night, try **Altitude Trampoline Park** on Highway 95 N—they're open till 8pm Friday and 9pm Saturday, with 90-minute or 120-minute jump sessions for $19–$24. If you're looking for something more cultural, **Grace Arts Live** has theatre productions like *Alice in Wonderland Jr.* coming up in late June.",
  "mode": "ask",
  "sub_intent": "DATE_LOOKUP",
  "entity": null,
  "tier_used": "3",
  "latency_ms": 1856,
  "llm_tokens_used": 1735
}
```

| Field | Value |
|--------|--------|
| `tier_used` | `3` |
| `llm_tokens_used` | 1735 |
| Server `latency_ms` | 1856 |
| Wall time (curl) | ~2.03 s |

**Observations:** `tier_used` = `3` as expected for this path. **Classifier note:** `DATE_LOOKUP` rather than `OPEN_ENDED` — still reasonable for “date night.” **Grounding:** Altitude on Highway 95 N, Fri/Sat closing times, and $19 / $24 align with seeded hours and programs (90 min @ $19, 120 min @ $24). Grace Arts Live and *Alice in Wonderland Jr.* in late June match catalog events in Tier 3 context. No restaurants. **Voice:** Markdown bold/italics inside `response` — acceptable depending on client; flag if plain text is required. Two catalog-backed pillars (active + theatre), not inappropriate categories (e.g. random kids’ gymnastics as “date night”).

---

## Query 4 — BMX for kids (Tier 3 + entity)

**Request:**

```json
{"query":"tell me about bmx for kids","session_id":"tier3-round2-4"}
```

**Full JSON response:**

```json
{
  "response": "Lake Havasu City BMX at Sara Park offers programs for kids ages 5+: Tuesday practice ($5), Wednesday training ($5), and Thursday racing ($10, Oct–Jun). They've also got a balance bike track for ages 1–5. Call (928) 208-5388 or check usabmx.com/tracks/1292 for details.",
  "mode": "ask",
  "sub_intent": "OPEN_ENDED",
  "entity": "Lake Havasu City BMX",
  "tier_used": "3",
  "latency_ms": 2100,
  "llm_tokens_used": 2669
}
```

| Field | Value |
|--------|--------|
| `tier_used` | `3` |
| `llm_tokens_used` | 2669 |
| Server `latency_ms` | 2100 |
| Wall time (curl) | ~2.30 s |

**Observations:** `entity` = Lake Havasu City BMX. `sub_intent` = `OPEN_ENDED` (not `AGE_LOOKUP`). **Grounding (post-hoc DB read via `railway run`, not a chat call):** Phone `(928) 208-5388`, website `usabmx.com/tracks/1292`, Tuesday practice $5, Wednesday training $5, Thursday race $10 Oct–Jun, Strider/balance bike track — aligned with seeded `Provider` / `Program` rows; “ages 1–5” for the balance-bike track is a reasonable reading of Strider program copy. **Voice:** Leads with venue, day-by-day structure, closes with contact + official link.

---

## Batch summary

| # | Intent / tier | `llm_tokens_used` | Notes |
|---|-----------------|-------------------|--------|
| 1 | `OUT_OF_SCOPE` / `chat` | `null` | Fast path, correct refusal. |
| 2 | `PHONE_LOOKUP` / `1` | `null` | Verbatim phone from catalog. |
| 3 | `DATE_LOOKUP` / `3` | 1735 | Intent label differs from “OPEN_ENDED” expectation; still catalog-grounded, no restaurants. |
| 4 | `OPEN_ENDED` + entity / `3` | 2669 | Strong match to BMX seed data including URL and phone. |

---

## Cleanup

`q1.json`–`q4.json` and `q1_response.json`–`q4_response.json` were removed from the working tree after reporting. No additional production chat calls.
