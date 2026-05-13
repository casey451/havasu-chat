# Manual-Recovery Checklist — Lake Havasu Directory

> **Purpose:** A living catalog of directory items that can't be reliably gathered from online sources (Google Places, Yelp, public APIs) and require in-person operator field-work. Casey ticks items off as data is gathered. ChatGPT deep-research taxonomy will populate concrete entries; this file scaffolds the structure.
>
> **Status:** back-filled 2026-05-13 at session-23-extension-3 per Phase 5 prereq checklist §3.4.j. The back-fill is **field-work prompts** (where to look, what to record), NOT a populated venue inventory — operator generates the venue list during Phase 5 Layer-5 passes per category. ChatGPT taxonomy synthesis at `outputs/chatgpt_taxonomy_research_synthesis.md` informs the category boundaries; operator's local Lake Havasu knowledge informs the specific entries.
>
> **How to use:** Each entry has a `Status` field (`pending` / `field-trip-scheduled` / `info-gathered` / `entered` / `verified`). When you do a field-trip pass, you visit a cluster of items (e.g., "all dog parks in town" in one Saturday afternoon), photograph them, write down addresses + hours + amenities + access notes, then sit down later and enter the data via the admin form. Mark items `info-gathered` after the field trip and `entered` after the admin form submission.
>
> **Operator workflow:** drive to the location → photograph the front (one shot for hero) + any signage with hours or rules → note address from your phone's location pin → note any accessibility / parking / amenities details → on the way back, dictate notes to Notes app → that evening, type into admin form.

---

## §1 Community recreation facilities

Public or quasi-public facilities maintained by the city, Mohave County, school districts, or private organizations. Often missing from Google Places or listed with stale info. Best gathered via city Parks & Recreation website + in-person verification.

### Dog parks

- **Where to look:** Lake Havasu City Parks & Recreation facility list (`https://www.lhcaz.gov/parks-recreation`); cross-reference Google Places `dog_park` type; drive-by survey along the major park corridors (English Village, Rotary, Mesquite Bay)
- **Expected count:** 2-5 official + 1-3 informal
- **Pattern per entry:**
  - **Name:** official name if posted; otherwise the locals' name
  - **Address:** from phone pin if no street address
  - **Hours / access:** sunrise-sunset, leash-required-areas, fenced sections
  - **Amenities:** water bowl, shade, separate small-dog area, parking, waste-bag dispensers
  - **Status:** `pending` / `field-trip-scheduled` / `info-gathered` / `entered` / `verified`
- **Operator note:** OSM Overpass `leisure=dog_park` is the Phase 4.3 single-category proof — most dog parks should be on OSM too; cross-reference reduces Layer-5 work

### Baseball / softball / Little League fields

- **Where to look:** Lake Havasu City Parks & Rec field schedule (often a PDF); Lake Havasu Little League website; high school district fields (Lake Havasu Unified School District); the major sports complex if one exists locally
- **Expected count:** 4-8 fields across the city
- **Pattern per entry:**
  - **Name:** field name + park name (e.g., "Field 3, Rotary Park")
  - **Address:** parent park address
  - **Surface:** dirt infield / all-turf / mixed
  - **Lights:** TRUE / FALSE (lighted fields support evening games)
  - **Booking:** city P&R reservation line if applicable; otherwise first-come

### Pickleball courts

- **Where to look:** Lake Havasu City P&R; USAPickleball facility directory (verify per prereq §4.6 if endpoint live); local pickleball Facebook groups; drive-by HOA / RV-park courts (often visible from main roads)
- **Expected count:** 6-15 court locations (4-8 dedicated + 4-6 shared / convertible tennis courts)
- **Pattern per entry:**
  - **Name:** facility + court count (e.g., "Dust Devil Park — 8 dedicated courts")
  - **Address:** parent facility address
  - **Surface:** dedicated / lined-over-tennis
  - **Lights / hours:** dawn-dusk vs lighted-evening
  - **Reservation system:** drop-in / paid-rental / club-only
- **Operator note:** dedicated court counts are an active community topic in Lake Havasu; expect new builds during the Phase 5 window

### Tennis courts

- **Where to look:** City P&R facility list; high school + middle school courts (district website); private club courts (London Bridge Resort area)
- **Expected count:** 4-8 public + private courts
- **Pattern per entry:** same shape as pickleball courts but `surface = hard | clay`

### Soccer / multi-sport fields

