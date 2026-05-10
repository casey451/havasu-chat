# Hava — questions and answers

Hava is a local concierge chat tool built specifically for Lake Havasu City, Arizona. It answers questions about local businesses, events, services, and activities in short conversational replies instead of long lists of links and reviews.

The project is run locally and is still growing. You can use Hava at [havasu-chat-production.up.railway.app](https://havasu-chat-production.up.railway.app).

---

## What is Hava?

Hava is a chat-style local assistant for Lake Havasu City. Instead of searching through multiple apps, websites, Facebook groups, and review pages, you can ask a question the same way you'd text somebody who knows the area well.

Questions can be casual, incomplete, or specific. You do not need perfect wording. Things like the following all work normally:

- "good mexican food open right now"
- "where can I get stitches"
- "boat repair open saturday"

Hava answers in short 1–3 sentence responses because most local searches are not deep research problems. Usually people just want an answer quickly without opening five tabs and comparing reviews for twenty minutes.

The goal is not to replace Google or Yelp entirely. The goal is to handle the "I just need an answer" moment faster.

---

## How is this different from Google or Yelp?

Google and Yelp are good at browsing, comparing reviews, and exploring options. They are less useful when you already know roughly what you want and just need a fast local answer.

Hava is designed around conversational local search instead of directory-style search. You can type awkward phrasing, partial memories, or quick text-message-style questions and still usually get a usable response.

For example:

- "good mexican food open right now"
- "where can I get stitches"
- "boat repair open saturday"
- "quiet dinner place with kids"
- "anything going on tonight"

Hava is also focused only on Lake Havasu City. It is not trying to answer questions about every city everywhere. That narrower focus makes shorter and more direct answers possible.

---

## Can I trust the answers?

Hava answers using a curated catalog of Lake Havasu businesses, services, and events. Businesses in the catalog are manually reviewed and verified by the operator instead of being pulled blindly from the internet.

Each business also has an internal "last verified" timestamp that Hava uses when deciding how confident to sound about hours, contact information, or availability. That date is not shown directly to users, but it helps prevent stale information from sounding overly certain.

If Hava is not confident about something, it should say so clearly. Responses may include wording like:

- "you might want to call to confirm"
- "hours may have changed recently"
- "I'm not completely sure on that one"

If Hava does not know something, the goal is to say that plainly instead of guessing.

Some businesses pay for a Spotlight placement inside Hava. Those listings are labeled `Sponsored` when they appear. Sponsored placement only affects visibility within results. It does not change factual business information like hours, phone numbers, or addresses.

---

## What can I ask Hava?

### Local business lookup

- "good breakfast spot open now"
- "best place for tire repair"
- "where can i get my phone fixed"
- "urgent care open sunday"

### Event and activity lookup

- "anything happening tonight"
- "kid events this weekend"
- "live music near the bridge"
- "pickleball classes this week"

### After-hours and emergency questions

- "emergency plumber tonight"
- "boat repair open saturday"
- "ac stopped working who do i call"
- "where can i get stitches"

### Casual recommendations

- "quiet place to eat with kids"
- "good coffee shop to work from"
- "best happy hour right now"
- "things to do when it's too hot outside"

### Location-specific questions

- "food near london bridge"
- "closest gas station to the marina"
- "restaurants near the launch ramp"
- "anything open late on the south side"

---

## What can't Hava do?

Hava is intentionally local-only. It is built around Lake Havasu City and nearby local activity. If you ask about another city, another state, or general internet questions, the answers may be limited or unavailable.

Hava also does not:

- book reservations
- place orders
- process payments
- call businesses for you
- guarantee availability or wait times

The catalog is still growing. If Hava says "I'm not sure" for something that should probably exist locally, that may simply mean the business or event has not been added yet.

If something seems missing or incorrect, you can send feedback directly. Right now there is not a built-in per-message feedback inbox inside Hava, so email feedback should go to [CASEY: insert feedback contact email].

---

## Is my chat private?

Hava stores chat queries to improve answer quality and identify gaps in the local catalog. Stored logs may include the text of the query, a timestamp, and a session ID.

The logs are not intended to identify individual users personally. Hava does not intentionally store personal identity information, browsing history, or memory across sessions unless you explicitly type that information into the chat yourself.

If you want a session deleted or have privacy questions, email [CASEY: insert privacy contact email].

---

## Who runs this?

Hava was built and is operated by Casey, a Lake Havasu resident, as a side project focused on making local information easier to find without relying entirely on large search platforms and review directories.

It is not affiliated with Google, Yelp, or another national directory company.

---

## How do I give feedback?

You can reply directly inside Hava or email [CASEY: insert feedback contact email].

The most useful feedback is:

- missing businesses
- wrong hours or contact info
- confusing answers
- categories Hava should support better
- local events that should be included
