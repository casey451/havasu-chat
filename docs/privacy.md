## What we collect

When you use Havasu Chat, we store:

- **Your chat messages and our responses** — to improve the
  service, fix bugs, and catch gaps in what we cover.
- **Your session ID** — a random identifier generated per visit.
  It doesn't tie to any identity or personal information.
- **Technical metadata** — which tier of the chat pipeline
  answered, how long it took, how many language-model tokens
  were used.
- **A one-way hash of your query** — used for rate limiting and
  spotting repeated questions, not for identifying you.

If you contribute a business or event, we also store:

- **The submission content** — name, URL, and any notes you
  provide.
- **Your email address** — only if you choose to provide one for
  follow-up.
- **A one-way hash of your IP address** — used to prevent spam.
  We don't store your raw IP address.

In addition to the one-way hash, we keep a plain-text copy of your
question in our database so we can read real examples when improving
the service — fixing bugs, noticing gaps, and tuning the concierge's
voice. Only the operator accesses this; it is not sold or used for
advertising.

## Why we collect it

We use this data to:

- Make the concierge better — read what people ask, spot what
  we can't answer yet, fine-tune the local-friend voice.
- Catch abuse — rate limiting and spam prevention.
- Review contributions — the operator (one person) reviews
  submissions before they go live in the catalog.

We do not sell or share this data with anyone else. We do not
use it to build profiles of individual users or to target ads.

## Who else sees your data (subprocessors)

To answer your questions, we send some of your data to these
providers:

- **Anthropic** — we send your message to Claude Haiku for
  filtering, analyzing, and generating responses across the
  chat pipeline.
- **OpenAI** — we send your message to OpenAI models (GPT-4.1 mini
  and text-embedding-3-small) for extracting hints to maintain
  session context, generating tags, and computing semantic
  search embeddings.
- **Google Places** — when someone contributes a business, we
  query Google Places for hours, address, and other details.

These providers have their own privacy and data-retention
policies:

- Anthropic: https://www.anthropic.com/privacy
- OpenAI: https://openai.com/privacy
- Google: https://policies.google.com/privacy

We host on Railway, which stores the application logs and
database. We use Sentry for error tracking. Both operate under
their own policies.

## How long we keep it

Right now, we do not automatically delete old chat messages or
contributions. The database retains them indefinitely.

We'll revisit this after six months of operation. If retention
becomes a concern you'd like to raise sooner, contact us (below).

## Your choices

- You can use Havasu Chat without providing an email address or
  any personal information.
- Your session gets a fresh random identifier each time you
  load or reload the app — no persistent
  account ties you to past conversations from our side.
- The feedback button at the bottom of each response lets us
  know when something's wrong; it's the fastest way to reach
  us with questions or concerns.

## Contact

The fastest way to reach us is the feedback button at the bottom
of each chat response — it goes straight to the operator.

You can also reach us by email at caseylsolomon@gmail.com.

<!-- TODO: replace caseylsolomon@gmail.com with dedicated havasuchat contact address before public launch -->
