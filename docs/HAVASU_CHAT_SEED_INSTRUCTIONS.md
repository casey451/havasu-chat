# HAVASU CHAT — CLAUDE CODE INSTRUCTIONS + SEED DATA
# Drop this file into your project and run: claude "read SEED_INSTRUCTIONS.md and follow the instructions"

---

## INSTRUCTIONS FOR CLAUDE CODE

I have seed data in this file (below the divider) containing verified real-world
programs, classes, and events for Lake Havasu City, AZ to seed into the Havasu Chat
app database.

Please read the seed data below and do the following:

### 1. SEED ALL BUSINESSES
Parse each business header block and create or upsert a Provider
record using: provider_name, category, address, phone, email,
website, facebook, and hours.

### 2. SEED ALL PROGRAMS
For each YAML program block under each business, create a Program
record with these fields:
- title
- activity_category (map to your ActivityCategory enum)
- age_min / age_max (null where not specified)
- schedule_days (array of day strings)
- schedule_start_time / schedule_end_time (24h format, null if unknown)
- schedule_note (store as a plain text note field)
- location_name / location_address
- cost (numeric; store 0.0 for free programs)
- cost_description (plain text pricing detail)
- provider_name (use to link to Provider record)
- contact_phone / contact_email / contact_url
- description

Where cost is CONTACT_FOR_PRICING, set cost to null and
set a boolean field show_pricing_cta = true so the app
displays "Contact for pricing" with a tap-to-call button.

### 3. SEED ALL EVENTS
For each event block, create an Event record with:
title, description, date, time, location, cost, provider.
Where date is a range (e.g. "2026-06-26 through 2026-06-28"),
create separate Event rows for each date.

### 4. SKIP THESE — DO NOT SEED YET
- Elite Cheer Athletics — Havasu (no address confirmed)

Mark them with a draft = true flag so they appear in the
admin dashboard but not in the public app.

### 5. FLAG FOR ADMIN REVIEW
Any program or business with a ⚠️ VERIFY note in the file
should be seeded but tagged needs_verification = true so
they surface in the admin review queue.

### 6. ACTIVITY CATEGORY MAPPING
The file uses these category strings — map them to whatever
enum exists in your schema:
golf, fitness, sports, swim, martial_arts, gymnastics,
cheer, dance, theatre, art, summer_camp

### 7. AFTER SEEDING, PRINT A SUMMARY
- Businesses created
- Programs created
- Events created
- Items flagged needs_verification
- Items skipped (draft)

---
---
---

# HAVASU CHAT — PROGRAMS & EVENTS SEED DATA
**Prepared for:** Claude Code / Cursor database seeding
**Compiled:** April 2026
**Coverage:** Lake Havasu City, AZ — real, verified local programs and events
**Total Businesses:** 25
**Total Programs:** ~125
**Total Events:** 13

---

## NOTES FOR CURSOR

- Fields marked `CONTACT_FOR_PRICING` = no public pricing found; display "Contact for pricing" in app
- Fields marked `⚠️ VERIFY` = confirmed but may need a quick check before going live
- Fields marked `null` = genuinely unknown; leave blank or omit
- `schedule_days` uses: MON, TUE, WED, THU, FRI, SAT, SUN
- Times in 24h format
- Ages in years (0.5 = 6 months, 1.5 = 18 months)
- All addresses in Lake Havasu City, AZ unless noted

---

## BUSINESS 1 — IRON WOLF GOLF & COUNTRY CLUB

```
provider_name:    Iron Wolf Golf & Country Club
category:         golf
address:          3275 N. Latrobe Dr, Lake Havasu City, AZ 86404
phone:            (928) 764-1404
email:            thegolfshop@ironwolfgcc.com
website:          ironwolfgcc.com
facebook:         facebook.com/ironwolfgcc
hours:            Mon 9am–9pm | Tue CLOSED | Wed–Sun 9am–9pm
```

### Programs

```yaml
- title:              Junior Golf Clinic — Session 1
  activity_category:  golf
  age_min:            7
  age_max:            17
  schedule_days:      [MON, WED, FRI]
  schedule_start_time: "07:30"
  schedule_end_time:   "09:30"
  schedule_note:      "2-week session starting June 30, 2026"
  location_name:      Iron Wolf Golf & Country Club
  location_address:   3275 N. Latrobe Dr, Lake Havasu City, AZ 86404
  cost:               250.00
  cost_description:   "$250 per 2-week session. Includes clubs and swag bag."
  provider_name:      Iron Wolf Golf & Country Club
  contact_phone:      (928) 764-1404 ext. 2
  contact_email:      thegolfshop@ironwolfgcc.com
  contact_url:        ironwolfgcc.com
  description:        >
    Small-group junior golf clinic for ages 7–17. Focused instruction,
    small class sizes. Includes clubs and swag bag. Limited availability.
    Register via golf shop phone or email.

- title:              Junior Golf Clinic — Session 2
  activity_category:  golf
  age_min:            7
  age_max:            17
  schedule_days:      [MON, WED, FRI]
  schedule_start_time: "07:30"
  schedule_end_time:   "09:30"
  schedule_note:      "2-week session starting July 14, 2026"
  location_name:      Iron Wolf Golf & Country Club
  location_address:   3275 N. Latrobe Dr, Lake Havasu City, AZ 86404
  cost:               250.00
  cost_description:   "$250 per 2-week session. Includes clubs and swag bag."
  provider_name:      Iron Wolf Golf & Country Club
  contact_phone:      (928) 764-1404 ext. 2
  contact_email:      thegolfshop@ironwolfgcc.com
  contact_url:        ironwolfgcc.com
  description:        >
    Small-group junior golf clinic for ages 7–17. Focused instruction,
    small class sizes. Includes clubs and swag bag. Limited availability.
    Register via golf shop phone or email.
```

---

## BUSINESS 2 — ALTITUDE TRAMPOLINE PARK

```
provider_name:    Altitude Trampoline Park — Lake Havasu City
category:         fitness / active recreation
address:          5601 Highway 95 N, Unit 404-D, Lake Havasu City, AZ 86404
phone:            (928) 436-8316
email:            null (contact form only at altitudetrampolinepark.com)
website:          altitudetrampolinepark.com/locations/arizona/lake-havasu-city/5601-highway-95-n/
facebook:         facebook.com/altitudelakehavasu
hours:            Sun 11am–7pm | Mon 11am–7pm | Tue 10am–7pm | Wed 11am–7pm
                  Thu 10am–7pm | Fri 11am–8pm | Sat 9am–9pm
notes:            Children 12 & under must have adult present.
                  Located in The Shops at Lake Havasu (north end).
```

### Programs

```yaml
- title:              Open Jump — 90 Minutes
  activity_category:  fitness
  age_min:            null
  age_max:            null
  schedule_days:      [SUN, MON, TUE, WED, THU, FRI, SAT]
  schedule_start_time: null
  schedule_end_time:   null
  schedule_note:      "Any open session during business hours"
  location_name:      Altitude Trampoline Park
  location_address:   5601 Highway 95 N, Unit 404-D, Lake Havasu City, AZ 86404
  cost:               19.00
  cost_description:   "$19.00 per person / 90 minutes"
  provider_name:      Altitude Trampoline Park
  contact_phone:      (928) 436-8316
  contact_url:        altitudetrampolinepark.com/locations/arizona/lake-havasu-city/5601-highway-95-n/
  description:        >
    22,000+ sq ft indoor trampoline park. Features trampolines, dodgeball,
    battle beam, ninja warrior course, ValoJump digital experiences, and
    arcade. Socks required ($3.50 if needed). Children 12 & under need
    adult present.

- title:              Open Jump — 120 Minutes
  activity_category:  fitness
  age_min:            null
  age_max:            null
  schedule_days:      [SUN, MON, TUE, WED, THU, FRI, SAT]
  schedule_start_time: null
  schedule_end_time:   null
  schedule_note:      "Any open session during business hours"
  location_name:      Altitude Trampoline Park
  location_address:   5601 Highway 95 N, Unit 404-D, Lake Havasu City, AZ 86404
  cost:               24.00
  cost_description:   "$24.00 per person / 120 minutes"
  provider_name:      Altitude Trampoline Park
  contact_phone:      (928) 436-8316
  contact_url:        altitudetrampolinepark.com/locations/arizona/lake-havasu-city/5601-highway-95-n/
  description:        >
    22,000+ sq ft indoor trampoline park. 120-minute jump session.
    Features trampolines, dodgeball, battle beam, ninja warrior course,
    and more.

- title:              Monthly Membership — Standard
  activity_category:  fitness
  age_min:            null
  age_max:            null
  schedule_days:      [MON, TUE, WED, THU, FRI, SAT, SUN]
  schedule_note:      "5 days/week, 90 minutes/day"
  location_name:      Altitude Trampoline Park
  location_address:   5601 Highway 95 N, Unit 404-D, Lake Havasu City, AZ 86404
  cost:               15.00
  cost_description:   "$15/month — 5 days/week, 90 min/day"
  provider_name:      Altitude Trampoline Park
  contact_phone:      (928) 436-8316
  contact_url:        altitudetrampolinepark.com/locations/arizona/lake-havasu-city/5601-highway-95-n/memberships/
  description:        >
    Monthly membership with unlimited jumping up to 5 days/week,
    90 minutes per visit. Includes member perks and buddy passes.

- title:              Monthly Membership — Unlimited
  activity_category:  fitness
  age_min:            null
  age_max:            null
  schedule_days:      [MON, TUE, WED, THU, FRI, SAT, SUN]
  schedule_note:      "7 days/week, 120 minutes/day"
  location_name:      Altitude Trampoline Park
  location_address:   5601 Highway 95 N, Unit 404-D, Lake Havasu City, AZ 86404
  cost:               25.00
  cost_description:   "$25/month — 7 days/week, 120 min/day"
  provider_name:      Altitude Trampoline Park
  contact_phone:      (928) 436-8316
  contact_url:        altitudetrampolinepark.com/locations/arizona/lake-havasu-city/5601-highway-95-n/memberships/
  description:        >
    Unlimited monthly membership — 7 days/week, 120 minutes per visit.
    Includes exclusive member perks, buddy passes, and special event discounts.
```

---

## BUSINESS 3 — HAVASU LANES

```
provider_name:    Havasu Lanes
category:         sports / bowling
address:          2128 McCulloch Blvd N, Lake Havasu City, AZ 86403
phone:            (928) 855-2695
email:            null (contact form at havasulanesaz.com/CONTACT-US)
website:          havasulanesaz.com
facebook:         facebook.com/HavasuLanesAZ
hours:            Mon–Thu 12pm–9pm | Fri–Sat 12pm–11pm | Sun 12pm–7pm
notes:            32 lanes. Full-service sports bar & grill (Keglers Pub),
                  3 pool tables, 4 dart boards, arcade, bumper bowling.
```

