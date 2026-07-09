# Cuisine backfill — client-side review batch (2026-07-08)

**Provenance:** client-side review (audit-informed). **Rule:** UNKNOWN over guess;
snippets used as context only. **27 classified, 17 UNKNOWN** of 44
`needs_llm`+`needs_places` rows. Classified rows are appended to
`cuisine_apply_approved_2026-07-08.csv` (note = `client-side review`) and applied
via `cuisine-backfill-apply.yml`; UNKNOWN rows are recorded here and written
nowhere (an unknown beats a wrong chip).

## Full curated CSV (as received)

```
slug,cuisine
arizona-rebel-republic-havasu,american
bad-miguel-s,mexican
boat-house-grill,american
desert-martini-too,UNKNOWN
foundry,UNKNOWN
hangar-24-taproom-restaurant,american
heat-bar-the-heat-hotel,UNKNOWN
kegler-s-pub-at-havasu-lanes,american
kitchen-738,american
kokomo-beach-surf-party-bar,UNKNOWN
lake-view-grill,american
majik-bistro-milkshakes,american
monch,burgers
montana-s,steakhouse
naked-turtle-beach-bar-at-the-nautical-beachfront-resort,UNKNOWN
niko-s-grill-and-pub,american
oasis-at-the-views-restaurant,american
oxido,mexican
paleo-to-go-inc,UNKNOWN
papa-bear-s-restaurant,american
piccadilly-s-and-more,UNKNOWN
place-to-be,american
river-blend-coffee-co,UNKNOWN
rotary-kitchen-bar,american
shugrue-s-bridgeview-room,american
shugrue-s-restaurant-bar,american
siddhartha-s-garden,UNKNOWN
side-alley-cafe,UNKNOWN
sloane-s-craft-kitchen-cocktails,american
subway-at-havasu-north-shopping-center,sandwiches
subway-at-smith-s-shopping-center,sandwiches
subway-at-southside-basha-s-plaza,sandwiches
the-bunker-bar,UNKNOWN
the-chair,UNKNOWN
the-human-bean-palo-verde-blvd-n,UNKNOWN
the-meltdown,sandwiches
the-office-cocktail-lounge,UNKNOWN
the-pour-house,american
the-springs-dining-at-havasu-springs-resort,american
tropical-smoothie-cafe,UNKNOWN
turtle-grille,american
turtle-grille-at-the-nautical-beachfront-resort,american
wet-pool-bar-at-the-nautical-beachfront-resort,UNKNOWN
wild-coffee,UNKNOWN
```

## Reasoning (kept with the undo CSV)

- Montana's = steakhouse via its §14.1 twin (Montana Steak House). Bad Miguel's =
  mexican via its twin. The Meltdown = sandwiches (Denny's melt-focused virtual
  brand — same 1620 McCulloch address; consider a "virtual brand" note or hiding
  it). Monch = burgers (burger food truck). OXIDO = mexican (known local Mexican
  street-food concept).
- Notable abstentions: Siddhartha's Garden (plant-based/health — no enum home;
  the audit's own cautionary example), Piccadilly's (signature is Navajo
  frybread/tacos — no enum home), Foundry and The Chair (evidence too thin), Side
  Alley Cafe (one review praising pizza ≠ pizza place).

## Follow-ups (logged, NOT actioned in this batch)

- **Enum-gap proposals (separate list, do not force):** `vegetarian_vegan`,
  `coffee`, `frybread/native_american`.
- **Better-than-cuisine SUBCATEGORY fixes (5 rows):** river-blend-coffee-co,
  wild-coffee, the-human-bean (coffee shops) and tropical-smoothie-cafe belong in
  the **Cafés & Coffee** subcategory, not the Restaurants facet; paleo-to-go-inc
  is a meal-prep service, arguably not a restaurant listing. Reclassifying their
  SUBCATEGORY beats giving them a cuisine.
- **Twin alert (§14.1 pattern, merge once the WS4 phone-signal fix lands):**
  bad-miguel-s, montana-s, hangar-24-taproom-restaurant, niko-s-grill-and-pub,
  kokomo-beach-surf-party-bar, shugrue-s-bridgeview-room, shugrue-s-restaurant-bar,
  turtle-grille-at-the-nautical-beachfront-resort, the-office-cocktail-lounge.
  Classifications match their keepers, so facet counts stay correct through merge.
- **Geo flag:** the-springs-dining-at-havasu-springs-resort is out-of-region
  (Parker side) — same M5 geo-scope treatment as Black Meadow Landing Diner.