- **Where to look:** City P&R; LHUSD school fields; the local AYSO or club soccer league site
- **Expected count:** 3-6 fields
- **Pattern per entry:** field name + parent park + surface (grass / artificial turf) + lights

### Basketball courts (public)

- **Where to look:** City P&R; drive-by survey of parks (Rotary Park, English Village, Site Six, Mesquite Bay)
- **Expected count:** 5-10 public outdoor courts
- **Pattern per entry:** parent park + court count + lights + condition (well-maintained / cracked / needs repair) — operator photo helps Phase 6 hero

### Skate parks

- **Where to look:** City P&R lists; SAM Park is the known one; check for newer builds in subdivisions
- **Expected count:** 1-3
- **Pattern per entry:** name + address + features (bowls / rails / quarter-pipes) + lights + adjacent restroom

### Disc golf courses

- **Where to look:** PDGA course directory (verify per prereq §4.7); SAM Park / Rotary Park; drive-by spotting (tee signs visible from park roads)
- **Expected count:** 1-3 (Lake Havasu is small for disc-golf coverage; expect 1 well-known + maybe 1 newer)
- **Pattern per entry:** name + parent park + hole count + difficulty rating per PDGA + free or fee

### Playgrounds (notable / destination)

- **Where to look:** City P&R; community-Facebook "best playground" threads; in-person spot during family time
- **Expected count:** 5-10 destination playgrounds (excludes basic playgrounds at every neighborhood park)
- **Pattern per entry:** name + parent park + age range (toddler / 5-12 / accessible) + shaded structures + restroom + parking
- **Operator note:** "destination" filter — only list playgrounds residents would drive to vs. the one within walking distance

---

## §2 Public infrastructure / outdoor places

Non-business places that aren't recreational facilities but are useful destinations. Often have a Google Maps pin but missing operational details (hours, fees, access notes).

### Boat ramps + marinas

- **Where to look:** OSM Overpass `leisure=marina` + `man_made=pier` + `natural=beach` (Phase 5 brief §3.2 OSM runs); Lake Havasu State Park ramp; Cattail Cove ramp; Site Six; English Village dock; Havasu Springs area; BLM-land primitive ramps (often unmapped)
- **Expected count:** 8-15 public + 3-6 private marinas
- **Pattern per entry:**
  - **Name:** official name (per State Parks or BLM signage) or locals' name
  - **Address / coordinates:** GPS pin if no street address (BLM-land ramps especially)
  - **Type:** State Park / city / BLM / private
  - **Boat access JSON:** populate per `docs/operations/boat_access_rubric.md` §1.1 (marinas) or §1.2 (public ramps)
  - **Notes:** launch fee, trailer parking count, restroom availability, dock condition, peak-hour wait estimate (Saturday morning during summer)
  - **Status:** `pending` / `field-trip-scheduled` / `info-gathered` / `entered` / `verified`
- **Operator note:** highest-priority Layer 5 category — Phase 6 boat-mode toggle depends on dense on-the-water coverage. Plan a single Saturday morning sweep covering the southern lake (Cattail Cove + Site Six) and a second weekday morning covering the channel (English Village + Lake Havasu State Park)

### Public beaches + lake-access points

- **Where to look:** Lake Havasu State Park (multiple beaches); Cattail Cove; London Bridge Beach; Rotary Park beach area; Mesquite Bay beaches; informal pull-offs along the shoreline
- **Expected count:** 8-15 designated beaches + 5-10 informal access points
- **Pattern per entry:**
  - **Name + parent park** (State Park, city park, BLM)
  - **Boat access JSON:** populate per `docs/operations/boat_access_rubric.md` §1.3 (beach shape)
  - **Notes:** motorized vs non-motorized buoy line, lifeguarded TRUE/FALSE, swim area marked, ADA access, parking spaces, fee or free, shade structures count
- **Operator note:** photograph each one — Phase 6 hero images depend on it; the public-domain photo problem makes operator photos disproportionately valuable here

### Fishing access points

- **Where to look:** Arizona Game & Fish fishing access map (`https://www.azgfd.com`); BLM-land shoreline; pull-offs along Highway 95 with visible bank fishing
- **Expected count:** 10-20 access points (overlap with beaches + ramps; many entities cross-list)
- **Pattern per entry:** name + parent jurisdiction + bank-only vs boat-launch + parking + restroom + best-known species (bass, crappie, striper)
- **Operator note:** for entries that ALSO appear in boat ramps + marinas, cross-list rather than duplicate — same entity, multiple secondary attributes

### Scenic overlooks / viewpoints

