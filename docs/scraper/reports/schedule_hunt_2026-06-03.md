# Schedule Hunt — first run report (2026-06-03)

42 candidate businesses identified from the DB; all websites crawled. Details in
`schedule_hunt_candidates.csv`. Headlines:

## Full schedules found on websites (ready to model as Offerings/Schedules)
- **The Tap Room Jiu Jitsu** — complete weekly grid (Gi M/W, NoGi T/Th, kids 4:00/4:30/5:15p, adults 6:15p, MMA W/F, wrestling Sat, open mat Sun) — thetaproomjiujitsu.com/schedule
- **LHC Aquatic Center** — water classes ($5: Ai-Chi, Aqua Aerobics, Tai Chi, Warm Water Yoga), open swim Jun–Jul noon–4 (exc T/Th), swim lessons $42/8, Swim League + Jr Lifeguard M/W or T/Th — lhcaz.gov (+2 PDF grids)
- **Lake Havasu Senior Center** — Tai Chi Qigong Fri 12p ($1), Arts & Crafts Thu 8:30–11a, daily lunch, billiards M–F — lakehavasuseniorcenter.com/current-events
- **Iron Wolf G&CC** — Line Dancing Wed 5–8p, themed dinners Wed/Thu, concerts — ironwolfgcc.com/events-calendar

## Partial (some info, times missing or stale)
Amalaya Yoga (class list yes, times in JS widget), Beyond Dance (schedules in PDFs), Tennis Association (M/T/Th night doubles, no clock times), Sportsman's Club (range mornings W/Sa/Su, no match calendar), the studio 2959 (2024-dated bootcamp times), Scuba Training (courses on demand), LH Golf Club (lessons $75, no times), Grand Piano Studio (school-year lessons), Yacht Club (members Fri).

## Queued for Facebook capture (15 venues) — `schedule_hunt_fb_queue.csv`
Planet Fitness, Altitude Trampoline Park, Stingrays Swim Team, Anytime Fitness,
Iron Age Gym, FOS Gym, LH Bike & Fitness, Amalaya (times), Cycle Therapy,
Havasu Martial Arts, The Dance Center, Swivel & Sway, For Dog's Sake!, Tennis
Assoc (times), PetSmart Training. → Needs the OpenClaw capture cron (supervised
setup; reuse the proven chromium-exec pipeline from PROJECT_HANDOFF.md).

## Appointment-only (no schedule exists — exclude)
Chris Padgett Fitness, Heart & Sole, Athletic Advantage, Soul Lifting,
Pilates of LH, MJ's Dog Training (classes paused), Hava Math Tutor.

## Flags for Casey
- **WACKO Kayak** — website is dead (domain disconnected); business may be closed.
- **Align and Define Pilates** — no website or FB found at all.
- "Kids Activities Studio", "River Rat Yacht Club", "RockerBens" — no website on file; need research or removal.
- SARA Park Disc Golf lives in a FB **group** (needs login) — deferred per architecture.
- DB fixes: Stingrays entity has fake website + generic name; Tap Room missing address.