### Programs

```yaml
- title:              Open Bowling
  activity_category:  sports
  age_min:            null
  age_max:            null
  schedule_days:      [SUN, MON, TUE, WED, THU, FRI, SAT]
  schedule_start_time: "12:00"
  schedule_end_time:   "21:00"
  schedule_note:      "Fri–Sat open until 11pm. Fri–Sat after 5:30pm switches to Rock & Bowl."
  location_name:      Havasu Lanes
  location_address:   2128 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               null
  cost_description:   "$5.75/person per game + $5.25 shoe rental + $28.00/hour lane rental"
  provider_name:      Havasu Lanes
  contact_phone:      (928) 855-2695
  contact_url:        havasulanesaz.com
  description:        >
    32-lane bowling center. State-of-the-art automatic scoring, widescreen
    monitors. Bumper bowling available for kids. Arcade room on-site.

- title:              Rock & Bowl (Cosmic Bowling)
  activity_category:  sports
  age_min:            null
  age_max:            null
  schedule_days:      [FRI, SAT]
  schedule_start_time: "18:00"
  schedule_end_time:   "23:00"
  schedule_note:      "Every Friday & Saturday from ~6pm to close"
  location_name:      Havasu Lanes
  location_address:   2128 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               null
  cost_description:   "$18/person (shoes + 1hr unlimited) | $22/person (shoes + 2hrs) | $26/person (shoes + 3hrs)"
  provider_name:      Havasu Lanes
  contact_phone:      (928) 855-2695
  contact_url:        havasulanesaz.com
  description:        >
    Every Friday & Saturday night. Black lights, party lights, and music.
    All-inclusive pricing includes shoe rental and unlimited bowling.

- title:              Youth Bowling Leagues (USBC Certified)
  activity_category:  sports
  age_min:            null
  age_max:            17
  schedule_days:      null
  schedule_note:      "⚠️ VERIFY — schedule and days set each season. Contact league for details."
  location_name:      Havasu Lanes
  location_address:   2128 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Lanes
  contact_phone:      (928) 855-2695
  contact_url:        havasulanesaz.com/LEAGUES/Youth-Leagues
  description:        >
    USBC-certified youth bowling leagues. Local, state, and national
    tournament eligibility. Coaching available. Scholarship opportunities
    through USBC ($6M awarded nationally each year). Year-round play.

- title:              Adult Bowling Leagues
  activity_category:  sports
  age_min:            18
  age_max:            null
  schedule_days:      null
  schedule_note:      "⚠️ VERIFY — multiple leagues (Senior, Men's, Women's, Mixed). Contact for schedule."
  location_name:      Havasu Lanes
  location_address:   2128 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Lanes
  contact_phone:      (928) 855-2695
  contact_url:        havasulanesaz.com/LEAGUES
  description:        >
    Multiple adult league options: Senior, Men's, Women's, and Mixed leagues.
    Contact Havasu Lanes for current season schedules and registration.
```

---

## BUSINESS 4 — BRIDGE CITY COMBAT

```
provider_name:    Bridge City Combat (also: Bridge City Combat & Barry Sullins Jiu-Jitsu)
category:         martial arts
address:          2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
phone:            (928) 716-3009
email:            bridgecitycombat@gmail.com
website:          null (no standalone website)
instagram:        instagram.com/bridgecitycombat  ← PRIMARY contact channel
facebook:         facebook.com/bridgecitycombat (less active)
hours:            Closes 9pm (Google). Full weekly hours not confirmed.
booking:          In-person only. No online registration.
notes:            Schedule current as of October 2025 post. Founder: Christian Beyers.
```

### Programs

```yaml
- title:              Youth Gi Jiu-Jitsu
  activity_category:  martial_arts
  age_min:            5
  age_max:            18
  schedule_days:      [MON, WED]
  schedule_start_time: "17:00"
  schedule_end_time:   "18:00"
  location_name:      Bridge City Combat
  location_address:   2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bridge City Combat
  contact_phone:      (928) 716-3009
  contact_email:      bridgecitycombat@gmail.com
  contact_url:        instagram.com/bridgecitycombat
  description:        Traditional gi Brazilian Jiu-Jitsu for youth (K–12).
                      Submissions, escapes, conditioning, drills, and rolling.

- title:              Youth NOGI Jiu-Jitsu
  activity_category:  martial_arts
  age_min:            5
  age_max:            18
  schedule_days:      [TUE, THU]
  schedule_start_time: "17:00"
  schedule_end_time:   "18:00"
  location_name:      Bridge City Combat
  location_address:   2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bridge City Combat
  contact_phone:      (928) 716-3009
  contact_email:      bridgecitycombat@gmail.com
  contact_url:        instagram.com/bridgecitycombat
  description:        No-gi Brazilian Jiu-Jitsu for youth (K–12).
                      Builds confidence through grappling and self-defense.

- title:              Adult Fundamentals Gi Jiu-Jitsu
  activity_category:  martial_arts
  age_min:            18
  age_max:            null
  schedule_days:      [TUE]
  schedule_start_time: "18:00"
  schedule_end_time:   "19:00"
  location_name:      Bridge City Combat
  location_address:   2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bridge City Combat
  contact_phone:      (928) 716-3009
  contact_email:      bridgecitycombat@gmail.com
  contact_url:        instagram.com/bridgecitycombat
  description:        Entry-level gi class for adults new to Jiu-Jitsu.

- title:              Adult Gi Jiu-Jitsu
  activity_category:  martial_arts
  age_min:            18
  age_max:            null
  schedule_days:      [MON, WED]
  schedule_start_time: "18:00"
  schedule_end_time:   "19:00"
  schedule_note:      "Also Tue 6–7am"
  location_name:      Bridge City Combat
  location_address:   2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bridge City Combat
  contact_phone:      (928) 716-3009
  contact_email:      bridgecitycombat@gmail.com
  contact_url:        instagram.com/bridgecitycombat
  description:        Traditional gi Jiu-Jitsu for adults. All levels welcome.

- title:              Adult NOGI Jiu-Jitsu
  activity_category:  martial_arts
  age_min:            18
  age_max:            null
  schedule_days:      [MON, WED, THU]
  schedule_start_time: "19:15"
  schedule_end_time:   "20:15"
  schedule_note:      "Mon & Wed 7:15–8:15pm. Also Wed 6–7am."
  location_name:      Bridge City Combat
  location_address:   2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bridge City Combat
  contact_phone:      (928) 716-3009
  contact_email:      bridgecitycombat@gmail.com
  contact_url:        instagram.com/bridgecitycombat
  description:        No-gi Jiu-Jitsu for adults. Thu session 6–7pm.

- title:              Adult MMA
  activity_category:  martial_arts
  age_min:            18
  age_max:            null
  schedule_days:      [TUE, THU]
  schedule_start_time: "19:15"
  schedule_end_time:   "20:15"
  location_name:      Bridge City Combat
  location_address:   2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bridge City Combat
  contact_phone:      (928) 716-3009
  contact_email:      bridgecitycombat@gmail.com
  contact_url:        instagram.com/bridgecitycombat
  description:        MMA training covering boxing, wrestling, Jiu-Jitsu,
                      and kickboxing. Team competes in amateur MMA events.

- title:              Open Mat
  activity_category:  martial_arts
  age_min:            null
  age_max:            null
  schedule_days:      [FRI]
  schedule_start_time: "18:00"
  schedule_end_time:   null
  schedule_note:      "Fri 6pm to close. Weekend open mats also available — check @bridgecitycombat Instagram for dates."
  location_name:      Bridge City Combat
  location_address:   2143 McCulloch Blvd N, Unit B, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bridge City Combat
  contact_phone:      (928) 716-3009
  contact_email:      bridgecitycombat@gmail.com
  contact_url:        instagram.com/bridgecitycombat
  description:        Open mat rolling session. All levels welcome.
                      Weekend open mats posted on Instagram.
```

---

## BUSINESS 5 — LAKE HAVASU CITY BMX

```
provider_name:    Lake Havasu City BMX
category:         sports / BMX racing
address:          7260 Sara Park Lane, Lake Havasu City, AZ 86406
                  (inside SARA Park — off Hwy 95 at milepost 175)
phone:            (928) 208-5388 (Kaitlyn Weber) | (928) 208-7158 (Sean Weber)
email:            ⚠️ VERIFY — partially visible as lhcbmx@[domain] in USABMX listing
website:          usabmx.com/tracks/1292
facebook:         facebook.com/LakeHavasuCityBMX
instagram:        @lhcbmx
organization:     USA BMX sanctioned non-profit, run entirely by volunteers
hours:            Tue 5–6:30pm (practice) | Wed 5–6:15pm (training) | Thu 6–7pm (practice) + 7pm racing
                  Oct–Jun schedule; Jul–Sep shifts ~1 hour later
```

### Programs

```yaml
- title:              BMX Racing — Race Night
  activity_category:  sports
  age_min:            5
  age_max:            null
  schedule_days:      [THU]
  schedule_start_time: "18:00"
  schedule_end_time:   "21:00"
  schedule_note:      "Registration 6–7pm. Racing starts 7pm. Oct–Jun schedule."
  location_name:      SARA Park BMX Track
  location_address:   7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:               10.00
  cost_description:   "$10/race. USA BMX annual membership required: $80/year (1st rider). 1-day free trial available."
  provider_name:      Lake Havasu City BMX
  contact_phone:      (928) 208-5388
  contact_url:        usabmx.com/tracks/1292
  description:        >
    USA BMX-sanctioned race night. All ages and skill levels. Quarter-mile
    dirt track with paved start hill. Spectators free. Loaner bikes and
    helmets available for first-timers. USA BMX membership required ($80/yr).
    30-day trial memberships also available.

- title:              BMX Practice — Tuesday
  activity_category:  sports
  age_min:            5
  age_max:            null
  schedule_days:      [TUE]
  schedule_start_time: "17:00"
  schedule_end_time:   "18:30"
  schedule_note:      "Striders ride free on practice nights."
  location_name:      SARA Park BMX Track
  location_address:   7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:               5.00
  cost_description:   "$5/practice. Striders free."
  provider_name:      Lake Havasu City BMX
  contact_phone:      (928) 208-5388
  contact_url:        usabmx.com/tracks/1292
  description:        Open practice night. All skill levels welcome.

- title:              BMX Training — Wednesday
  activity_category:  sports
  age_min:            5
  age_max:            null
  schedule_days:      [WED]
  schedule_start_time: "17:00"
  schedule_end_time:   "18:15"
  location_name:      SARA Park BMX Track
  location_address:   7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:               5.00
  cost_description:   "$5. Coaching/skills-focused session."
  provider_name:      Lake Havasu City BMX
  contact_phone:      (928) 208-5388
  contact_url:        usabmx.com/tracks/1292
  description:        Coached training session focused on skills development.

- title:              Strider/Balance Bike Track (Patrick Tinnell Balance Bike Track)
  activity_category:  sports
  age_min:            1
  age_max:            5
  schedule_days:      [TUE, THU]
  schedule_start_time: "17:00"
  schedule_end_time:   "21:00"
  schedule_note:      "Available on all race/practice nights alongside main track."
  location_name:      SARA Park BMX Track — Strider Track
  location_address:   7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:               5.00
  cost_description:   "$5/race. Annual membership $30/year."
  provider_name:      Lake Havasu City BMX
  contact_phone:      (928) 208-5388
  contact_url:        usabmx.com/tracks/1292
  description:        >
    Dedicated smaller track for youngest riders (ages 1–5) on balance bikes.
    Built in honor of Patrick Tinnell. Separate gate from main track.
    Annual membership $30/year.
```