- **Where to look:** drive-by survey along the highway loops (Lake Havasu City to Parker direction; Lake Havasu City to Bullhead direction); SARA Park trail viewpoints; the Pittsburgh Point bluffs; Crystal Beach overlook
- **Expected count:** 5-12 designated + 5-10 informal pull-offs
- **Pattern per entry:** name (or "viewpoint at MM XX of Hwy 95") + parking + accessibility + best-known feature (sunrise / sunset / lake panorama / channel view)

### Hiking trailheads

- **Where to look:** BLM-land trail map; SARA Park trails; Crack-in-the-Mountain; State Park trails; Mohave Community College area
- **Expected count:** 8-15 trailheads
- **Pattern per entry:**
  - **Name + parent land** (BLM / State Park / city / SARA Park / private)
  - **Notes:** trail length (round-trip), difficulty (easy / moderate / strenuous), dog-friendly, parking, water availability (NONE for most desert trails), cell coverage, best season (typically Oct-Apr; summer too hot)
  - **Phase 5 specific:** seasonal_hours JSON for summer-closure trails (some BLM trails are operator-judgment-closed in 110°F+ temps)

### Off-roading / OHV staging areas

- **Where to look:** BLM-land OHV maps; State Trust Land OHV permits; local OHV club sites (Lake Havasu area OHV clubs)
- **Expected count:** 5-10 staging areas
- **Pattern per entry:** name + GPS pin + permit required TRUE/FALSE + connecting trail systems + nearest gas + cell coverage

### Public restrooms (notable)

- **Where to look:** parks already on the list; downtown English Village area; State Park facilities; gas stations rarely qualify (operator judgment on "notable")
- **Expected count:** 10-20 — only include if "notable" (clean, ADA-accessible, available during boating/fishing day, or specifically searched-for by visitors)
- **Pattern per entry:** parent location + indoor vs vault toilet + accessibility + 24-hour vs daytime-only
- **Operator note:** this list is for visitor-traffic UX (the "is there a restroom near the dock?" search), not infrastructure inventory

### Picnic areas + shaded ramadas

- **Where to look:** every public park + State Park; HOA-managed common-area picnic spots (typically not in scope); BLM picnic sites on shoreline
- **Expected count:** 15-25 dedicated picnic structures (within entities; many entities have multiple ramadas — count per parent entity)
- **Pattern per entry:** parent park + ramada count + table count + BBQ grills available + reservation system (some city parks book ramadas via P&R)

---

## §3 Hobbyist clubs / specialty venues

Places that exist because a local group runs them. Usually no formal storefront, often only findable via Facebook groups or word of mouth.

### RC tracks / RC clubs

- **Where to look:** Lake Havasu RC club Facebook groups; AMA (Academy of Model Aeronautics) club locator; SARA Park area (often hosts RC events); drive-by spotting of fenced dirt tracks
- **Expected count:** 1-3 (small-town RC scene; often one main track)
- **Pattern per entry:** name + parent location + surface (dirt / paved / indoor) + club affiliation + event schedule

### Model railroad / hobbyist gatherings

- **Where to look:** local hobby shop bulletin boards (Hobby Lobby / Michaels in Lake Havasu); senior-center or community-center event schedules
- **Expected count:** 0-2 — small-town hobby scene, expect this to be sparse or absent
- **Pattern per entry:** group name + meeting location + meeting cadence (monthly / weekly) + open-to-public TRUE/FALSE

### Shooting / archery ranges

- **Where to look:** Arizona Game & Fish public range list; private clubs (Lake Havasu Trap & Skeet club historically); BLM-land informal shooting areas (operator must verify legality before listing)
- **Expected count:** 1-3 organized ranges + 1-2 informal BLM areas
- **Pattern per entry:** name + range type (rifle / pistol / shotgun / archery) + public access vs membership + safety officer schedule + fee

### Skating rinks (roller / ice)

