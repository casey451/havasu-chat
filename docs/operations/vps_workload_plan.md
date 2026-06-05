# VPS Workload Plan — Hostinger srv1729030 ("the Openclaw box")

Date: 2026-06-04. Prepared from direct inspection of the VPS, the OpenAI/Anthropic
billing dashboards, and the havasu-chat codebase. Status: awaiting Casey's
approval at Gate A. Nothing in this plan has been executed.

---

## 1. Measured inputs (no estimates)

### 1.1 The VPS, inspected over SSH 2026-06-04

| Fact | Value |
|---|---|
| Host | srv1729030.hstgr.cloud (2.25.168.120), Hostinger KVM 4, paid through 2027-06-03 |
| OS | Ubuntu 24.04.4 LTS, kernel 6.8.0-111 |
| Resources | 4 vCPU, 15 GB RAM (1.0 GB used), 193 GB disk (8 GB used), load avg 0.00 |
| Running | Docker + Traefik (ports 80/443) + one container: `ghcr.io/hostinger/hvps-openclaw` on port 60340 |
| **"Openclaw" resolved** | It is **Hostinger's OpenClaw AI-agent product**, installed from their "Docker and Traefik" VPS template. **Not** Open WebUI, **not** Ollama. No local models exist on the box. |
| Security posture | Root SSH allows password auth; no host firewall observed (22/80/443/60340 open); Hostinger malware scanner not installed |

### 1.2 Real API spend (billing dashboards, read 2026-06-04)

| Item | May 2026 | June 1–4 |
|---|---|---|
| OpenAI total | **$5.42** | $0.49 |
| — gpt-4.1-mini (input/output/cached) | $3.99 / $0.72 / $0.27 | — |
| — gpt-4o-mini (all) | $0.43 | — |
| — **text-embedding-3-small** | **$0.002** (2,848 requests / 17.8K tokens in the 5/20–6/4 window) | ~$0 |
| Anthropic | ~$6 (claude-haiku-4-5, May 1–7 only: 5.78M in / 105K out) | **$0.00** — zero usage, zero balance |

The Anthropic→OpenAI migration on 2026-05-07 (`app/core/llm_messages.py` docstring:
"every Anthropic call site was migrated to OpenAI gpt-4o-mini") is confirmed by both
the code and the dashboards. **Total current AI spend ≈ $5–6/month.**

### 1.3 Code paths (verified in repo)

- **Embeddings**: OpenAI `text-embedding-3-small`, hardcoded in `app/core/extraction.py:277`
  and `app/chat/llm_cache.py:24`. Generated at ingest time (events/providers/programs)
  plus per-query only on Tier-3 cache similarity misses. Stored as JSON columns
  (`providers.embedding`, `events.embedding`, `programs.embedding`,
  `llm_response_cache.query_embedding`) — **no pgvector**. Dimension fragmentation
  exists (1536 real vs 32-dim deterministic fallback in `extraction.py:295`).
- **LLM calls**: tiered router (`app/chat/unified_router.py`). Tier 1 regex templates and
  Tier 2 parser+SQL are deterministic and zero-token; Tier 3 fallback is `gpt-4.1-mini`
  (150 max tokens) behind a semantic response cache. `USE_INTENT_LAYER` and
  `USE_LLM_ROUTER` flags default OFF.
- **Background jobs**: all scheduled work runs as **GitHub Actions cron** (parks-rec every
  6h, River Scene M/W/F, gas prices daily, GoLakeHavasu events+partners), writing
  **directly to the production DB** via the `DATABASE_URL` repo secret. Nothing
  scheduled runs on Railway; in-process hourly cleanup runs in the FastAPI lifespan.
- **Deploy**: Railway auto-deploys `main`; `railway.json` preDeploy runs
  `alembic upgrade head` (63 migrations). There is **no staging environment anywhere**;
  migrations are rehearsed nowhere before they hit prod.

---

## 2. The savings model — projected at 5,000 daily users

**Casey's correction (2026-06-04): the site is pre-launch, so May's $5.42 is dev
traffic, not a baseline. Target: 5,000 DAU.** The model below projects from measured
per-call unit costs instead (gpt-4.1-mini: $0.40/M in, $1.60/M out), assuming 4
turns/user/day → ~20K turns/day. That multiplier is an assumption to validate at launch.