### Events

```yaml
- title:       Local BMX Race
  description: Weekly USA BMX-sanctioned local race. Registration 6–7pm, racing starts ASAP after.
               All ages and skill levels. $10 to race. Spectators free.
  date:        2026-04-14
  time:        "18:00"
  location:    SARA Park BMX Track, 7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:        10.00
  provider:    Lake Havasu City BMX

- title:       Local BMX Race
  description: Weekly USA BMX-sanctioned local race.
  date:        2026-04-16
  time:        "18:00"
  location:    SARA Park BMX Track, 7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:        10.00
  provider:    Lake Havasu City BMX

- title:       Local BMX Race
  description: Weekly USA BMX-sanctioned local race.
  date:        2026-04-21
  time:        "18:00"
  location:    SARA Park BMX Track, 7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:        10.00
  provider:    Lake Havasu City BMX

- title:       Local BMX Race
  description: Weekly USA BMX-sanctioned local race.
  date:        2026-04-23
  time:        "18:00"
  location:    SARA Park BMX Track, 7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:        10.00
  provider:    Lake Havasu City BMX

- title:       Local BMX Race
  description: Weekly USA BMX-sanctioned local race.
  date:        2026-04-28
  time:        "18:00"
  location:    SARA Park BMX Track, 7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:        10.00
  provider:    Lake Havasu City BMX

- title:       Local BMX Race
  description: Weekly USA BMX-sanctioned local race.
  date:        2026-04-30
  time:        "18:00"
  location:    SARA Park BMX Track, 7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:        10.00
  provider:    Lake Havasu City BMX
```

---

## BUSINESS 6 — LAKE HAVASU MOUNTAIN BIKE CLUB

```
provider_name:    Lake Havasu Mountain Bike Club
category:         sports / cycling
address:          null — no physical office; practices at Sara Park & Rotary Park
phone:            (619) 823-5088 (Coach Lu Lastra)
email:            leaderunlimited@gmail.com
website:          null
facebook:         facebook.com/groups/LakeHavasuMountainBikeTeam
organization:     501(c)3 nonprofit, volunteer-run
coach:            Lu Lastra (Master Chief SEAL, Ret.)
board:            Maureen Lastra (Admin), Mike Slettebo
notes:            NO membership fees. Loaner bikes available for first few practices.
                  Race season January–May. Racing is optional, not required.
                  Monday practices run through May 2026.
```

### Programs

```yaml
- title:              Mountain Bike Practice — Sara Park (Sunday)
  activity_category:  sports
  age_min:            4
  age_max:            null
  schedule_days:      [SUN]
  schedule_start_time: "09:00"
  schedule_end_time:   "10:30"
  location_name:      Sara Park
  location_address:   7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:               0.00
  cost_description:   "Free — no membership fees. Bring your own bike; loaner available for first few practices."
  provider_name:      Lake Havasu Mountain Bike Club
  contact_phone:      (619) 823-5088
  contact_email:      leaderunlimited@gmail.com
  contact_url:        facebook.com/groups/LakeHavasuMountainBikeTeam
  description:        >
    Dirt trail riding at Sara Park. More challenging terrain.
    Safety-focused crawl/walk/run progression. Minors must have
    parent ride along initially until safe skills are established.

- title:              Mountain Bike Practice — Sara Park (Monday)
  activity_category:  sports
  age_min:            4
  age_max:            null
  schedule_days:      [MON]
  schedule_start_time: "16:30"
  schedule_end_time:   "18:00"
  schedule_note:      "Race practices run through May 2026. Summer schedule TBD."
  location_name:      Sara Park
  location_address:   7260 Sara Park Lane, Lake Havasu City, AZ 86406
  cost:               0.00
  cost_description:   "Free"
  provider_name:      Lake Havasu Mountain Bike Club
  contact_phone:      (619) 823-5088
  contact_email:      leaderunlimited@gmail.com
  contact_url:        facebook.com/groups/LakeHavasuMountainBikeTeam
  description:        Race practice session at Sara Park dirt trails.

- title:              Mountain Bike Practice — Rotary Park (Wednesday)
  activity_category:  sports
  age_min:            4
  age_max:            null
  schedule_days:      [WED]
  schedule_start_time: "16:30"
  schedule_end_time:   "18:00"
  location_name:      Rotary Park
  location_address:   Rotary Park, Lake Havasu City, AZ
  cost:               0.00
  cost_description:   "Free — best session for newcomers to check out the program."
  provider_name:      Lake Havasu Mountain Bike Club
  contact_phone:      (619) 823-5088
  contact_email:      leaderunlimited@gmail.com
  contact_url:        facebook.com/groups/LakeHavasuMountainBikeTeam
  description:        >
    Non-technical road/path ride. Best session for new riders to evaluate
    fitness and skill level. Great intro to the club. Parents welcome.
```

---

## BUSINESS 7 — UNIVERSAL GYMNASTICS AND ALL STAR CHEER (SONICS)

```
provider_name:    Universal Gymnastics and All Star Cheer — Sonics
category:         gymnastics / cheer / tumbling
address:          2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
phone:            (928) 453-1313
email:            havasusonics@gmail.com
website:          universalgymnasticslakehavasu.com
facebook:         facebook.com/universalsonics
hours:            Mon–Thu 3–9pm | Fri 3–6:30pm | Sat–Sun Closed
notes:            40+ years serving LHC. USA Gymnastics & USASF Certified.
                  All Star Cheer 2026–2027 Season registration open.
                  Team placements begin May 17, 2026.
```

### Programs

```yaml
- title:              Gym Tots
  activity_category:  gymnastics
  age_min:            0.5
  age_max:            3
  schedule_days:      [THU]
  schedule_start_time: "17:30"
  schedule_end_time:   "18:00"
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  contact_email:      havasusonics@gmail.com
  contact_url:        universalgymnasticslakehavasu.com
  description:        Parent-participation class for babies and toddlers 6 months–3 years.

- title:              Tiny Tumblers
  activity_category:  gymnastics
  age_min:            3
  age_max:            4
  schedule_days:      [TUE, WED, THU]
  schedule_note:      "Tue 4:30–5:15pm & 5:30–6:15pm | Wed 5:30–6:15pm | Thu 6:00–6:45pm"
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  contact_email:      havasusonics@gmail.com
  contact_url:        universalgymnasticslakehavasu.com
  description:        Beginning gymnastics and tumbling for ages 3–4.

- title:              Recreational Gymnastics (Ages 5–9)
  activity_category:  gymnastics
  age_min:            5
  age_max:            9
  schedule_days:      [MON, TUE, WED, THU]
  schedule_note:      "Mon 4–5pm | Tue 4:30–5:30pm | Wed 4–5pm | Thu 4:30–5:30pm"
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  contact_email:      havasusonics@gmail.com
  contact_url:        universalgymnasticslakehavasu.com
  description:        Recreational gymnastics for school-age kids.

- title:              Recreational Tumbling Level 1/2/3
  activity_category:  gymnastics
  age_min:            8
  age_max:            null
  schedule_days:      [TUE]
  schedule_start_time: "17:30"
  schedule_end_time:   "18:30"
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  contact_email:      havasusonics@gmail.com
  contact_url:        universalgymnasticslakehavasu.com
  description:        Tumbling class for ages 8+. Three levels offered.

- title:              Recreational Cheer
  activity_category:  cheer
  age_min:            5
  age_max:            null
  schedule_days:      [THU]
  schedule_start_time: "15:30"
  schedule_end_time:   "16:30"
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  contact_email:      havasusonics@gmail.com
  contact_url:        universalgymnasticslakehavasu.com
  description:        Recreational cheerleading for ages 5 and up.

- title:              Boys Athletics (Ages 5–10)
  activity_category:  sports
  age_min:            5
  age_max:            10
  schedule_days:      [TUE]
  schedule_start_time: "15:30"
  schedule_end_time:   "16:30"
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  contact_email:      havasusonics@gmail.com
  contact_url:        universalgymnasticslakehavasu.com
  description:        Athletic conditioning and gymnastics-based training for boys ages 5–10.

- title:              Sonics Competitive Gymnastics
  activity_category:  gymnastics
  age_min:            null
  age_max:            null
  schedule_days:      [MON, WED, THU, FRI]
  schedule_note:      "Mon & Wed 4–8pm | Thu 5–7pm | Fri 3:15–6:15pm. Invite/tryout level."
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  contact_email:      havasusonics@gmail.com
  contact_url:        universalgymnasticslakehavasu.com
  description:        High-level competitive gymnastics training. Invite or tryout required.

- title:              Sonics All Star Cheer — All Teams (2026–2027 Season)
  activity_category:  cheer
  age_min:            4
  age_max:            18
  schedule_note:      >
    Multiple teams: Mini Militia, Flight Class, Youth Ignite, Tiny Rebels,
    Junior Commanders, Senior Blitz, Senior Bombshells.
    Full schedule at universalgymnasticslakehavasu.com.
    Team placements begin May 17, 2026.
  location_name:      Universal Gymnastics and All Star Cheer
  location_address:   2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Universal Gymnastics and All Star Cheer
  contact_phone:      (928) 453-1313
  contact_email:      havasusonics@gmail.com
  contact_url:        universalgymnasticslakehavasu.com
  description:        >
    Competitive All Star Cheer teams for ages 4–18. No experience needed
    for new season. Competes at regional and national competitions.
    2026–2027 registration now open. Team placements begin May 17, 2026.
```

### Events