- **Where to look:** city directory; expect this category to be empty or near-empty (Lake Havasu doesn't have indoor ice; roller rink unclear)
- **Expected count:** 0-1 — likely empty; if scratched, omit the entry from final inventory
- **Pattern per entry:** standard venue shape

### Bowling alleys

- **Where to look:** Google Places `bowling_alley` type catches this; operator verifies operating-status during Phase 5 (small-town bowling alleys often close)
- **Expected count:** 1-2 active
- **Pattern per entry:** name + lane count + youth-league hours + bar / food TRUE/FALSE

### Indoor go-karts / arcades

- **Where to look:** Lake Havasu Chamber member directory; family-entertainment Facebook groups
- **Expected count:** 1-3
- **Pattern per entry:** name + age range + reservation required + party-rental availability

### Climbing walls / gyms (bouldering)

- **Where to look:** community-rec listings; YMCA-equivalent organizations; the Mohave Community College facility
- **Expected count:** 0-2 — likely sparse in a non-mountain town; operator-judgment whether to include outdoor bouldering spots
- **Pattern per entry:** name + indoor / outdoor + difficulty range + youth program TRUE/FALSE

### Car clubs / classic car meet-up locations

- **Where to look:** Cruise-in Facebook groups; weekly meet-up venues (often diner parking lots or chain restaurant lots); annual events (operator separates one-off events from weekly recurring)
- **Expected count:** 3-8 recurring meet-ups + 1-3 annual events
- **Pattern per entry:** event name + venue + day of week + time + season + sponsoring club
- **Operator note:** these are mostly Events (Phase 1 Event entity) not Provider entries — list here for operator memory + cross-link to Event rows

### Boating / fishing clubs

- **Where to look:** Lake Havasu Bass Club + similar; fishing-tournament organizers; yacht clubs / power-squadrons
- **Expected count:** 3-6 active clubs
- **Pattern per entry:** club name + meeting location + meeting cadence + public-event schedule + dues vs free + sponsoring marina or restaurant

### Aviation / RC airplane fields

- **Where to look:** AMA club locator; Lake Havasu Municipal Airport (regular aviation, not RC); county RC airfield permits
- **Expected count:** 1-2 RC airfields + 1 general-aviation airport
- **Pattern per entry:** name + airfield type (paved / grass / RC-only) + access (public / club / fee) + nearest restroom + cell coverage

---

## §4 Ephemeral / seasonal / recurring

Things that happen on a schedule rather than existing as a fixed venue. Treated as Events in the schema but worth listing here for operator memory.

### Farmers markets

- **Where to look:** Lake Havasu Farmers Market Facebook page; city event calendars; downtown Main Street / English Village area on weekend mornings; check seasonality (many farmers markets pause during 110°F+ summer months)
- **Expected count:** 1-3 weekly + 1-2 seasonal
- **Pattern per entry:** name + location + day of week + season (year-round vs winter-only) + vendor count estimate (low: ~10, mid: ~25, high: ~50+) + sponsoring organization

### Food truck regulars + meet-ups

- **Where to look:** "Lake Havasu food truck" Facebook search; weekly meet-up venues (brewery parking lots, park events); Friday night gathering spots
- **Expected count:** 5-15 regular trucks + 1-3 organized meet-up venues
- **Pattern per entry:**
  - **Trucks:** truck name + cuisine + booking/contact + typical weekly schedule
  - **Meet-up venues:** venue name + day of week + truck count estimate per gathering

### Weekly meet-ups (car shows, etc.)

- **Where to look:** Facebook groups (Lake Havasu Cruise-in, RV-owner meet-ups, motorcycle groups); diner/restaurant parking lots on weekend mornings (cruise-ins are classic American small-town tradition); the Lake Havasu Chamber event calendar
- **Expected count:** 3-8 recurring
- **Pattern per entry:** event name + venue + day of week + time + season + sponsoring club + estimated attendance

### Seasonal events (Desert Storm, IJSBA, spring break, holiday)

- **Where to look:** Visit Lake Havasu official tourism calendar; Lake Havasu Chamber annual events list; previous-year photos / news coverage
- **Expected count:** 10-20 named annual events
- **Pattern per entry:** event name + month + duration (single-day vs multi-day vs season-long) + scale (local vs regional vs national-draw) + traffic-impact (low / medium / high — for Phase 8 event_traffic alerts) + venue or geographic spread
- **Operator note:** these populate the events table (Phase 1 Event entity), not manual-recovery Provider entries — but listing them here helps the operator track which seasonal events also have associated Provider entries (e.g., Desert Storm has a temporary registration venue; IJSBA Worlds has temporary spectator zones)

### Music / open-mic / karaoke nights

- **Where to look:** restaurant + bar Facebook pages; flyers in coffee shop / bar bulletin boards; the music-scene Facebook groups
- **Expected count:** 8-20 recurring nights across 5-12 venues
- **Pattern per entry:** venue + night of week + type (open mic / karaoke / live band / DJ) + start time + season (some pause during summer or winter)
- **Operator note:** these populate as recurring Events with parent Provider entries — venue is the Provider, night-of-week is the Event recurring pattern

---

## §5 Non-business places worth listing

Local landmarks, historical points, civic locations that don't sell anything but matter for orientation + recommendations.

### Historical markers / monuments

- **Where to look:** Lake Havasu City historic sites page; Mohave County historical society; Arizona historical-marker registry; the McCulloch family / Robert McCulloch Sr. memorial sites
- **Expected count:** 5-12 markers + monuments
- **Pattern per entry:** name + location (often a roadside pull-off or park location) + plaque text summary + parking + season (some inaccessible in summer heat)

### Civic locations (City Hall, Library, DMV, Court)

- **Where to look:** Google Places `city_hall` + `library` types catch some; Lake Havasu City government directory; Mohave County Lake Havasu offices; Arizona MVD location
- **Expected count:** 8-15 civic locations
- **Pattern per entry:** name + address + hours (most close early afternoons or weekends) + parking + restroom availability for visitor-routing
- **Operator note:** these map to `public-civic-resources` category (Tier 2/3 not Tier 1, but listed here for operator field-trip planning)

### Notable public art / installations

- **Where to look:** "Lake Havasu public art" Facebook search; city Public Art Master Plan if available; the lighthouse-replica project series (see below); drive-by spotting along the channel and main parks
- **Expected count:** 10-20 (lighthouse replicas + sculpture installations + murals)
- **Pattern per entry:** name + location + artist (if known) + installation year + best-known feature (photo-spot, plaque, hidden, etc.)

### London Bridge + nearby points of interest

- **Where to look:** London Bridge Visitor Center; English Village shopping area; "Bridgewater Channel" area; the historic-marker series surrounding the bridge
- **Expected count:** 5-10 named POIs in the bridge area
- **Pattern per entry:** name + position relative to bridge (under-bridge, north end, south end, channel-side, English Village side) + best-photo-time + parking
- **Operator note:** London Bridge itself + the channel under it is a single high-profile entity; surrounding POIs (visitor center, plaques, retail areas) are separate Provider/place entities cross-linked

### Lake Havasu lighthouses

- **Where to look:** Lake Havasu Lighthouse Club site (the local non-profit that maintains the replica lighthouses); operator coastline drive; each lighthouse has a numbered placement along the shoreline
- **Expected count:** 20-30 replicas (this is a defining Lake Havasu feature; the replica series is locally famous)
- **Pattern per entry:** lighthouse number + named-after (most are scale replicas of real lighthouses) + GPS coordinates + parking access + photo-friendly best time of day
- **Operator note:** consolidate as a single "Lake Havasu Lighthouse Replica Series" entity with sub-list, OR list each as its own entity — operator's call based on Phase 6 UX rendering preference. Recommended: single parent entity with the 20-30 replicas as enumerated sub-points in `crowd_notes` JSON

---

## §6 Tier-2 manual recovery — businesses with weak online presence

Real businesses that exist but have minimal/no online footprint. Smaller operators, older businesses, niche services. Often discoverable by driving past them or via local knowledge.

### Mom-and-pop home services (handymen, mobile mechanics)

- **Where to look:** Nextdoor "recommended handyman" threads; RV-park bulletin boards (operator photo during routine errands); Facebook Marketplace service-offerings; gas-station + diner bulletin boards
- **Expected count:** 15-30 mom-and-pop service providers not on Google
- **Pattern per entry:**
  - **Name:** owner-operator name OR business name if branded
  - **Contact:** phone (most don't have websites; SMS-first is common)
  - **Specialty:** handyman / mobile mechanic / mobile RV-tech / cleaning / pool-service / etc.
  - **Service area:** Lake Havasu city / wider (Parker / Bullhead / Kingman) / island-only
  - **Verification:** AZ ROC license cross-reference per Phase 5 §3.3 — many of these will be unlicensed by design (small jobs, owner-operator); document license status either way
- **Operator note:** these dominate the Layer 5 work for `home-property-services` category — expect this section to be the largest in the full back-fill once Phase 5 runs

### Specialty shops not on Google Places

- **Where to look:** Downtown / Main Street walking survey; the McCulloch corridor strip-mall directories; Lake Havasu City annual Visitor Guide (commercial annual, operator scan); the Saturday-market vendors with permanent storefronts elsewhere
- **Expected count:** 10-20
- **Pattern per entry:** name + specialty + address + hours + owner-operator vs chain (most are owner-operator)
- **Operator note:** typical surface patterns — niche hobby shops, consignment stores, vintage / antique dealers, gun shops, specialty crafts. Each gets a Google Places search to verify they aren't on Google (some are but with bad info)

### Local trades that work word-of-mouth

- **Where to look:** RV-park resident referrals (operator asks at front desk during routine errands); Facebook neighborhood-group "who do you use for..." threads; gas-station bulletin boards
- **Expected count:** 10-25 word-of-mouth-only trades
- **Pattern per entry:** trade type + contact + service area + verification status (license + insurance)
- **Operator note:** verifying license + insurance is harder for word-of-mouth trades — operator may need to ask the trade directly for proof + photograph it; document `verified=False` with reason if proof not obtainable

---

## §7 Operator field-trip planner

When ChatGPT research populates the entries above, use this section to plan efficient field-trip routes — group items by geographic cluster so one Saturday morning covers several entries.

### Suggested route clusters

- **North-side sweep (estimated 90-120 min):**
  - Mesquite Bay area parks + dog parks + ramadas
  - North-end neighborhood Layer-5 (mom-and-pop services bulletin boards)
  - North-end public art / lighthouse replicas
  - North-end fishing access points
- **Downtown / Main Street sweep (estimated 60-90 min):**
  - Downtown Main Street walking survey for specialty shops
  - McCulloch corridor strip-mall scan
  - Civic locations (City Hall, Library, DMV nearby)
  - Downtown public art / murals
- **English Village + Channel sweep (estimated 90-120 min):**
  - London Bridge POIs (visitor center, plaques, photo-spots)
  - Channel-side restaurants for boat_access JSON (dock-and-dines)
  - English Village dock + ramp
  - Lighthouse replicas along the channel
  - Channel-side public art
- **Lakefront sweep (estimated 2-3 hours, full Saturday morning):**
  - Lake Havasu State Park (multiple beaches + ramps + picnic areas + trail)
  - Cattail Cove + neighboring BLM-land access
  - Site Six public ramp + amenities
  - Castle Rock area beaches
  - Pittsburgh Point bluffs + overlooks
- **95 corridor sweep (estimated 2-3 hours):**
  - SARA Park trailheads + RC area + disc golf if present
  - Highway 95 scenic overlooks
  - South-of-town gas-stations + auto services for Layer-5 home-property field-tech contacts
  - Crack-in-the-Mountain trailhead
- **Off-island sweep (operator-judgment whether in scope for V1):**
  - Parker direction: Buckskin Mountain State Park, smaller marinas
  - Bullhead direction: Lake Havasu Marina at lake's north end if scoped
  - Kingman direction: county government offices, Mohave County GIS in-person verify

**Sequencing recommendation:**
- Lakefront sweep is the **highest-value first** because it densely populates on-the-water Layer-5 (the Phase 6 boat-mode-critical category). Do this in week 1 of Phase 5.
- English Village + Channel sweep is **second-highest-value** — high tourist density + the photogenic London Bridge area + significant lighthouse coverage. Do in week 2.
- Downtown + Main Street sweep is **third** — fills eat-drink + shopping-essentials Layer-5 gaps. Do in week 3.
- North-side + 95 corridor in weeks 4-5 (lower-density coverage; the operator chooses based on what's still light per the per-category acceptance gates).
- Off-island sweep only if Tier 1 acceptance gates land early; otherwise V1.5.

---

## §8 Status summary (auto-updates as items are ticked)

- **Total items catalogued:** TBD (pending taxonomy research)
- **Items pending field-trip:** TBD
- **Items in `info-gathered`:** 0
- **Items in `entered`:** 0
- **Items in `verified`:** 0

(Update this section manually after each field-trip pass or batch entry session.)

---

## §9 Categories that AREN'T manual-recovery

For reference — categories that are mostly online-discoverable and don't need this checklist. Listed here so the operator doesn't burn time on them.

- Restaurants (Google Places + Yelp coverage is comprehensive in Lake Havasu)
- Hotels / motels (Booking + Tripadvisor + Google all cover well)
- Most retail (Google Places good)
- Most professional services (Google + the AZ business registry)
- Most healthcare providers (Google + NPI registry + insurance directories)
- Most automotive services (Google Places good)

These categories use the **automated scraper** lane (`scripts/places_discovery.py` + `scripts/places_enrichment.py`), not this manual-recovery flow. Manual-recovery only kicks in for the gaps the scraper can't cover.

---

*This file is updated as ChatGPT taxonomy research returns + as field-trips are scheduled and completed. Cowork primary will populate the section bodies once the taxonomy research is in hand.*