| Cost line at 5K DAU | Per call | Calls/day | $/month |
|---|---|---|---|
| **Hint extractor** (`unified_router.py:868` — fires on **every turn**, ~378 in / ≤100 out) | ~$0.0003 | ~20,000 | **~$180** |
| Tier 3 synthesis (~20% of turns × ~50% cache miss, ~500 in / 30 out) | ~$0.00025 | ~2,000 | ~$15 |
| Query embeddings (Tier-3 cache lookups, ~20 tokens) | ~$0.0000004 | ~2,000 | **~$0.02** |
| Ingest embeddings + extraction | — | volume-independent of DAU | ~$1 |
| **Projected total** | | | **~$200/mo, ±2× on the turns/user assumption** |

**The headline finding is in the code, not the infrastructure:** the hint extractor is
~90% of projected spend and runs synchronously on the hot path — every turn, including
Tier-1 regex lookups, waits ~1s on an OpenAI call before any tier executes. That
single call site undermines both the cost structure and the sub-200ms target. Making
it conditional (regex-first, only call the LLM when a hint pattern is plausible),
cached per session, or async would cut projected spend ~10× — worth more than any
VPS workload by two orders of magnitude. Recommend adding this as a pre-launch code
task (it is not a VPS matter).

Even at 5K DAU, embeddings round to **$0.02/month** — the local-embedding no-go
survives the scale correction by a factor of ~1,000.

### Candidate workloads