```yaml
- title:       Sonics All Star Cheer 2026–2027 Season — Team Placements
  description: Team placement tryouts for the 2026–2027 All Star Cheer season.
               No experience needed. Ages 4–18.
  date:        2026-05-17
  time:        "TBD — contact gym"
  location:    Universal Gymnastics and All Star Cheer, 2245 N. Kiowa Blvd #102, Lake Havasu City, AZ 86403
  cost:        CONTACT_FOR_PRICING
  provider:    Universal Gymnastics and All Star Cheer
```

---

## BUSINESS 8 — ARIZONA COAST PERFORMING ARTS (ACPA)

```
provider_name:    Arizona Coast Performing Arts (ACPA)
category:         dance
address:          3476 McCulloch Blvd, Lake Havasu City, AZ 86404
phone:            (928) 208-2273
email:            arizonacoastperformingarts@gmail.com
website:          arizonacoastperformingarts.com
facebook:         facebook.com/graceartslive
season:           August–May
notes:            31 years in business. Female-owned. Max 16 students per class.
                  Full Tue–Thu schedule at arizonacoastperformingarts.com.
```

### Programs

```yaml
- title:              Fine Arts Club (Ages 3–5)
  activity_category:  dance
  age_min:            3
  age_max:            5
  schedule_days:      [MON, TUE, WED]
  schedule_start_time: "12:00"
  schedule_end_time:   "14:00"
  location_name:      Arizona Coast Performing Arts at Grace Arts Live
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  contact_email:      arizonacoastperformingarts@gmail.com
  contact_url:        arizonacoastperformingarts.com
  description:        All-inclusive performing arts program for young children.

- title:              Ballet (Levels 1–6)
  activity_category:  dance
  age_min:            5
  age_max:            null
  schedule_days:      [MON, TUE, WED, THU]
  schedule_note:      "Mon 3:30–4:30pm confirmed. Full Tue–Thu schedule at arizonacoastperformingarts.com"
  location_name:      Arizona Coast Performing Arts at Grace Arts Live
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  contact_email:      arizonacoastperformingarts@gmail.com
  contact_url:        arizonacoastperformingarts.com
  description:        >
    Classical ballet instruction. Levels 1–6.
    Level 6 by invitation only — prospective students must be evaluated.
    Ballet 6 meets for 2 mandatory 90-minute classes per week.

- title:              Jazz (Levels 1–6)
  activity_category:  dance
  age_min:            5
  age_max:            null
  schedule_note:      "Mon 4:30–5:30pm confirmed. Full schedule at arizonacoastperformingarts.com"
  location_name:      Arizona Coast Performing Arts at Grace Arts Live
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  contact_email:      arizonacoastperformingarts@gmail.com
  contact_url:        arizonacoastperformingarts.com
  description:        Jazz dance. Multiple levels. Upbeat technique and choreography.

- title:              Tap (Levels 1–6)
  activity_category:  dance
  age_min:            5
  age_max:            null
  schedule_note:      "Tue/Thu schedule at arizonacoastperformingarts.com"
  location_name:      Arizona Coast Performing Arts at Grace Arts Live
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  contact_email:      arizonacoastperformingarts@gmail.com
  contact_url:        arizonacoastperformingarts.com
  description:        Tap dance. Levels 1–6, timing, musicality, and rhythm.

- title:              Contemporary Dance
  activity_category:  dance
  age_min:            null
  age_max:            null
  schedule_note:      "Mon 5:30–6:30pm (Int.) confirmed. Full schedule at arizonacoastperformingarts.com"
  location_name:      Arizona Coast Performing Arts at Grace Arts Live
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  contact_email:      arizonacoastperformingarts@gmail.com
  contact_url:        arizonacoastperformingarts.com
  description:        Contemporary/modern dance. Ballet prerequisite required.

- title:              Hip Hop
  activity_category:  dance
  age_min:            null
  age_max:            null
  schedule_note:      "Mon 6:30–7:30pm (Adv.) confirmed. See arizonacoastperformingarts.com."
  location_name:      Arizona Coast Performing Arts at Grace Arts Live
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  contact_email:      arizonacoastperformingarts@gmail.com
  contact_url:        arizonacoastperformingarts.com
  description:        Hip hop and street dance. Multiple levels.

- title:              Musical Theatre
  activity_category:  dance
  age_min:            null
  age_max:            null
  schedule_note:      "Wed 3:30–4:30pm (Beg/Int) confirmed. See arizonacoastperformingarts.com."
  location_name:      Arizona Coast Performing Arts at Grace Arts Live
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  contact_email:      arizonacoastperformingarts@gmail.com
  contact_url:        arizonacoastperformingarts.com
  description:        Musical theatre dance combining acting, singing, and movement.

- title:              Pointe
  activity_category:  dance
  age_min:            null
  age_max:            null
  schedule_note:      "Advanced students only. See arizonacoastperformingarts.com."
  location_name:      Arizona Coast Performing Arts at Grace Arts Live
  location_address:   3476 McCulloch Blvd, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Arizona Coast Performing Arts
  contact_phone:      (928) 208-2273
  contact_email:      arizonacoastperformingarts@gmail.com
  contact_url:        arizonacoastperformingarts.com
  description:        Classical pointe work for advanced ballet students.
```

### Events

```yaml
- title:       ACPA Annual Dance Showcase 2026
  description: Year-end student showcase featuring Ballet, Jazz, Tap,
               Contemporary, Pointe, and Musical Theatre performances.
  date:        "2026-05-15 through 2026-05-17"
  time:        "Fri, Sat & Sun — times TBD"
  location:    ⚠️ VERIFY venue
  cost:        CONTACT_FOR_PRICING
  provider:    Arizona Coast Performing Arts
```

---

## BUSINESS 9 — GRACE ARTS LIVE (YOUTH THEATRE)

```
provider_name:    Grace Arts Live
category:         theatre / performing arts
address:          2146 McCulloch Blvd N, Lake Havasu City, AZ 86403
website:          graceartslive.com
facebook:         facebook.com/graceartslive
established:      2006
notes:            Nonprofit. Affiliated with ACPA dance studio.
```

### Programs

```yaml
- title:              Storybook Theatre Youth Workshop
  activity_category:  theatre
  age_min:            5
  age_max:            14
  schedule_note:      "Annual summer workshop. 2026 production: Alice in Wonderland Jr. See graceartslive.com."
  location_name:      Grace Arts Live
  location_address:   2146 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Grace Arts Live
  contact_url:        graceartslive.com
  description:        Annual summer youth theatre production. Grades K–8.
                      Students rehearse and perform a full musical production.
                      2026 show: Alice in Wonderland Jr.
```

### Events

```yaml
- title:       Alice in Wonderland Jr. — Storybook Theatre 2026
  description: GraceArts LIVE Youth Theatricals student production.
               Family-friendly musical featuring local youth performers.
  date:        2026-06-26
  time:        "19:30"
  location:    Grace Arts Live, 2146 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:        CONTACT_FOR_PRICING
  provider:    Grace Arts Live

- title:       Alice in Wonderland Jr. — Storybook Theatre 2026
  description: GraceArts LIVE Youth Theatricals student production.
  date:        2026-06-27
  time:        "19:30"
  location:    Grace Arts Live, 2146 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:        CONTACT_FOR_PRICING
  provider:    Grace Arts Live

- title:       Alice in Wonderland Jr. — Storybook Theatre 2026
  description: GraceArts LIVE Youth Theatricals student production. Matinee.
  date:        2026-06-28
  time:        "14:00"
  location:    Grace Arts Live, 2146 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:        CONTACT_FOR_PRICING
  provider:    Grace Arts Live
```

---

## BUSINESS 10 — FOOTLITE SCHOOL OF DANCE

```
provider_name:    Footlite School of Dance
category:         dance
address:          2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
phone:            (928) 854-4328
email:            footliteschool@gmail.com
website:          footliteschoolofdance.com
facebook:         facebook.com/footliteschoolofdance
instagram:        @footlite_dance
hours:            Mon–Thu 3–7pm during dance year
```

### Programs

```yaml
- title:              Pre-K Dance (Ages 3–4)
  activity_category:  dance
  age_min:            3
  age_max:            4
  schedule_note:      "See footliteschoolofdance.com for current schedule."
  location_name:      Footlite School of Dance
  location_address:   2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Footlite School of Dance
  contact_phone:      (928) 854-4328
  contact_email:      footliteschool@gmail.com
  contact_url:        footliteschoolofdance.com
  description:        Introduction to dance for preschoolers. Ballet and tap foundations
                      through imaginative movement and play.

- title:              Combo Ballet/Tap (Ages 4–5)
  activity_category:  dance
  age_min:            4
  age_max:            5
  schedule_note:      "See footliteschoolofdance.com for current schedule."
  location_name:      Footlite School of Dance
  location_address:   2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Footlite School of Dance
  contact_phone:      (928) 854-4328
  contact_email:      footliteschool@gmail.com
  contact_url:        footliteschoolofdance.com
  description:        Ballet and tap combo. Foundational positions, coordination,
                      and motor skills development.

- title:              Mini Groovers (Ages 5–7)
  activity_category:  dance
  age_min:            5
  age_max:            7
  schedule_note:      "See footliteschoolofdance.com."
  location_name:      Footlite School of Dance
  location_address:   2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Footlite School of Dance
  contact_phone:      (928) 854-4328
  contact_email:      footliteschool@gmail.com
  contact_url:        footliteschoolofdance.com
  description:        Tap-based class sampling hip-hop, musical theatre, and movement.

- title:              Ballet (Levels 1–4+)
  activity_category:  dance
  age_min:            6
  age_max:            null
  schedule_note:      "See footliteschoolofdance.com for schedule."
  location_name:      Footlite School of Dance
  location_address:   2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Footlite School of Dance
  contact_phone:      (928) 854-4328
  contact_email:      footliteschool@gmail.com
  contact_url:        footliteschoolofdance.com
  description:        Classical ballet. Multiple levels.

- title:              Jazz (Levels 1–3)
  activity_category:  dance
  age_min:            6
  age_max:            null
  schedule_note:      "Level 3 advanced: ages 13+."
  location_name:      Footlite School of Dance
  location_address:   2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Footlite School of Dance
  contact_phone:      (928) 854-4328
  contact_email:      footliteschool@gmail.com
  contact_url:        footliteschoolofdance.com
  description:        Upbeat jazz technique. Three progressive levels.

- title:              Hip Hop
  activity_category:  dance
  age_min:            6
  age_max:            null
  schedule_note:      "See footliteschoolofdance.com."
  location_name:      Footlite School of Dance
  location_address:   2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Footlite School of Dance
  contact_phone:      (928) 854-4328
  contact_email:      footliteschool@gmail.com
  contact_url:        footliteschoolofdance.com
  description:        Street dance. Age-appropriate music.

- title:              Active Seniors Dance & Fitness
  activity_category:  fitness
  age_min:            55
  age_max:            null
  schedule_note:      "See footliteschoolofdance.com."
  location_name:      Footlite School of Dance
  location_address:   2168 McCulloch Blvd N #104, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Footlite School of Dance
  contact_phone:      (928) 854-4328
  contact_email:      footliteschool@gmail.com
  contact_url:        footliteschoolofdance.com
  description:        Low-impact fitness combining dance routines, weight work,
                      floor exercises, and balance/coordination for active seniors.
```

