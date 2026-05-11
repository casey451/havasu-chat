# Background-Job Infrastructure — Decision Memo

> **Status:** design + decision only; no implementation.
> **Source gap:** Gap #3 (Gap 7 in the §2 table; "background-job infrastructure")
> in `docs/maintainability/architecture_gaps_for_full_vision_audit.md` §3.7.
> **Audience:** Cowork primary + Casey; future implementation-lane author.
> **Date:** 2026-05-14.

---

## §1 Problem statement

The full Lake Havasu directory vision (pivot §1, §4) requires multiple
async/scheduled jobs that currently have no home. Today the codebase has
exactly one durable background pattern — `_hourly_cleanup_loop` at
`app/main.py:246`, an in-process `asyncio.create_task` started in the
`lifespan` context manager (`app/main.py:256`). That loop sleeps 3600 seconds
and calls `run_expired_review_cleanup` (`app/main.py:227`) which marks expired
`pending_review` Event rows as `deleted`. Everything else either (a) runs
inline on the request thread, (b) rides on FastAPI `BackgroundTasks` and dies
with the worker process, or (c) is operator-triggered from the shell.

This doesn't scale to the post-pivot product. Concrete failure cases:

- **A sponsor signup blocks the HTTP request for 200-500ms while Resend's API
  is called** (per Resend's documented send latency; pivot §8.3 locked
  Resend as the magic-link provider). Per-request `BackgroundTasks`
  (`app/api/routes/chat.py:62`, `app/contrib/enrichment.py:18`) get us most
  of the way there but die on worker restart — a failed send is silent.
- **Scrapers must be hand-run.** `python -m scripts.places_discovery` and
  `python -m scripts.places_enrichment` (per the module-level docstrings at
  `scripts/places_discovery.py:10-13` and `scripts/places_enrichment.py:13-15`)
  are operator-triggered. The directory pivot needs systematic refresh across
  12 categories on a recurring cadence; nothing today drives that.
