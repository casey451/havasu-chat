# Schedule Hunt — Workstream A continuation (2026-06-04, Cowork supervised)

Per `docs/PROMPT_COWORK_KICKOFF_2026-06-05.md` Workstream A. Auto-publish OFF.
Sandbox posting was blocked (stale pre-rotation token in the `.env` mount, sha8
efc1efaa → 401), so findings were packaged into resend scripts; **Casey ran
`scripts/resend_pending.ps1` same day — all 7 queued: Driftwood Group Riding
Lessons 610, Roping Group 611; Eight Lotus Lymphatic Bliss 612, Pranayama
Vinyasa 613, Havasu Hula Dance 614, Slow Flow Hip Yoga 615, Mat Pilates 616.**
Payload JSONs also in session outputs `ingest_2026-06-04_continuation/`.

## 1. CSV backfill — DONE

`schedule_hunt_candidates.csv` updated with all 6/04 validation + gather + browser
findings (statuses now: dead-site Trinity MMA / Flips For Fun / Windy Hills;
fb-only Kaizen / Shaolin Kempo / NextGen MMA; schedule-down Havasu Pilates /
Crazy Ed's; not-launched Soul Lifting; stale-source-only Marsh; blank-embed LHC
Pickleball + paused-til-Dec-2026 detail; posted-contribution IDs 563–609 noted on
their venues; address flags Desert Bloom / HavaLife / Driftwood; Bella Faccia
skincare-only note; Horseback + Lions FC seasonal pauses). `schedule_hunt_fb_queue.csv`
reasons synced (dead-site/fb-only). Both CSVs parse clean (94 + 27 rows, uniform
field counts).

## 2. Stingrays (567) — summer grid NOT posted yet

`gomotionapp.com/team/azhsaz` practice page still shows the expired Nov 10 '25 –
Jun 2 '26 grid verbatim; Team News page is stale 2024 content. Nothing to
supersede 567 with. Re-check next run (city news still the only summer source:
7–9a at Aquatic Center).

## 3. Eight Lotus — re-observed via Chrome (NOT a second week yet)

The week-1 observation was earlier the SAME day (6/04), so today's read is a
same-week re-read, not the second week — **563/564 confidence NOT raised.** The
booking widget only exposes the current 7 days (next-week chevron does not
advance); a true second-week check needs a run on/after Thu 6/11.

What the re-read DID find (live Mindbody widget, Jun 4–10):

- Consistent with week 1: Yin Thu 5:15p + Sun 3p; Heated Ashtanga Fri 5:30a
  (Ginny Sautner) + Sat 8:30a (Diane Bradley); TruFusion Pilates Mon+Fri 8:15a
  (Lizelle Landicho); Breathwork Mon 9:30a (Jessica Vicari); Slow Flow Mon 4:30p;
  Belly Dance Mon 6:15p + 7:15p (now titled "Beginners" / "Choreography",
  Savanna Cosentino).
- **NEW: Tuesday now has 6 classes** (Tue was unselectable/empty in week 1):
  TruFusion Pilates 5:30a; Lymphatic Bliss: Face + Body Reset 8a (Toni Icard);
  Pranayama Vinyasa 9:30a (Monique Day); Havasu Hula Dance 1p (Kahealani
  Cherland); Slow Flow Hip Yoga 5:15p (Adrianna Gardocki); Mat Pilates 6:30p
  (Ja'nette Hodge).
- Hula conflict: week 1 saw Hula Thu 1p; it now appears Tue 1p (today's Thu view
  only showed 5:15p Yin, but past classes hide on "today" so Thu Hula can't be
  disconfirmed). Flagged in the payload at 0.55.
- Wednesday remains unselectable → no Wed classes.

**5 new Tue findings packaged** in `scripts/resend_eightlotus_tue.ps1`
(conf 0.55–0.60, single-observation per conventions): Lymphatic Bliss,
Pranayama Vinyasa Yoga, Havasu Hula Dance, Slow Flow Hip Yoga, Mat Pilates.
Tue 5:30a TruFusion NOT posted — same title as queued 563 (Mon/Fri 8:15a), the
program dedup would eat it; noting here instead: 563's record may eventually
need the Tue 5:30a slot represented somehow (separate time → separate row?
Casey's call).

## 4. Next venue batch

- **Universal Sonics Gymnastics & All Star Cheer — FULL weekly grid captured**
  via the machine-readable ClassScheduleDeluxe component (now in the CSV row):
  public rec classes M–Th (Rec Gym, Tiny Tumblers, Gym Tots, Boys Athletics,
  Rec Tumbling, Rec Cheer) + team blocks. NOT posted: venue has no entity id in
  the map, and the grid carries no validity dates while the site elsewhere says
  gymnasts are "on off season" — verify (928-453-1313) before ingest.
- **Lake Havasu Little League** — regular season (opened Feb 28) is over;
  All-Stars period now; per-team schedules behind Team Central JS. No postable
  weekly grid. Revisit Oct (fall ball) / Feb.
- **Lake Havasu Chiefs** — SportsEngine site is an empty JS shell to raw fetch;
  fall sport off-season. Browser pass ~Aug registration.

## 5. Blockers / for Casey

1. **Sandbox mount staleness is now a repeating failure mode, and it's not just
   `.env`** (stale token sha8 efc1efaa again this session — a FRESH session, so
   "fresh mounts get the new value" is not reliable). It also served a stale,
   truncated snapshot of `schedule_hunt_candidates.csv` mid-session (Desert
   Bloom row missing, HavaLife cut mid-notes) while the Windows-side file was
   verified complete and uniform (94 lines, 8 fields/row) via direct read.
   Treat sandbox reads of repo files as advisory; Windows-side file state is
   authoritative. Options for the token: re-save/touch the Windows `.env`, store
   the token where the sandbox reads fresh, or accept the resend-script pattern
   as standard.
2. ~~Run the resend scripts~~ DONE — 610–616 queued (see header).
3. Queued 563–566 still await your admin review (567 superseded later; do NOT
   admin-Approve scraper findings — PR #127 manual-attach / auto-publish path).
4. Eight Lotus second-week observation: schedule a run on/after Thu 6/11 —
   that's the one that can justify ≥0.85 on 563/564 (and now also confirms the
   new Tue lineup + the Hula day question).
5. Universal Sonics: worth adding to the entity-id map + a quick phone check on
   season status; the grid is rich and fully fetchable.