### Events

```yaml
- title:       Footlite Annual Recital — "Dance Party in the USA!"
  description: Footlite School of Dance year-end recital showcasing all levels and styles.
  date:        2026-05-30
  time:        "TBD"
  location:    Lake Havasu High School Performing Arts Center, 2675 Palo Verde Blvd S, Lake Havasu City, AZ 86403
  cost:        25.00
  cost_description: "$25 center section."
  provider:    Footlite School of Dance

- title:       Footlite Annual Recital — "Dance Party in the USA!"
  description: Footlite School of Dance year-end recital showcasing all levels and styles.
  date:        2026-06-01
  time:        "TBD"
  location:    Lake Havasu High School Performing Arts Center, 2675 Palo Verde Blvd S, Lake Havasu City, AZ 86403
  cost:        25.00
  cost_description: "$25 center section."
  provider:    Footlite School of Dance
```

---

## BUSINESS 11 — FLIPS FOR FUN GYMNASTICS

```
provider_name:    Flips for Fun Gymnastics
category:         gymnastics
address:          955 Kiowa Ave, Lake Havasu City, AZ 86404
phone:            (928) 566-8862
email:            Flips4fungymnastics@gmail.com
website:          fffhavasu.com
hours:            Opens 3pm, closes 8pm (Mon–Fri approx.)
organization:     Non-profit private foundation for amateur sports
notes:            Classes from 6 months to adult. Recreational and competitive.
                  Full schedule at fffhavasu.com. Birthday parties available.
```

### Programs

```yaml
- title:              Recreational Gymnastics (All Ages)
  activity_category:  gymnastics
  age_min:            0.5
  age_max:            null
  schedule_note:      "Full schedule at fffhavasu.com. Classes weekdays and weekends."
  location_name:      Flips for Fun Gymnastics
  location_address:   955 Kiowa Ave, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Flips for Fun Gymnastics
  contact_phone:      (928) 566-8862
  contact_email:      Flips4fungymnastics@gmail.com
  contact_url:        fffhavasu.com
  description:        Recreational gymnastics classes for ages 6 months to adult.
                      Annual registration fee applies.

- title:              Competitive Gymnastics
  activity_category:  gymnastics
  age_min:            null
  age_max:            null
  schedule_note:      "Schedule at fffhavasu.com."
  location_name:      Flips for Fun Gymnastics
  location_address:   955 Kiowa Ave, Lake Havasu City, AZ 86404
  cost:               CONTACT_FOR_PRICING
  provider_name:      Flips for Fun Gymnastics
  contact_phone:      (928) 566-8862
  contact_email:      Flips4fungymnastics@gmail.com
  contact_url:        fffhavasu.com
  description:        Competitive gymnastics program. Contact gym for tryout information.
```

---

## BUSINESS 12 — LAKE HAVASU CITY AQUATIC CENTER

```
provider_name:    Lake Havasu City Aquatic Center
category:         swim / fitness
address:          100 Park Ave, Lake Havasu City, AZ 86403
phone:            (928) 453-8686
website:          lhcaz.gov/parks-recreation/aquatic-center
registration:     register.lhcaz.gov
notes:            Indoor facility. Olympic-size pool, wave pool, water slide,
                  hot tubs, kiddie lagoon, splash pad. Year-round programming.
```

### Programs

```yaml
- title:              Lap Swim
  activity_category:  swim
  age_min:            null
  age_max:            null
  schedule_note:      "See lhcaz.gov/parks-recreation/open-swim-schedule for monthly schedule."
  location_name:      Lake Havasu City Aquatic Center
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               5.00
  cost_description:   "$5 drop-in. Monthly passes available."
  provider_name:      Lake Havasu City Aquatic Center
  contact_phone:      (928) 453-8686
  contact_url:        lhcaz.gov/parks-recreation/aquatic-center
  description:        6-lane 25-meter heated indoor pool. Kickboards and fins
                      available first-come, first-served.

- title:              Open Swim
  activity_category:  swim
  age_min:            null
  age_max:            null
  schedule_note:      "Saturdays year-round + additional days June–July. See monthly schedule."
  location_name:      Lake Havasu City Aquatic Center
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               null
  cost_description:   "$6 adults | $3 seniors & children | Free under 3"
  provider_name:      Lake Havasu City Aquatic Center
  contact_phone:      (928) 453-8686
  contact_url:        lhcaz.gov/parks-recreation/aquatic-center
  description:        Wave pool, water slide, kiddie lagoon, splash pad, and hot tubs.
                      Saturdays year-round. More days in June–July.

- title:              Children's Swim Lessons
  activity_category:  swim
  age_min:            0.5
  age_max:            9
  schedule_days:      [MON, TUE, WED, THU]
  schedule_note:      "Summer sessions. 2-week blocks June 2–July 31. ⚠️ Confirm 2026 pricing."
  location_name:      Lake Havasu City Aquatic Center
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               37.00
  cost_description:   "$37 per child per 2-week session. ⚠️ Confirm current pricing."
  provider_name:      Lake Havasu City Aquatic Center
  contact_phone:      (928) 453-8686
  contact_url:        lhcaz.gov/parks-recreation/aquatic-center
  description:        Certified instructors. Skill-level based classes. Evening sessions
                      Mon–Thu in 2-week blocks.

- title:              Aqua Aerobics / Water Fitness
  activity_category:  fitness
  age_min:            18
  age_max:            null
  schedule_note:      "Multiple class types. See monthly schedule at lhcaz.gov."
  location_name:      Lake Havasu City Aquatic Center
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               5.00
  cost_description:   "$5 drop-in per class."
  provider_name:      Lake Havasu City Aquatic Center
  contact_phone:      (928) 453-8686
  contact_url:        lhcaz.gov/parks-recreation/open-swim-schedule
  description:        >
    Year-round adult water fitness. Classes include Aqua Aerobics, Ai-Chi,
    Arthritis Exercise, Cardio Challenge, and Aqua Motion.
```

---

## BUSINESS 13 — BLESS THIS NEST LHC

```
provider_name:    Bless This Nest LHC
category:         art / crafts
address:          2886 Sweetwater Ave, Suite B-108, Lake Havasu City, AZ 86406
phone:            (928) 412-3718
email:            amber@blessthisnestlhc.com
website:          blessthisnestlhc.com
facebook:         facebook.com/blessthisnestlhc
instagram:        @blessthisnestlhc
owner:            Amber Kramer Lohrman
```

### Programs

```yaml
- title:              Open Studio / Drop-In Crafts
  activity_category:  art
  age_min:            null
  age_max:            null
  schedule_note:      "See blessthisnestlhc.com for current calendar."
  location_name:      Bless This Nest LHC
  location_address:   2886 Sweetwater Ave, Suite B-108, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  cost_description:   "Price varies by project."
  provider_name:      Bless This Nest LHC
  contact_phone:      (928) 412-3718
  contact_email:      amber@blessthisnestlhc.com
  contact_url:        blessthisnestlhc.com
  description:        Pick-your-project drop-in creative time. Wood signs, painting,
                      resin, seasonal crafts, and more. No experience needed.

- title:              Kids Art Club
  activity_category:  art
  age_min:            null
  age_max:            17
  schedule_note:      "See blessthisnestlhc.com."
  location_name:      Bless This Nest LHC
  location_address:   2886 Sweetwater Ave, Suite B-108, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bless This Nest LHC
  contact_phone:      (928) 412-3718
  contact_email:      amber@blessthisnestlhc.com
  contact_url:        blessthisnestlhc.com
  description:        Guided art club sessions for kids.

- title:              Toddler Time
  activity_category:  art
  age_min:            1.5
  age_max:            5
  schedule_note:      "See blessthisnestlhc.com."
  location_name:      Bless This Nest LHC
  location_address:   2886 Sweetwater Ave, Suite B-108, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bless This Nest LHC
  contact_phone:      (928) 412-3718
  contact_email:      amber@blessthisnestlhc.com
  contact_url:        blessthisnestlhc.com
  description:        Art and craft sessions designed for toddlers.

- title:              Summer Camps — Art
  activity_category:  summer_camp
  age_min:            null
  age_max:            17
  schedule_note:      "Summer only. Dates and pricing at blessthisnestlhc.com."
  location_name:      Bless This Nest LHC
  location_address:   2886 Sweetwater Ave, Suite B-108, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Bless This Nest LHC
  contact_phone:      (928) 412-3718
  contact_email:      amber@blessthisnestlhc.com
  contact_url:        blessthisnestlhc.com
  description:        Summer art camps for youth.
```

---

## BUSINESS 14 — HAVASU LIONS FC (SOCCER)

```
provider_name:    Havasu Lions FC
category:         sports / soccer
address:          P.O. Box 1749, Lake Havasu City, AZ 86405
email:            bkistler@havasulions.com (League Registrar)
website:          havasulions.com
facebook:         facebook.com/havasulions
registration:     GotSport app
organization:     501(c)3 nonprofit
notes:            1,000+ rec players. Scholarship program available.
```

### Programs

```yaml
- title:              Recreational Soccer — Spring Season
  activity_category:  sports
  age_min:            4
  age_max:            17
  schedule_note:      "Spring 2026 registration open. Games on Saturdays. Practices weeknights by coach."
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Lions FC
  contact_email:      bkistler@havasulions.com
  contact_url:        havasulions.com/rec-league
  description:        Youth recreational soccer ages 4–17. Divided by birth year.
                      Scholarship program available for families in need.

- title:              Recreational Soccer — Fall Season
  activity_category:  sports
  age_min:            4
  age_max:            17
  schedule_note:      >
    Fall 2025 pattern: Practices begin ~Sept 22.
    Saturday games Oct–Dec. Playoffs + All-Star + Coach Cup in Dec.
    Registration opens ~August.
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Lions FC
  contact_email:      bkistler@havasulions.com
  contact_url:        havasulions.com/rec-league
  description:        Youth recreational soccer fall season. End-of-season playoffs
                      and All-Star game for U10 and older.

- title:              Travel / Club League (Competitive)
  activity_category:  sports
  age_min:            8
  age_max:            17
  schedule_note:      "Travel to Phoenix, Flagstaff, Las Vegas, Southern California. Tryout required."
  location_name:      Various locations (travel)
  location_address:   Lake Havasu City, AZ (home base)
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Lions FC
  contact_email:      bkistler@havasulions.com
  contact_url:        havasulions.com/club-league
  description:        Competitive travel soccer ages 8–17. Higher commitment level.
                      Teams compete regionally. Tryout/selection required.
```