| Candidate workload | Monthly $ saved (at 5K DAU) | Cost to implement | Verdict |
|---|---|---|---|
| Local embedding service | **~$0.02** | Re-embed entire corpus (new vector space, can't mix with existing OpenAI vectors), fix 32/1536 dimension fragmentation, centralize hardcoded model refs, build retrieval-quality eval, operate a service | **NO-GO.** Even at full target scale, embeddings round to pennies. Revisit only if embedding spend exceeds ~$20/mo. |
| Local LLM serving live traffic | n/a | n/a | **NO** (hard boundary; CPU box, serializes under load) |
| Local LLM for intent catalog generation | ~$0 (catalog is static code — `tier1_templates.py`, `intents/dicts.py` — regenerated never, only edited and deployed) | n/a | **NO** (the premise doesn't exist in the codebase) |
| Move batch jobs off Railway | **$0** — jobs don't run on Railway; they run free on GitHub Actions | Self-hosted runner or cron migration + secrets handling | **NOT NOW.** Nothing to save. Revisit only if Actions minutes/limits bite or a job needs >6 GB RAM. |
| Staging mirror | $0 saved — but this was never a cost play | ~1 day of setup, $0 marginal (box is sunk cost, 14 GB RAM free) | **GO.** The value is risk elimination: every push to `main` currently applies untested migrations to prod. |

**Conclusion:** projected spend at 5K DAU (~$200/mo) is real but its fix is a code
change (hint extractor), not hardware — no VPS workload touches it. The VPS still
cannot pay for itself in API savings. Its value is as **infrastructure**: a staging
mirror and load-test rig that de-risks `main` auto-deploying migrations to prod, now
with launch traffic coming.

---

## 3. Concurrency: the stated assumption

Basis: **5,000 DAU (Casey's launch target), assumed 4 turns/user/day → ~20K turns/day.**
Distinguishing in-flight concurrency from volume:

- 20K turns/day with 5× peak-hour concentration ≈ **1–1.5 requests/second peak**.
- In-flight concurrency = arrival rate × latency. On deterministic-path latencies
  (10–150 ms) that's **<1**; with today's synchronous per-turn hint-extractor call
  (~1 s), it's still only **~1–2 in flight at peak** — but every one of those requests
  is slow for the user. Fixing the hint extractor matters more than capacity.
- **Design/test target: 50 concurrent in-flight requests, 25 RPS sustained** on the
  deterministic path — ≥15× headroom over the 5K-DAU peak, covering bursts, retries,
  and the turns/user assumption being off by 2–3×.
- **Validation gate (post-launch)**: a read-only aggregate over `chat_logs` (counts
  per hour, p95 `latency_ms` by `tier_used`) to replace the turns/user assumption with
  measured truth. Needs Casey's approval to run against prod (read-only, no writes).
- Watch item at this rate: Railway runs a **single uvicorn process** (Procfile) —
  the load test should specifically confirm one worker + the Postgres connection pool
  hold 25 RPS, and the fix if not is `--workers N`, not new hardware.

The 8-core/32 GB upgrade question stays **deferred**: the box is at load 0.00 with
14 GB RAM free, and no identified workload needs more. Let the Phase-3 load test
surface a bottleneck first; none is expected.

---

## 4. Phased plan (smallest reversible steps, approval gate before each)

### Phase 1 — Staging mirror, synthetic data (reversible: `docker compose down`)
1. Docker Compose on the VPS: `postgres:16` + the app built from a feature branch,
   routed through the existing Traefik with HTTP basic-auth, deployed alongside (not
   replacing) the OpenClaw container.
2. `alembic upgrade head` against the staging Postgres — first-ever rehearsal of the
   full 63-migration chain from empty.
3. Seed via existing seed/fixture scripts (no prod data), run `pytest -q` and
   `scripts/post_deploy_smoke.py` against staging.
4. Hygiene piggyback (cheap while we're in there): disable SSH password auth, enable
   UFW (22/80/443 + staging port), and decide keep/remove for the unused OpenClaw
   container.

**GATE A (Casey):** approve the compose file, Traefik route, firewall change, and
OpenClaw keep/remove decision. *Nothing touches Railway or prod.*

### Phase 2 — Prod-shaped data, migration rehearsal becomes routine
1. Casey exports a Railway Postgres backup (Claude doesn't handle the secrets);
   restore into staging. Decide whether `chat_logs`/`users` need scrubbing first.
2. Standing rule going forward: any PR containing an alembic migration gets restored-
   backup + `alembic upgrade head` rehearsal on staging before merge to `main`.
3. Re-point one scrape workflow (e.g. parks-rec) at staging as a dry-run lane to
   rehearse ingest changes — prod lanes untouched.

**GATE B (Casey):** approve backup handling/scrubbing and the dual-lane workflow change.

### Phase 3 — Load test (plan-only until the command is approved)
1. Tooling: extend `scripts/smoke_concurrent_chat.py` or add a k6 script; target the
   deterministic path (Tier 1/2 query battery from `scripts/run_query_battery.py`).
2. Run against **staging** at 25 RPS / 50 concurrent; record p50/p95/p99 by tier,
   with the hint extractor both on and off (it dominates per-turn latency today).
3. Only if staging passes and Casey approves the exact command: a capped, read-only,
   low-rate run against Railway prod (hard request cap, off-peak, abort threshold).
4. Run the `chat_logs` aggregate (Gate above) to replace the concurrency assumption
   with measured truth.

**GATE C (Casey):** approve the prod load-test command verbatim, or skip prod and
accept staging numbers.

### Phase 4 — Optional batch-lane expansion (only if a trigger fires)
Triggers: GitHub Actions minutes exhausted, a job needs more memory than runners
offer, or a job needs a stable egress IP for proxy/scrape reasons. Until then: no action.

### Explicit no-gos (recorded so they stay decided)
- Local embedding migration: **no-go** per savings model above (eval-gated revisit
  only if embedding spend > $20/mo).
- Local LLM on the serving path: **no**, permanent for this box (CPU-only).
- VPS plan upgrade: **deferred** pending a load-test-surfaced bottleneck.

---

## 5. Loose ends for Casey

- Delete `C:\Users\casey\projects\havasu-chat\.tmp_vps_key` (the temporary key copy;
  it is gitignored but shouldn't linger). The original stays in `~/.ssh`.
- Chrome on the work machine has a new-tab hijacker redirecting new tabs to
  `signalqueryhub.com` — check `chrome://extensions` and remove the culprit.
- Consider GitHub branch protection on `main` (per CLAUDE.md backstop note) — Phase 2's
  "rehearse before merge" rule is only as strong as the merge gate.
