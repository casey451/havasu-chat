# Schedule Hunt — first supervised publish-path validation (2026-06-04)

Cowork session, supervised by Casey. Goal: prove the scraper → ingest →
review-queue path end to end with real venue schedules, auto-publish OFF.
Outcome: **5 real findings queued, one display bug found and fixed in prod
(PR #133), dedup verified working.**

---

## 1. What was run

Per the kickoff prompt: read `INGEST_PUBLISH_CONTRACT.md` +
`COWORK_JOB_RUNNER_RUNBOOK.md` (from `docs/cowork-job-runner`, since merged),
pick 3–5 venues from the entity-id map likely to publish a class timetable on
their own site, extract real schedules only, POST to
`/api/ingest/contribution` with `target_entity_id` + `proposed_record`, and
report. Token from repo-root `.env` (never echoed).

## 2. Crawl results — venue by venue

### Posted (real schedules found)

| Venue | Source | How read | Found |
|---|---|---|---|
| Eight Lotus Center for Wellness | 8lotuswellness.com/book-class | Live Mindbody widget is JS-only — read via Chrome extension, day tabs Thu Jun 4 → Mon Jun 8 | Full live week: Hula Thu 1p (90m); Yin Thu 5:15p + Sun 3p; Heated Ashtanga Fri 5:30a + Sat 8:30a; TruFusion Pilates Fri + Mon 8:15a; Breathwork Mon 9:30a (45m); Slow Flow Mon 4:30p; Belly Dance Mon 6:15p + 7:15p. Tue/Wed tabs would not select (likely no classes). $20 walk-in / $100 mo unlimited / $150 10-class |
| Ballet Havasu | ballethavasu.org/2025 | Schedule is an image — read via Chrome + zoom | Full 2025/26 season grid, 9 blocks: Tiny Toes Mon 3:30–4p; Ballet Beginnings Mon + Fri 4–4:45p; Elementary Tue 5–6p (B) / Wed 5:45–6:45p (A); Intermediate Tue 3:30–5p (B) / Wed 4–5:30p (A/B) / Thu 3:30–5p (Tech); Advanced Mon + Tue 6–7:30p, Thu 5–6:30p; Pointe Mon 7:30–8:30p; Adult Ballet Tue 6:30–7:30p; New Students 11+ Mon 4:30–6p. Season recital was 5/31/26 — may pause for summer |
| Havasu Stingrays Swim Team | gomotionapp.com/team/azhsaz (practice page) | web_fetch | Clean grid but explicitly dated Nov 10 2025 – Jun 2 2026 — **ended 2 days before crawl**. Summer = reportedly 7–9a at Aquatic Center, not yet published. Posted at 0.30 deliberately |

### Skipped (nothing real to ingest)

- **Trinity MMA**, **Flips For Fun Gymnastics** — sites fully down (error
  pages in a real browser, not just JS shells).
- **Windy Hills Pottery** — services page won't render; only "Tue & Thu
  pottery classes," no clock times anywhere.
- **LHC Pickleball Association** — calendar is an embed that loads blank even
  in Chrome.
- **Havasu Pilates / Crazy Ed's** — schedule taken down ("schedule down =
  sold out"; new schedule "up soon").
- **Soul Lifting** — classes still not launched (consistent with CSV note).
- **Marsh Dance Studios** — only source is a Dec-2024 newspaper article;
  stale per the plan's data rules.
- **Kaizen Golf & Fitness, Havasu Shaolin Kempo, Next Generation MMA** —
  FB-only; left for the OpenClaw sweep.

## 3. Findings posted

All five returned `queued` (auto-publish off — correct), IDs **563–567**:

| ID | Venue | Finding | Days/times | Conf |
|---|---|---|---|---|
| 563 | Eight Lotus | TruFusion Pilates | Mon, Fri 08:15–09:15 | 0.70 |
| 564 | Eight Lotus | Belly Dance: Beginners | Mon 18:15–19:15 | 0.65 |
| 565 | Ballet Havasu | Adult Ballet | Tue 18:30–19:30 | 0.70 |
| 566 | Ballet Havasu | Ballet Beginnings (3–5) | Mon, Fri 16:00–16:45 | 0.70 |
| 567 | Stingrays | Bronze Group Practice | Mon/Tue/Thu 17:00–18:00 | 0.30 (season expired — flagged in description) |

Confidence rationale: Eight Lotus is a live booking feed but recurrence was
inferred from one observed week → 0.65–0.70, below the 0.85 auto-publish
threshold by design. Request JSON bodies kept in the session workspace
(`outputs/ingest/f1–f5.json`).

## 4. The "rows are empty" investigation

Casey reviewed `/admin/contributions` and saw findings with **only a name —
no days/times**. Root-cause chain, including two wrong turns worth recording:

1. **Wrong turn #1:** the local checkout's `main` was stale (PR #116) and its
   `ContributionCreate` had no `proposed_record`/`confidence`/
   `target_entity_id` fields → concluded the fields were silently dropped by
   Pydantic and the contract wasn't deployed. A `git fetch` showed origin/main
   was actually at PR #126 with **#127 (`feat/scraper-loop-hardening`) already
   merged** — the contract was implemented and live.
2. **Wrong turn #2:** deploy-timing theory (posts landed minutes before the
   #127 deploy). Disproved by re-posting all 5 findings: every one returned
   `duplicate / program_already_queued`, and that dedup matches on
   **stored** `(target_entity_id, normalized proposed_record.title)` — so
   rows 563–567 had the full payload all along. (Side benefit: the new
   program dedup is confirmed working in prod.)
3. **Actual bug:** the admin detail page rendered Confidence and Target
   entity but **never rendered `proposed_record`**, and the "Event date /
   Event times" rows it does show are the legacy `event_*` columns — correctly
   empty for program findings. Data fine; display gap.

## 5. The fix — PR #133 (merged `bb0e720`)

`fix(admin): render scraped proposed_record + source URL on contribution detail`
(+136 / 2 files):

- `app/admin/contributions_html.py` — new **"Proposed record (scraped)"**
  section: known ProgramApprovalFields in fixed order (title, description,
  days, start/end, location, address, provider, cost, ages, contacts, tags),
  unknown worker-sent keys rendered after so nothing is hidden; plus a
  clickable **Source URL** row (scraped findings carry `source_url`, not
  `submission_url`, so the existing URL row was always blank for them).
- `tests/test_admin_contributions_html.py` — renders-section test +
  absent-when-no-record test.

Verification before push: built on a fresh shallow clone of origin/main
(`906bbb5`, post-#129); ruff clean; **full suite ~4,200 passed / 8 skipped /
0 failed** on Python 3.12 (run in 24 shards — the sandbox kills background
processes between calls, so no single long run). Pushed from Casey's Windows
checkout (sandbox has no GitHub creds); PR opened via browser; Casey merged.
The "2 of 3 checks" on the PR was CodeRabbit rate-limiting, not a test
failure.

After deploy, contributions 563–567 show their schedules in admin with no
re-posting — the data was in the DB the whole time.

## 6. Pipeline observations for the autonomous loop

- **Dedup** keys on `(target_entity_id, proposed_record.title)` for programs
  and works; same-`source_url` posts do NOT collide (by design — many classes
  share one schedule page).
- **`schedule_hunt_candidates.csv` (21 rows, uncommitted) doesn't cover most
  of the entity-id-map venues** — websites had to be discovered fresh via
  search. Needs a row-fill pass before the next run.
- JS-only portals (Mindbody, Wix calendars, GoDaddy builders) need the
  browser fallback; raw fetch returns empty shells. Schedule-as-image (Ballet
  Havasu) also needs vision. Both worked via the Chrome extension.
- Two venue sites in the map are dead (Trinity MMA, Flips For Fun) — entity
  records may warrant a liveness flag.

## 7. Housekeeping / environment notes

- The shared checkout `C:\Users\casey\projects\havasu-chat` had a **broken
  HEAD** at session start (parallel-session tangling per CLAUDE.md); all git
  reads used explicit refs; the later `git switch` to the PR branch appears to
  have resolved it.
- Stale worktree metadata `hc` in `.git/worktrees` couldn't be removed from
  the sandbox — `git worktree prune` from Windows clears it. The
  `0001-admin-render-proposed-record.patch` in the repo root and the merged
  remote branch can both be deleted.
- Old session leftovers in the sandbox `/tmp` (pr104, havasu-dupe-report,
  hava-fix) hold ~900 MB of venvs; **`/tmp/hava-fix` has uncommitted changes**
  (`app/chat/hint_extractor.py` + a new test) from another session at PR #126
  — reconcile or discard deliberately.

## 8. Follow-ups

1. Backfill `schedule_hunt_candidates.csv` with this session's discoveries
   (websites, schedule URLs, dead-site/FB-only statuses).
2. Casey: review queued 563–567 in admin (do NOT use Approve — it creates a
   new venue; these wait for the auto-publish path or the
   manual-attach flow from #127).
3. Stingrays: re-crawl when the summer schedule posts; 567 can then be
   superseded.
4. Eight Lotus: a second week's observation would justify raising confidence
   toward the 0.85 auto-publish bar.