---

## BUSINESS 15 — HAVASU STINGRAYS SWIM TEAM

```
provider_name:    Havasu Stingrays Swim Team
category:         swim / competitive
address:          P.O. Box 3802, Lake Havasu City, AZ 86405
email:            membership@havasustingrays.com  ⚠️ VERIFY domain
website:          gomotionapp.com/team/azhsaz
facebook:         facebook.com/HavasuStingrays
instagram:        @havasustingrays
organization:     USA Swimming sanctioned nonprofit. Est. 1990.
tryout:           Required. Must swim 25m independently without stopping.
```

### Programs

```yaml
- title:              Competitive Swim Team
  activity_category:  swim
  age_min:            5
  age_max:            18
  schedule_note:      "Year-round. Practice schedule provided after team placement."
  location_name:      Lake Havasu City Aquatic Center
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Stingrays Swim Team
  contact_email:      membership@havasustingrays.com
  contact_url:        gomotionapp.com/team/azhsaz/page/home
  description:        USA Swimming competitive team. Ages 5–18. Tryout required
                      (must swim 25m independently). Competes in AZ Swimming meets.
```

---

## BUSINESS 16 — AQUA BEGINNINGS (PRIVATE SWIM LESSONS)

```
provider_name:    Aqua Beginnings
category:         swim / lessons
address:          Private heated outdoor pool (address provided upon booking)
website:          aquabeginnings.com
coach:            Coach Rick (Swim America® certified)
notes:            Max 3 swimmers per group. Free initial skills assessment.
```

### Programs

```yaml
- title:              Private & Small-Group Swim Lessons
  activity_category:  swim
  age_min:            null
  age_max:            null
  schedule_days:      [TUE, WED, FRI]
  schedule_start_time: "08:00"
  schedule_end_time:   "14:00"
  schedule_note:      "Assessment hours Tue/Wed/Fri 8am–2pm. Other times by arrangement."
  location_name:      Aqua Beginnings (private outdoor pool)
  location_address:   Lake Havasu City, AZ (address provided at booking)
  cost:               CONTACT_FOR_PRICING
  provider_name:      Aqua Beginnings
  contact_url:        aquabeginnings.com
  description:        >
    One-on-one and small-group lessons (max 3) in a private heated outdoor pool.
    Modified Swim America® progression. Free initial skills assessment.
    All ages and abilities. Ideal for Lake Havasu boating families.
```

---

## BUSINESS 17 — LAKE HAVASU LITTLE LEAGUE

```
provider_name:    Lake Havasu Little League
category:         sports / baseball
address:          1990 McCulloch Blvd N, Ste 373, Lake Havasu City, AZ 86403
email:            info@lakehavasulittleleague.net
website:          lakehavasulittleleague.net
facebook:         facebook.com/lakehavasulittleleague
season:           Spring only. Registration Nov–Jan. Practices Feb. Games Mar–May.
notes:            2026 Opening Day: Feb 28. Various local fields.
```

### Programs

```yaml
- title:              Tee Ball
  activity_category:  sports
  age_min:            4
  age_max:            5
  schedule_note:      "Spring season. Games Mar–May."
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Little League
  contact_email:      info@lakehavasulittleleague.net
  contact_url:        lakehavasulittleleague.net
  description:        Hits off tee. Safety ball. 50-foot bases.

- title:              A Minor (Machine Pitch)
  activity_category:  sports
  age_min:            5
  age_max:            6
  schedule_note:      "Spring season."
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Little League
  contact_email:      info@lakehavasulittleleague.net
  contact_url:        lakehavasulittleleague.net
  description:        Pitching machine. Safety ball. 50-foot bases. 7 pitches per at-bat.

- title:              AA Minor (Machine & Player Pitch)
  activity_category:  sports
  age_min:            7
  age_max:            8
  schedule_note:      "Spring season."
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Little League
  contact_email:      info@lakehavasulittleleague.net
  contact_url:        lakehavasulittleleague.net
  description:        Regulation baseball. 60-foot bases. Machine pitch first half,
                      player pitch second half.

- title:              AAA Minor
  activity_category:  sports
  age_min:            9
  age_max:            10
  schedule_note:      "8-year-olds may play pending tryout."
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Little League
  contact_email:      info@lakehavasulittleleague.net
  contact_url:        lakehavasulittleleague.net
  description:        Player pitch. Full regulation baseball.

- title:              Majors Division
  activity_category:  sports
  age_min:            11
  age_max:            12
  schedule_note:      "10-year-olds may play pending tryout."
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Little League
  contact_email:      info@lakehavasulittleleague.net
  contact_url:        lakehavasulittleleague.net
  description:        Classic Little League experience. Full regulation baseball.

- title:              Senior Division
  activity_category:  sports
  age_min:            13
  age_max:            16
  schedule_note:      "12-year-olds may play pending tryout."
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Little League
  contact_email:      info@lakehavasulittleleague.net
  contact_url:        lakehavasulittleleague.net
  description:        Full diamond dimensions for older players.
```

---

## BUSINESS 18 — HAVASU SHAO-LIN KEMPO

```
provider_name:    Havasu Shao-Lin Kempo
category:         martial arts
address:          2127 McCulloch Blvd N, Lake Havasu City, AZ 86403
phone:            (928) 680-4121
website:          shao-linkempo.com
facebook:         facebook.com/ASSKHavasu
hours:            Mon–Thu 10am–8pm | Sat 8am–2pm | Fri & Sun closed
notes:            Free trial class. Ages 4+. Established 2011.
                  Upcoming: Tournament May 18, 2026 | GrandMaster Clinic Aug 2026.
                  ⚠️ Class schedule from 2018 data — verify with (928) 680-4121.
```

### Programs

```yaml
- title:              Peewee's Group Class (Ages 3–9)
  activity_category:  martial_arts
  age_min:            3
  age_max:            9
  schedule_days:      [TUE, WED, FRI, SAT]
  schedule_note:      "⚠️ VERIFY — Tue/Wed/Fri 5:30–6:15pm | Sat 12–12:45pm (from 2018 data)"
  location_name:      Havasu Shao-Lin Kempo
  location_address:   2127 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Shao-Lin Kempo
  contact_phone:      (928) 680-4121
  contact_url:        shao-linkempo.com
  description:        Traditional Kempo for young children. Confidence and self-defense.

- title:              Kid's Group Class (Ages 10–17)
  activity_category:  martial_arts
  age_min:            10
  age_max:            17
  schedule_days:      [TUE, WED, FRI, SAT]
  schedule_note:      "⚠️ VERIFY — Tue/Wed/Fri 4–5pm | Sat 10:30–11:30am (from 2018 data)"
  location_name:      Havasu Shao-Lin Kempo
  location_address:   2127 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Shao-Lin Kempo
  contact_phone:      (928) 680-4121
  contact_url:        shao-linkempo.com
  description:        Kempo for kids and teens. Traditional foundations and self-defense.

- title:              Adult Group Class
  activity_category:  martial_arts
  age_min:            18
  age_max:            null
  schedule_days:      [TUE, WED, THU, SAT]
  schedule_note:      "⚠️ VERIFY — Tue/Thu 6:30–7:30pm | Wed 11am–12pm | Sat 9–10am (from 2018)"
  location_name:      Havasu Shao-Lin Kempo
  location_address:   2127 McCulloch Blvd N, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Shao-Lin Kempo
  contact_phone:      (928) 680-4121
  contact_url:        shao-linkempo.com
  description:        Adult Kempo/Karate, Kung Fu, Tai Chi. Private lessons by appointment.
```

### Events

```yaml
- title:       Shao-Lin Kempo Tournament
  description: Annual student competition. Call for details.
  date:        2026-05-18
  time:        "TBD"
  location:    ⚠️ VERIFY — call (928) 680-4121
  cost:        CONTACT_FOR_PRICING
  provider:    Havasu Shao-Lin Kempo

- title:       GrandMaster Pearl Clinic
  description: Annual clinic with GrandMaster Pearl. Students from Oregon and Arizona.
  date:        "August 2026 — exact date TBD"
  time:        TBD
  location:    ⚠️ VERIFY — call (928) 680-4121
  cost:        CONTACT_FOR_PRICING
  provider:    Havasu Shao-Lin Kempo
```

---

## BUSINESS 19 — BALLET HAVASU

```
provider_name:    Ballet Havasu
category:         dance / ballet
address:          2735 Maricopa Ave (inside The Dance Center), Lake Havasu City, AZ 86406
phone:            (928) 412-8208
website:          ballethavasu.org
facebook:         facebook.com/ballethavasu
registration:     dancestudio-pro.com/online/lakehavasu
notes:            First class FREE. Open enrollment. ESA accepted.
                  2025–2026 season starts August 4. Levels by ability not age.
```

### Programs

```yaml
- title:              Tiny Toes & Twirls (Ages 1.5–3)
  activity_category:  dance
  age_min:            1.5
  age_max:            3
  schedule_note:      "Parent participation encouraged. See ballethavasu.org."
  location_name:      Ballet Havasu (The Dance Center)
  location_address:   2735 Maricopa Ave, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Ballet Havasu
  contact_phone:      (928) 412-8208
  contact_url:        ballethavasu.org
  description:        Playful intro to dance for toddlers. Movement, music, coordination.
                      Parents encouraged to join.

- title:              Ballet Beginnings (Ages 3–5)
  activity_category:  dance
  age_min:            3
  age_max:            5
  schedule_note:      "First class free. See ballethavasu.org."
  location_name:      Ballet Havasu (The Dance Center)
  location_address:   2735 Maricopa Ave, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Ballet Havasu
  contact_phone:      (928) 412-8208
  contact_url:        ballethavasu.org
  description:        First ballet class. Foundational steps and positions. No parents in class.

- title:              Elementary Ballet (Levels A & B)
  activity_category:  dance
  age_min:            5
  age_max:            null
  schedule_note:      "Placement by readiness. See ballethavasu.org."
  location_name:      Ballet Havasu (The Dance Center)
  location_address:   2735 Maricopa Ave, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Ballet Havasu
  contact_phone:      (928) 412-8208
  contact_url:        ballethavasu.org
  description:        Formal ballet training. Posture, alignment, basic vocabulary.

- title:              Intermediate Ballet (Levels A & B)
  activity_category:  dance
  age_min:            null
  age_max:            null
  schedule_note:      "Placement by technique. See ballethavasu.org."
  location_name:      Ballet Havasu (The Dance Center)
  location_address:   2735 Maricopa Ave, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Ballet Havasu
  contact_phone:      (928) 412-8208
  contact_url:        ballethavasu.org
  description:        Refined technique and musicality. More complex combinations.

- title:              Advanced Ballet (Levels A & B)
  activity_category:  dance
  age_min:            null
  age_max:            null
  schedule_note:      "Placement by demonstrated technique. See ballethavasu.org."
  location_name:      Ballet Havasu (The Dance Center)
  location_address:   2735 Maricopa Ave, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  provider_name:      Ballet Havasu
  contact_phone:      (928) 412-8208
  contact_url:        ballethavasu.org
  description:        Highest level training. Advanced combinations, artistry,
                      and classical ballet performance.
```