- **Image processing on owner-uploaded photos** (gap #9 in the audit) will
  pin the upload request for several seconds while Pillow resizes for thumb +
  card + hero, then uploads three derivatives to storage. Inline = bad UX.
- **Re-verification** has no driver. `Provider.last_verified_at` feeds the
  freshness bands defined at `app/providers/queries.py:44-46`
  (`fresh`/`acceptable`/`aging`/`stale`); nothing periodically scans for stale
  rows and flags them for re-touch.

The shape we want: a single, documented background-work pattern that covers
both **scheduled** (cron-like) and **event-triggered** (queue-like) jobs,
without exotic new infrastructure. The shape we want to avoid: Celery + Redis
+ Beat + Flower for a 50-business catalog and a single-founder ops surface.

---

## §2 Required job types (inventory)

### §2.1 Scheduled jobs (cron-like)

| Job | Cadence | Latency tolerance | Failure mode |
|---|---|---|---|
| Places discovery sweep per category | Weekly per category, staggered across days | Hours (not minutes) | Retry next cycle; alert if 3 consecutive failures |
| Places enrichment refresh on aged rows | Daily on rows where `last_verified_at` is `aging` (per `app/providers/queries.py:44`) | Hours | Retry next cycle; surface in admin staleness queue |
| Re-verification flag pass | Weekly (mark rows crossing into `stale` band) | Hours | Idempotent; silent skip on failure |
| `_hourly_cleanup_loop` (existing) | Hourly | Hours | Already silent-skip; runs again next hour |
| Cache warming (`LlmResponseCache` pre-compute) | Hourly for top-N common queries | N/A — best-effort | Silent skip |
| Operator analytics rollup (Phase 3 — sponsor reporting) | Daily | Hours | Retry next cycle |

### §2.2 Event-triggered jobs (queue-like)

| Job | Expected frequency at launch | Latency tolerance | Failure mode |
|---|---|---|---|
| Magic-link email send via Resend (gap #8) | 10-50/day initially, growing with user adoption | <5s end-to-end | Retry 2x, then surface "resend link" UI; log to Sentry on exhaustion |
| Sponsor approval / claim-verification email | <5/day initially | <30s | Retry 2x; admin alert on exhaustion |
| Owner-uploaded image processing (gap #9) | <20/day at launch (scales with sponsor count) | <60s (user sees "processing" state) | Retry once; surface failure on profile edit page |
| Mention scanning (already shipped) | Per Tier 3 chat reply | <30s | Already best-effort via `BackgroundTasks` (`app/api/routes/chat.py:62`) |
| Contribution enrichment (already shipped) | Per contribution submission | <30s | Already best-effort via `BackgroundTasks` (`app/contrib/enrichment.py:18`) |

Notable: the existing two `BackgroundTasks` consumers
(`scan_and_save_mentions` and `enrich_contribution`) already prove the pattern
for non-critical event-triggered work. The new ones (Resend, image processing)
have stricter durability requirements — a magic-link email that silently fails
costs us a user signup.

---

## §3 Three credible options

### §3.1 Option A — Railway scheduled-jobs service for scheduled + FastAPI `BackgroundTasks` (with retry wrapper) for event-triggered

Railway natively supports scheduled jobs by deploying a separate service that
runs a one-shot command on a cron schedule (general industry knowledge; the
Railway cron-jobs docs describe this pattern but I could not fetch them in
this environment — see §9 Q4). Pattern: a sibling Railway service that runs
`python -m scripts.places_discovery --category $CATEGORY` once and exits;
Railway re-runs it next tick.

For event-triggered work, use FastAPI's built-in `BackgroundTasks` (already
proven at `app/api/routes/chat.py:62`, `app/contrib/enrichment.py:18`) wrapped
in a small retry helper.

**Pros:** zero new infra components (Railway-native cron + existing FastAPI
primitive; no Redis, no broker). Cron service deploys from the same repo;
same env vars, DB pool, logs. Operator already understands the scripts;
cron is just "Railway runs that command on a schedule." Migration to
Celery/Dramatiq later is clean — `BackgroundTasks` call sites become
`enqueue(...)` one at a time.

**Cons:** `BackgroundTasks` runs in the web worker process; worker kill
mid-task = lost task (mitigation: idempotent tasks + a DB-backed `Outbox`
for must-not-lose jobs like magic-link send). Railway's cron tier may
require a paid plan (open Q4). No central job dashboard — observability
is Railway logs + Sentry breadcrumbs.

**Requires:** one new Railway service per scheduled-command entry (or one
parameterized service driven by `$JOB_NAME`); a small `app/core/background.py`
retry-wrapper module; an `Outbox(Base)` model for the must-not-lose subset.

**Does not require:** Redis (until/unless slowapi moves Redis-backed for
gap #14 — separate decision); Celery / Dramatiq / RQ in `requirements.txt`
(confirmed absent today per `requirements.txt:1-72`); a worker process
Procfile entry.

### §3.2 Option B — Celery + Redis (or equivalent: Dramatiq, RQ)

Full task-queue infrastructure. A Redis broker (~$5-10/mo Railway add-on); a
Celery worker service that consumes from the queue; optionally a Celery Beat
scheduler service for cron-like work. Event-triggered jobs become
`task.delay(...)` calls from the web tier.

**Pros:** battle-tested reliability semantics (retry policies, dead-letter
handling, task acknowledgement, idempotency primitives); horizontal scaling
via N workers; mature observability (Flower, RQ Dashboard); centralized
retry logic.

**Cons:** three new Railway components (Redis, worker, optional Beat) —
each is a new ops surface and a bill line. Operator complexity climbs:
deploys must coordinate worker + web; broken workers silently stall queues;
serialization-incompatible task signatures break in production. Overkill
at launch scale (audit §3.7 called for RQ as the V1 cut; this memo argues
even that is premature). Migration cost is non-trivial — every
event-triggered call site rewrites through a task layer; tests need a
worker harness.

**Requires:** new Railway Redis + worker services; new Python deps
(`celery` + `redis-py`, or `rq` + `redis-py`); serialization-safe task
modules; a broker-SLA decision (Railway Redis is single-instance / not HA
by default).

**What it gets us:** a reliability ceiling we don't need at launch but will
need at, say, 10k sponsor count or 100k DAU.

### §3.3 Option C — In-app asyncio scheduler (extend the existing `_hourly_cleanup_loop` pattern)

Run all scheduled tasks inside the existing FastAPI process via additional
`asyncio.create_task` loops, modeled on `app/main.py:246`. Event-triggered
tasks continue using FastAPI `BackgroundTasks`.

**Pros:** zero new infra; lowest deploy complexity; cheapest dollars.
Leverages a pattern already shipping. Lowest cognitive load for a new
contributor.

**Cons:** job lifetime couples to web-server lifetime — Railway restart
kills jobs mid-flight (idempotency mitigates but doesn't eliminate).
Horizontal scaling means every scheduled job runs N times without
leader-election (audit §5 mentions "Railway autoscaling readiness").
Scrapers contend for CPU + DB pool with web traffic — audit §5.1 already
flags pool exhaustion at ~200 concurrent users. No job-state inspection
beyond Sentry. Long-running scraper sweeps (places enrichment is 30+
minutes per the `scripts/places_enrichment.py:22` "~$100" cost note)
inside the web process are an outage risk.

**Requires:** additional `asyncio.create_task` calls in
`app/main.py:lifespan` per new job. That's it.

**Verdict:** a prototyping-only answer once the directory has paying
sponsors.

---

## §4 Per-option comparison

| Option | New infra | Ops complexity | Reliability | Horizontal scale | Migration cost | Recommended for |
|---|---|---|---|---|---|---|
| A — Railway cron + asyncio + `BackgroundTasks` | None (just a new Railway service) | Low | Medium (idempotent + Outbox for critical) | Medium (cron service is single-instance; web workers OK) | Low | V1 + launch |
| B — Celery / RQ + Redis | Redis + worker service (+ optional Beat) | High | High | High | Medium-High | Production scale beyond V1 (e.g. >1000 jobs/day) |
| C — In-app asyncio only | None | Lowest | Lowest | Lowest (runs N times) | Zero | Prototyping only — not launch |

The audit (§3.7 of `architecture_gaps_for_full_vision_audit.md`) originally
recommended RQ + Redis. After reviewing the inventory in §2 above and the
single-existing-pattern at `app/main.py:246`, the recommendation in this
memo diverges — Option A is the right V1 cut. Reasoning in §5.

---

## §5 Recommendation

**Pick Option A** for V1 with a clear upgrade path to Option B when load
justifies it.

Reasoning:

- **Current scale doesn't justify Celery / RQ / Redis.** Per §2 above, the
  launch-cadence inventory is ~10 scheduled job types and <100
  event-triggered jobs/day. The most-frequent event-triggered job
  (magic-link email at 10-50/day) does not stress any of the three options.
- **Railway scheduled jobs are native infrastructure.** No new Python
  dependency, no new service-type to learn, same repo deploy. Compares
  favorably to Redis + Celery on every ops axis except raw reliability —
  and the reliability gap is closeable with an `Outbox` table for the small
  handful of must-not-lose jobs.
- **`BackgroundTasks` is already proven in this codebase.** Two production
  consumers (`app/api/routes/chat.py:62`,
  `app/contrib/enrichment.py:18`) demonstrate the pattern works for our
  current event-triggered surface area. The new jobs (Resend send, image
  processing) extend the pattern, they don't introduce it.
- **The asyncio-loop pattern at `app/main.py:246` is proven.** For
  cache-warming and other in-process schedulers, this is the cheapest
  available answer. We're not betting the company on it — we're betting
  one job type (cache warming) on it, and cache warming is best-effort by
  definition.
- **Upgrade path to Option B is clean.** Each event-triggered call site is
  a one-line change: `background_tasks.add_task(send_magic_link, ...)`
  becomes `send_magic_link.delay(...)` with Celery. Each cron service
  becomes a Beat schedule. Schedule the migration when failure rates,
  observability needs, or scaling demands actually justify it — not on
  speculation.

The audit recommended RQ + Redis because it framed the foundation as
"unblock email + image processing + scrapers in one infra add." That framing
optimizes for "consolidate the future." This memo optimizes for "ship the
present cheaply, migrate when forced." Both are reasonable; the present-
optimization wins because the founder-led ops surface is the binding
constraint, not the future-tech-debt surface.

---

## §6 Implementation pattern for Option A

### §6.1 Scheduled scraper service (Railway cron)

Add new Railway service(s) that run `python -m scripts.places_discovery
--category $CATEGORY` and `python -m scripts.places_enrichment` on cron
schedules. The scripts already exist and are operator-runnable today
(`scripts/places_discovery.py:1-100`, `scripts/places_enrichment.py:1-100`).
Required additions to the scripts:

- A `--category` flag on `places_discovery` (currently has `--dry-run` —
  category-aware filtering should land alongside the cron service).
- Idempotency review: confirm the resume-safe pattern at
  `scripts/places_enrichment.py:89-100` (`load_processed_ids`) holds under
  unattended re-runs.
- Schedule design: stagger categories across days of week (e.g. home services
  Monday, eat & drink Tuesday, …) so no single day saturates the Google
  Places quota.

The scripts already use `app.contrib.rate_limiter.SourceLimiter`
(`app/contrib/rate_limiter.py:39`) which provides retry + QPS pacing — so
running under cron inherits the same rate-limit semantics as operator-
triggered runs. No code change needed in the limiter.

### §6.2 Event-triggered tasks via FastAPI `BackgroundTasks`

For magic-link email send (pivot §8.3 Resend):

```python
@router.post("/api/auth/request-link")
async def request_link(email: str, background_tasks: BackgroundTasks):
    token = create_token(email)
    background_tasks.add_task(send_magic_link_email, email, token)
    return {"status": "sent"}
```

Wrap each task in a small retry helper at `app/core/background.py`:

```python
def with_retry(fn, *args, max_attempts=3, backoff_initial_s=1.0, **kwargs):
    """Execute fn with bounded retries on transient failure.
    On exhaustion, log to Sentry breadcrumb. Tasks must be idempotent."""
```

For magic-link specifically (must-not-lose), pair `BackgroundTasks` with an
`Outbox(Base)` table:

- On request: write a row to `Outbox(kind='magic_link', payload=..., state='pending')`
  inside the request transaction.
- After commit: `background_tasks.add_task(deliver_outbox_row, row_id)`.
- The cron service (§6.1 sibling) runs `python -m scripts.outbox_redrive`
  every 5 minutes, picking up rows in `state='pending'` older than 30s and
  retrying.

This pairs the best of `BackgroundTasks` (hot-path speed) with the durability
of a DB-persisted queue, without a Redis broker.

### §6.3 Async loops for in-app schedulers

Extend the existing `_hourly_cleanup_loop` pattern (`app/main.py:246`) for
any in-process scheduler. Example shape for cache warming every 15 minutes:

```python
async def _cache_warm_loop() -> None:
    while True:
        await asyncio.sleep(900)
        await asyncio.to_thread(warm_llm_response_cache)
```

Wired into `lifespan` (`app/main.py:252-264`) alongside the existing
`_hourly_cleanup_loop` task. Each loop is best-effort and idempotent;
process restart re-starts the loop with the next sleep window.

Cap on this pattern: do not use it for any job longer than ~5 seconds or any
job with strict timing requirements. The web process is shared with traffic.

### §6.4 Image processing

Two paths:

1. **V1 — inline via `BackgroundTasks`.** Acceptable for the launch volume
   (<20/day per §2.2). Processing time is 3-5s on a modest image; runs after
   the upload response returns. Failure surfaces on next profile edit.
2. **V2 — externalize to a Railway cron service that polls an
   `unprocessed_images` table.** Triggered the moment image volume exceeds
   ~100/day or processing time exceeds 10s/image (large RAW uploads).

V1 is the day-one cut. Build path for V2 is the same Outbox pattern as
§6.2.

---

## §7 Migration path to Option B (if/when needed)

**Triggers to upgrade:** job failure rates exceed ~10/day; job latency p95
exceeds tolerable bounds; observability beyond Sentry becomes essential
(e.g. "I never got the email" support tickets we can't diagnose);
horizontal scaling forces the issue (Railway autoscaling means in-process
schedulers start double-firing).

**Migration steps (rough order):** (1) Add Redis service (~$5/mo). (2) Add
`dramatiq` or `celery` to `requirements.txt`; author `app/jobs/` with task
definitions. (3) Add Railway worker service. (4) Move `BackgroundTasks`
call sites into the new task framework one at a time; web tier becomes a
thin enqueue layer. (5) Move scheduled jobs from Railway cron services into
Celery Beat / Dramatiq's scheduled middleware. (6) Decommission asyncio
loops in `app/main.py:lifespan`. (7) Decommission `Outbox` redrive.

**Estimated migration effort when triggered:** L (1-2 weeks elapsed) for a
single engineer who already knows the call sites. Migration is mechanical;
the cost is testing and infra learning curve.

---

## §8 Resend integration considerations

Resend (locked in pivot §8.3 for magic-link auth) is the highest-frequency
event-triggered job at launch.

- **Resend free tier:** 100 emails/day, 3000/month (per Resend's public
  pricing as of 2026; verify before launch).
- **Resend first paid tier:** ~$20/month for 50k emails.
- **Launch-scale fit:** Well within free tier (10-50 magic-link sends/day +
  <5 sponsor notifications/day = <60/day).
- **Send latency via Resend API:** 200-500ms typical (Resend's documented
  P50; verify against operator's own measurements once integration ships).
- **Failure modes:**
  - 429 rate-limited — retry with exponential backoff via the
    `app/core/background.py` retry wrapper. Resend rate limits are
    generous; should not hit at launch volume.
  - 5xx API down — retry 3x then surface to user as "resend link" CTA.
  - 4xx invalid email — fail fast; do not retry; surface validation error
    inline (this means the auth-request route must validate email format
    before enqueueing).

**Conclusion:** FastAPI `BackgroundTasks` + retry wrapper + `Outbox` table
(§6.2) is sufficient for V1 Resend integration. Move to Celery / Dramatiq
only once email volume justifies broker-grade retry semantics (probably
>1000 emails/day, well beyond Phase 1 / launch).

---

## §9 Open questions for Casey

1. **Are you OK with Option A's reliability characteristics for V1?** Specifically:
   asyncio loops die on Railway restart and resume on next process boot;
   in-flight `BackgroundTasks` can be lost on worker kill (mitigated for
   magic-link by the `Outbox` table; not mitigated for image processing
   in V1). If "magic-link emails may occasionally fail silently" is
   unacceptable, we should ship the `Outbox` table on day one rather than
   V1.5.
2. **Should the scheduled scraper services run on Railway cron (new service
   per category) or as one parameterized service driven by env vars?** Per-
   category gives finer-grained control + logs; parameterized service is
   one fewer line item on the Railway bill.
3. **For image processing — V1 inline via `BackgroundTasks`, or externalize
   from day one?** Inline is faster to ship and acceptable at launch volume.
   Externalizing avoids one future migration. The audit (§3.7) leaned
   toward externalizing; this memo leans toward inline-then-externalize.
4. **Railway cron pricing — what tier does the operator's current Railway
   plan include?** I was unable to fetch Railway's cron-services pricing
   docs in this environment. Casey: please confirm before the
   implementation lane lands. If cron-services require an upgrade tier and
   the upgrade cost is meaningful, Option A's $-cost rises.
5. **Cache warming — is it actually worth shipping in V1?** `LlmResponseCache`
   already exists (`app/db/models.py:421` per the audit). Pre-warming requires
   knowing the top-N queries; that signal builds over the first weeks of
   real traffic. Acceptable to defer cache warming to V1.5 and only ship
   `_hourly_cleanup_loop` and Resend send in the initial Option A cut?
6. **Observability — what's the minimum bar?** Sentry breadcrumbs on retry
   exhaustion is the cheap floor. A dedicated "background-jobs" Sentry tag
   + a weekly Sentry digest is the next tier up. Anything richer (a
   dashboard) implies Option B.

---

## §10 Effort estimate

Per-component, assuming Option A:

| Component | Effort | Notes |
|---|---|---|
| `app/core/background.py` retry-wrapper module + tests | S | ~50 lines of code; pattern is simple |
| Lift `_hourly_cleanup_loop` into the new module as documented reference pattern | S | Already works; just relocation + doc |
| Railway cron service for `places_discovery --category` | S (operator action) | 1-2 hours per category × 12 categories; can stagger across weeks |
| Railway cron service for `places_enrichment` aged-row refresh | S (operator action) | Same shape |
| `BackgroundTasks` integration for Resend magic-link send | S | Parallel with the magic-link auth route (gap #8); shared concern |
| `Outbox(Base)` table + redrive cron service | M | Alembic migration + ~100 lines of job code + tests |
| `BackgroundTasks` integration for image processing | S | Parallel with the image-storage lane (gap #9) |
| Cache-warming asyncio loop | S | Optional V1.5 per §9 Q5 |
| Tests + Sentry tag conventions | M | 1-2 days for full coverage |

**Total — engineering days for V1 Option A cut:**
2-4 days for the framework + first job-type integration. Each subsequent job
type integration (image, cache warming, etc.) is S = a few hours. Operator
Railway-cron-service setup is one of those workflows that's S per service
× number-of-services; spread across the operator's weeks comfortably.

The Outbox table is the largest single chunk (M); deferring it to V1.5
drops the total to ~2 days. Recommended sequence: ship the framework +
inline `BackgroundTasks` first, ship the Outbox table the moment any
must-not-lose job (magic-link) actually goes to production.

---

## §11 Confirmation

No git or state-mutating command was run during the authoring of this
memo. The only file created is
`docs/maintainability/background_job_infrastructure_decision.md` (this
file). All other operations were read-only `Read` and `Grep` calls against
the working tree, plus one attempted (and refused) `web_fetch` against
Railway's documentation URL — noted as a limitation in §9 Q4.
