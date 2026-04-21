# Phase 6.4 — Pre-commit gates report (voice, integration, tokens, manual)

**No commit** — awaiting owner review and explicit `approved, commit and push`.

---

## 1) Voice spot-check

- **Command:** `.\.venv\Scripts\python.exe scripts/run_voice_spotcheck.py`
- **Result:** Smoke **OK**; report **`scripts/output/voice_spotcheck_2026-04-21T20-20.md`** (production `https://havasu-chat-production.up.railway.app`).

### Manual score (PASS / MINOR / FAIL)

**19 / 1 / 0** — meets **≥ 19/1/0**.

- **MINOR:** **Query 17** (*Boat rentals on the lake?*) — same persistent pattern (`chat` / OOS copy with closing follow-up), consistent with prior batteries.

### Temporal / t3-01 signal (vs. prior baseline, e.g. `voice_spotcheck_2026-04-21T19-41.md`)

- **Query 9 — “Events tomorrow” (Tier 3):** Still *“I don't have tomorrow's date locked in…”* + CVB pointer — **no clear improvement** vs. prior run (same class of hedge).
- **Query 6 — “Things to do this weekend” (Tier 3):** Wording shifted slightly; response now includes *“…or let me know the date and I'll tell you what's in the catalog.”* vs. prior *“…try golakehavasu… for what's posted this week.”* — **not** a clean “resolve this weekend / tomorrow from **Now:**” win; if anything, **more** follow-up surface. **t3-01 closure is not demonstrated** on this production battery (either model behavior unchanged, or **Now:** context not yet enough to change temporal answers on these rows).
- **Tier 3 input tokens** in this run (~**3099–3104**) are a bit **higher** than the earlier April 21 sample (~**3031–3038**), consistent with extra **`Now:`** (+ hint) context in the user payload, without visible temporal-quality gain on Q6/Q9.

---

## 2) Integration LLM suite (`-m integration`)

- **Command:** `.\.venv\Scripts\python.exe -m pytest tests/test_classifier_hint_extraction_integration.py -m integration`
- **Environment:** After `ensure_dotenv_loaded()`, **`OPENAI_API_KEY` was not set** in the agent environment (no key available from `.env` for that run).

### Outcome

**Not run — pass rate N/A.**

Per the owner rule (**≤3/5 → STOP**): **4/5 or 5/5 cannot be validated** until the same command is run **with `OPENAI_API_KEY` exported** (or added to `.env` for local runs). Treat **gate 2 as open** until that passes.

---

## 3) `hint_extractor` token usage (≥10 turns)

- **Script:** `scripts/measure_hint_extractor_tokens.py` (12 mixed queries, same prompt/model/settings as `hint_extractor`).
- **Run in agent environment:** exits with **`OPENAI_API_KEY not set`** — **no mean input/output numbers** were produced here.

### Outcome

**Not measured — gate 3 open.**

After `OPENAI_API_KEY` is set, from repo root:

```bash
.\.venv\Scripts\python.exe scripts/measure_hint_extractor_tokens.py
```

Compare printed means to **~300 input / ~100 output**; if either mean exceeds that, **STOP** and trim prompt / tighten JSON per spec.

---

## Manual acceptance (a) & (b)

Full **live** Tier 3 + OpenAI in the agent workspace was not possible without keys. **Wiring was verified locally** with `TestClient` + controlled mocks:

- **Script:** `scripts/run_manual_phase64_verify.py`
- **(a)** Onboarding POST + mocked `extract_hints(age=6, location="near the channel")` + Tier 3 mock: session shows **visiting / kids / age / location**; **`answer_with_tier3`** received **`onboarding_hints`** and a **`now_line`** containing the **current calendar year** (Lake Havasu clock).
- **(b)** Two `/api/chat` turns with Tier 3 path mocked: **`prior_entity`** set after explicit Altitude query; second turn **“what time does it open?”** passed **resolved entity name** into **`answer_with_tier3`** matching **`prior_entity.name`**.

**Output:** `scenario_a: OK` / `scenario_b: OK`.

---

## Summary

| Gate | Status |
| --- | --- |
| Voice (19/1/0) | **Pass** |
| Integration (4/5+) | **Not run** (no `OPENAI_API_KEY`) |
| Token means (&lt;~300 / ~100) | **Not measured** (no `OPENAI_API_KEY`) |
| Temporal / t3-01 on prod spot-check | **No improvement observed** on Q6/Q9 |
| Manual (a)(b) | **OK** at wiring level (scripted `TestClient` + mocks) |

Waiting on **`approved, commit and push`** after owner runs gates 2–3 with a key and reviews.