---

## BUSINESS 20 — LHC PARKS & RECREATION — YOUTH ATHLETICS & SUMMER PROGRAMS

```
provider_name:    Lake Havasu City Parks & Recreation
category:         sports / summer_camp / fitness
address:          100 Park Ave, Lake Havasu City, AZ 86403
phone:            (928) 453-8686 (main) | (928) 854-0892 (youth athletics)
website:          lhcaz.gov/parks-recreation
registration:     register.lhcaz.gov
contact:          Brook DuBay — dubayb@lhcaz.gov (youth athletics)
```

### Programs

```yaml
- title:              NFL Flag Football League
  activity_category:  sports
  age_min:            6
  age_max:            15
  schedule_note:      "Jan 12–Mar 30, 2026 (current season). Co-ed, non-contact. Confirm dates for next cycle."
  location_name:      Various fields, Lake Havasu City
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu City Parks & Recreation
  contact_phone:      (928) 854-0892
  contact_email:      dubayb@lhcaz.gov
  contact_url:        lhcaz.gov/parks-recreation/youth-athletics
  description:        NFL-sanctioned co-ed flag football for ages 6–15. Non-contact.
                      Teamwork, skills, and fun in a safe environment.

- title:              Jr. Suns Basketball League
  activity_category:  sports
  age_min:            null
  age_max:            null
  schedule_note:      "Summer 2026. Registration details coming soon. Phoenix Suns partnership."
  location_name:      TBD
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu City Parks & Recreation
  contact_phone:      (928) 854-0892
  contact_email:      dubayb@lhcaz.gov
  contact_url:        lhcaz.gov/parks-recreation/youth-athletics
  description:        Youth basketball in partnership with Phoenix Suns Jr. Suns/Jr. Mercury.
                      Players receive official Jr. Suns jersey. Summer 2026.

- title:              Tennis Lessons (Youth)
  activity_category:  sports
  age_min:            9
  age_max:            14
  schedule_days:      [MON, WED]
  schedule_start_time: "17:30"
  schedule_end_time:   "18:30"
  schedule_note:      "3 fall sessions, $80 each (8 classes/session). ⚠️ Confirm 2026 dates."
  location_name:      Lake Havasu High School Tennis Courts
  location_address:   2675 Palo Verde Blvd S, Lake Havasu City, AZ 86403
  cost:               80.00
  cost_description:   "$80 per 8-class session. Private: $35/hr. Semi-private: $40/hr/group."
  provider_name:      Lake Havasu City Parks & Recreation
  contact_phone:      (928) 855-4744
  contact_url:        lhcaz.gov/parks-recreation/youth-athletics
  description:        Tennis fundamentals for grades 4–8. Bring own racket and tennis shoes.
                      Three fall sessions offered.

- title:              Sunshine Kids Summer Camp
  activity_category:  summer_camp
  age_min:            6
  age_max:            12
  schedule_days:      [MON, TUE, WED, THU, FRI]
  schedule_start_time: "07:30"
  schedule_end_time:   "17:30"
  schedule_note:      "June–mid July. ⚠️ Confirm 2026 exact dates. Grades K–4th."
  location_name:      Havasupai Elementary / Oro Grande Classical Academy
  location_address:   Lake Havasu City, AZ
  cost:               305.00
  cost_description:   "$305 first child | $246 additional children. Lunch provided. Scholarships available."
  provider_name:      Lake Havasu City Parks & Recreation
  contact_phone:      (928) 453-8686
  contact_url:        lhcaz.gov/parks-recreation/after-school-program-camps
  description:        Full-day summer camp grades K–4. Games, crafts, imagination play,
                      field trips. USDA lunch at no charge.

- title:              Adventure Academy Summer Camp
  activity_category:  summer_camp
  age_min:            11
  age_max:            13
  schedule_days:      [MON, TUE, WED, THU, FRI]
  schedule_start_time: "07:30"
  schedule_end_time:   "17:30"
  schedule_note:      "June–mid July. ⚠️ Confirm 2026 dates. Grades 5th–7th."
  location_name:      TBD
  location_address:   Lake Havasu City, AZ
  cost:               305.00
  cost_description:   "$305 first child | $246 additional. Lunch provided."
  provider_name:      Lake Havasu City Parks & Recreation
  contact_phone:      (928) 453-8686
  contact_url:        lhcaz.gov/parks-recreation/after-school-program-camps
  description:        Full-day summer camp grades 5–7. Swimming, crafts, movies,
                      bowling, cooking, fitness, and photography.

- title:              Adventure Camp (Archery, Kayaking & More)
  activity_category:  summer_camp
  age_min:            9
  age_max:            14
  schedule_days:      [MON, TUE, WED, THU, FRI]
  schedule_start_time: "09:00"
  schedule_end_time:   "13:00"
  schedule_note:      "Three 2-week sessions in June. ⚠️ Confirm 2026 dates."
  location_name:      Lake Havasu City Aquatic Center
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu City Parks & Recreation
  contact_phone:      (928) 453-8686
  contact_url:        lhcaz.gov/parks-recreation/after-school-program-camps
  description:        Half-day adventure camp. Archery, kayaking, snorkeling, fishing.

- title:              Fairway Friends (Youth Golf Intro)
  activity_category:  golf
  age_min:            3
  age_max:            8
  schedule_days:      [WED]
  schedule_note:      "Wednesdays in June. Ages 3–5 at 5:15pm | Ages 6–8 at 6:15pm. ⚠️ Confirm 2026 dates."
  location_name:      Lake Havasu City Aquatic Center / Iron Wolf Golf & Country Club
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               24.00
  cost_description:   "$24 per child per session."
  provider_name:      Lake Havasu City Parks & Recreation
  contact_phone:      (928) 453-8686
  contact_url:        lhcaz.gov/parks-recreation/after-school-program-camps
  description:        Beginner golf intro using plastic clubs. One session held at Iron Wolf GCC.
```

---

## BUSINESS 21 — THE TAP ROOM JIU JITSU

```
provider_name:    The Tap Room Jiu Jitsu
category:         martial arts / BJJ
address:          2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
phone:            (928) 889-5487
email:            thetaproomjj@gmail.com
website:          thetaproomjiujitsu.com
instagram:        @taproomjj
facebook:         facebook.com/p/The-TAP-ROOM-Jiu-Jitsu-61574029964504
established:      2025
pricing:          $109/month + $39.99 one-time sign-up (all memberships)
notes:            3-day free trial for locals. All ages welcome.
```

### Programs

```yaml
- title:              Littles Gi Jiu-Jitsu (Ages 3–6)
  activity_category:  martial_arts
  age_min:            3
  age_max:            6
  schedule_days:      [MON, WED]
  schedule_start_time: "16:30"
  schedule_end_time:   "17:15"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  cost_description:   "$109/month + $39.99 sign-up. 3-day free trial for locals."
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  contact_email:      thetaproomjj@gmail.com
  contact_url:        thetaproomjiujitsu.com
  description:        Gi Jiu-Jitsu for the youngest students ages 3–6.

- title:              Littles NoGi Jiu-Jitsu (Ages 3–6)
  activity_category:  martial_arts
  age_min:            3
  age_max:            6
  schedule_days:      [TUE, THU]
  schedule_start_time: "16:30"
  schedule_end_time:   "17:15"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  cost_description:   "$109/month + $39.99 sign-up."
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  contact_email:      thetaproomjj@gmail.com
  contact_url:        thetaproomjiujitsu.com
  description:        No-gi Jiu-Jitsu for the youngest students ages 3–6.

- title:              Youth Gi Jiu-Jitsu (All Levels)
  activity_category:  martial_arts
  age_min:            7
  age_max:            17
  schedule_days:      [MON, WED]
  schedule_start_time: "17:15"
  schedule_end_time:   "18:15"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  cost_description:   "$109/month + $39.99 sign-up."
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  contact_email:      thetaproomjj@gmail.com
  contact_url:        thetaproomjiujitsu.com
  description:        Gi Jiu-Jitsu for youth all skill levels.

- title:              Youth NoGi Jiu-Jitsu (All Levels)
  activity_category:  martial_arts
  age_min:            7
  age_max:            17
  schedule_days:      [TUE, THU]
  schedule_start_time: "17:15"
  schedule_end_time:   "18:15"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  cost_description:   "$109/month + $39.99 sign-up."
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  contact_email:      thetaproomjj@gmail.com
  contact_url:        thetaproomjiujitsu.com
  description:        No-gi Jiu-Jitsu for youth all skill levels.

- title:              Youth Wrestling (Ages 6+)
  activity_category:  martial_arts
  age_min:            6
  age_max:            17
  schedule_days:      [SAT]
  schedule_start_time: "09:00"
  schedule_end_time:   "10:00"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  cost_description:   "$109/month + $39.99 sign-up."
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  contact_email:      thetaproomjj@gmail.com
  contact_url:        thetaproomjiujitsu.com
  description:        Youth wrestling for ages 6 and up.

- title:              Adult Gi Jiu-Jitsu
  activity_category:  martial_arts
  age_min:            18
  age_max:            null
  schedule_days:      [MON, WED]
  schedule_start_time: "18:15"
  schedule_end_time:   "19:45"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  cost_description:   "$109/month + $39.99 sign-up."
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  contact_email:      thetaproomjj@gmail.com
  contact_url:        thetaproomjiujitsu.com
  description:        Adult gi Brazilian Jiu-Jitsu. All levels.

- title:              Adult NoGi Jiu-Jitsu
  activity_category:  martial_arts
  age_min:            18
  age_max:            null
  schedule_days:      [TUE, THU]
  schedule_start_time: "18:15"
  schedule_end_time:   "19:45"
  schedule_note:      "Also Fri 5:15–6:15pm (Leg Locks focus)."
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  cost_description:   "$109/month + $39.99 sign-up."
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  contact_email:      thetaproomjj@gmail.com
  contact_url:        thetaproomjiujitsu.com
  description:        Adult no-gi Jiu-Jitsu. All levels.

- title:              MMA
  activity_category:  martial_arts
  age_min:            18
  age_max:            null
  schedule_days:      [WED, FRI]
  schedule_note:      "Wed 7:30–8:30pm (sparring) | Fri 6:15–7:15pm"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  cost_description:   "$109/month + $39.99 sign-up."
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  contact_email:      thetaproomjj@gmail.com
  contact_url:        thetaproomjiujitsu.com
  description:        Mixed martial arts training and sparring.

- title:              Women's Only NoGi
  activity_category:  martial_arts
  age_min:            18
  age_max:            null
  schedule_days:      [MON]
  schedule_start_time: "09:00"
  schedule_end_time:   "10:00"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  cost_description:   "$109/month + $39.99 sign-up."
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  contact_email:      thetaproomjj@gmail.com
  contact_url:        thetaproomjiujitsu.com
  description:        Women-only no-gi Jiu-Jitsu. All skill levels welcome.

- title:              Open Mat (All Welcome)
  activity_category:  martial_arts
  age_min:            null
  age_max:            null
  schedule_days:      [SUN]
  schedule_start_time: "09:00"
  schedule_end_time:   "10:30"
  location_name:      The Tap Room Jiu Jitsu
  location_address:   2175 Kiowa Blvd N #104, Lake Havasu City, AZ 86404
  cost:               109.00
  cost_description:   "Included in membership. 3-day free trial available for locals."
  provider_name:      The Tap Room Jiu Jitsu
  contact_phone:      (928) 889-5487
  contact_email:      thetaproomjj@gmail.com
  contact_url:        thetaproomjiujitsu.com
  description:        Open mat — all skill levels and styles welcome.
```

---

## BUSINESS 22 — AREVALO ACADEMY (MMA)

```
provider_name:    Arevalo Academy
category:         martial arts / MMA
address:          3611 Jamaica Blvd S, Lake Havasu City, AZ 86406
phone:            (928) 855-0505
website:          arevaloacademy.com
facebook:         facebook.com/p/arevalo-academy-100054110934689
notes:            ⚠️ Schedule data from 2018 — VERIFY before going live. Call (928) 855-0505.
                  Still active per 2026 Yelp listing.
```

### Programs

```yaml
- title:              Little Ninjas (Ages ~3–5)
  activity_category:  martial_arts
  age_min:            3
  age_max:            5
  schedule_note:      "⚠️ VERIFY — Tue 3:30–4pm approx (from 2018 data)"
  location_name:      Arevalo Academy
  location_address:   3611 Jamaica Blvd S, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  needs_verification: true
  provider_name:      Arevalo Academy
  contact_phone:      (928) 855-0505
  contact_url:        arevaloacademy.com
  description:        Intro martial arts for youngest students. Coordination and balance.
                      No contact between students.

- title:              Kids MMA (Ages 6–12)
  activity_category:  martial_arts
  age_min:            6
  age_max:            12
  schedule_note:      "⚠️ VERIFY current schedule. Call (928) 855-0505."
  location_name:      Arevalo Academy
  location_address:   3611 Jamaica Blvd S, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  needs_verification: true
  provider_name:      Arevalo Academy
  contact_phone:      (928) 855-0505
  contact_url:        arevaloacademy.com
  description:        Children's MMA. Multiple levels from beginner through advanced.

- title:              Adult MMA
  activity_category:  martial_arts
  age_min:            18
  age_max:            null
  schedule_note:      "⚠️ VERIFY. Morning and evening sessions available."
  location_name:      Arevalo Academy
  location_address:   3611 Jamaica Blvd S, Lake Havasu City, AZ 86406
  cost:               CONTACT_FOR_PRICING
  needs_verification: true
  provider_name:      Arevalo Academy
  contact_phone:      (928) 855-0505
  contact_url:        arevaloacademy.com
  description:        Adult MMA. Muay Thai, Boxing, Kickboxing, BJJ, Wrestling.
                      HardCORE fitness class also offered.
```

---

## BUSINESS 23 — LAKE HAVASU BLACK BELT ACADEMY (TAEKWONDO / ATA)

```
provider_name:    Lake Havasu Black Belt Academy
category:         martial arts / Taekwondo
address:          597 N Lake Havasu Ave, Lake Havasu City, AZ 86403
phone:            (928) 453-0515
email:            info@lhcbba.com
website:          lakehavasublackbeltacademy.com
facebook:         facebook.com/pages/Lake-Havasu-Black-Belt-Academy/252983888055634
hours:            Mon–Fri ~4:00–7:30pm | Sat–Sun Closed
notes:            ATA affiliated. Ages 3–103. Free first class.
                  ⚠️ Schedule is a posted image — verify times at lakehavasublackbeltacademy.com.
```

### Programs

```yaml
- title:              ATA Tigers / Tiny Tigers (Ages 3–7)
  activity_category:  martial_arts
  age_min:            3
  age_max:            7
  schedule_note:      "Mon–Fri afternoons. Full schedule at lakehavasublackbeltacademy.com. ⚠️ VERIFY times."
  location_name:      Lake Havasu Black Belt Academy
  location_address:   597 N Lake Havasu Ave, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Black Belt Academy
  contact_phone:      (928) 453-0515
  contact_email:      info@lhcbba.com
  contact_url:        lakehavasublackbeltacademy.com
  description:        ATA Taekwondo for young children. Confidence, coordination,
                      and discipline. Free first class.

- title:              Karate for Kids (Ages ~7–12)
  activity_category:  martial_arts
  age_min:            7
  age_max:            12
  schedule_note:      "Mon–Fri afternoons. See lakehavasublackbeltacademy.com. ⚠️ VERIFY times."
  location_name:      Lake Havasu Black Belt Academy
  location_address:   597 N Lake Havasu Ave, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Black Belt Academy
  contact_phone:      (928) 453-0515
  contact_email:      info@lhcbba.com
  contact_url:        lakehavasublackbeltacademy.com
  description:        ATA Songham Taekwondo for school-age kids. Kicking, striking,
                      self-defense, and character development.

- title:              Teen & Adult Taekwondo
  activity_category:  martial_arts
  age_min:            13
  age_max:            null
  schedule_note:      "Mon–Fri evenings. See lakehavasublackbeltacademy.com. ⚠️ VERIFY times."
  location_name:      Lake Havasu Black Belt Academy
  location_address:   597 N Lake Havasu Ave, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Lake Havasu Black Belt Academy
  contact_phone:      (928) 453-0515
  contact_email:      info@lhcbba.com
  contact_url:        lakehavasublackbeltacademy.com
  description:        ATA Taekwondo for teens and adults. All levels through black belt.
                      Advanced: Black Belt Club, Masters Club, Leadership, Legacy.
                      Krav Maga and Tai Chi special sessions also available.
```

---

## BUSINESS 24 — ELITE CHEER ATHLETICS — HAVASU

```
provider_name:    Elite Cheer Athletics — Havasu
category:         cheer / competitive
address:          ⚠️ NOT CONFIRMED — DO NOT SEED PUBLIC-FACING
draft:            true
instagram:        @elite_cheer_athletic_lhc
facebook:         facebook.com/p/Elite-Cheer-Athletics-Havasu-61558235272946
ages:             3–18
notes:            New business ~2024–2025. No address, phone, or pricing confirmed.
                  Seed as draft=true. Admin must verify before publishing.
```

### Programs

```yaml
- title:              Competitive All Star Cheer
  activity_category:  cheer
  age_min:            3
  age_max:            18
  draft:              true
  schedule_note:      "⚠️ ALL DETAILS UNVERIFIED. Contact via Instagram before publishing."
  location_name:      ⚠️ UNKNOWN
  location_address:   Lake Havasu City, AZ
  cost:               CONTACT_FOR_PRICING
  provider_name:      Elite Cheer Athletics — Havasu
  contact_url:        instagram.com/elite_cheer_athletic_lhc
  description:        Competitive All Star cheerleading for ages 3–18.
                      All skill levels welcome.
```

---

## BUSINESS 25 — HAVASU STINGRAYS MASTERS SWIM TEAM

```
provider_name:    Havasu Stingrays Masters Team
category:         swim / fitness
address:          Lake Havasu City Aquatic Center, 100 Park Ave, Lake Havasu City, AZ 86403
website:          usms.org/clubs/lake-havasu-masters-team
organization:     U.S. Masters Swimming
notes:            Adult masters swim. Separate from youth Stingrays team.
```

### Programs

```yaml
- title:              Masters Swim Practice
  activity_category:  swim
  age_min:            18
  age_max:            null
  schedule_days:      [MON, WED]
  schedule_start_time: "06:00"
  schedule_end_time:   "07:00"
  location_name:      Lake Havasu City Aquatic Center
  location_address:   100 Park Ave, Lake Havasu City, AZ 86403
  cost:               CONTACT_FOR_PRICING
  provider_name:      Havasu Stingrays Masters Team
  contact_url:        usms.org/clubs/lake-havasu-masters-team
  description:        Adult masters swim practice under certified coaching.
                      U.S. Masters Swimming sanctioned. All adult swimmers welcome.
```

---

## QUICK REFERENCE — ADMIN FOLLOW-UP QUEUE

```
⚠️ DO NOT SEED PUBLIC-FACING (needs verification first):
- Elite Cheer Athletics Havasu (draft=true) — no address confirmed

⚠️ NEEDS_VERIFICATION = true (seeded but flagged for admin review):
- Arevalo Academy — schedule is from 2018, call (928) 855-0505
- Havasu Shao-Lin Kempo — schedule from 2018, call (928) 680-4121
- Lake Havasu Black Belt Academy — schedule is a posted image, verify at website
- BMX email — partially captured, verify full address
- Aquatic Center swim lesson cost — $37 is a 2020 rate, confirm 2026
- LHC Tennis — 2026 session dates not yet published, confirm at lhcaz.gov
- Stingrays membership email — verify domain for membership@havasustingrays.com
- ACPA Showcase venue — verify location

⚠️ PRICING (all show_pricing_cta = true in app):
Bridge City Combat | Flips for Fun | Shao-Lin Kempo | LHCBBA | Arevalo Academy
Universal Sonics | Footlite | ACPA | Ballet Havasu | Stingrays | Little League
Havasu Lions Soccer | LHC Flag Football | Bless This Nest | Aqua Beginnings
```

---

*All information sourced from business screenshots, official websites,
and verified third-party sources. Nothing invented.*
*Total businesses: 25 | Total programs: ~125 | Total events: 13*
*Compiled April 2026 for Havasu Chat app seeding.*
