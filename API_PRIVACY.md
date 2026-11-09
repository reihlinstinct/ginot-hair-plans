# Public planning data: privacy boundary

Owner decision recorded November 6, 2026 in issue #123.

- Public exports contain only reviewed planning/permit fields already shown by
  the site. `src/ginot/static/public-api-fields.json` is the shared allowlist
  for static `data.json`/`open.json` and the query Worker's responses.
- Unknown fields, objects, arrays and non-finite numbers do not pass the JSON
  boundary. New fields need privacy review and a test before publication.
- Names of people, contact details, identity/payment identifiers, private notes
  and planner tracking state must not be added. Free text in approved public
  fields still needs source/content review: an allowlist is not a classifier
  and cannot promise that every upstream description is free of personal data.
- Planning-data query routes are read-only. They cannot file an objection,
  submit a permit, change a record or trigger a workflow.
- Static Pages files remain the source of truth. No new live service is needed
  for this decision. The existing stateless query Worker only reads those
  public files; these changes do not add a route or capability.
- Existing aggregate usage counters (`/stats/event`, issue #821) are a separate
  feature, not a planning-data write API. They accept dictionary-matched public
  keys or `other`, never raw search text. This decision does not widen them.
- The separate community submission service is outside this data API decision;
  its permissions and privacy rules are not changed here.
- Any future service exposing private data needs a separate private repository,
  token authentication, and a new scoped decision. Private planning/tracking
  and parking/enforcement information stays out of this public repository.

The synthetic privacy tests inject unknown personal/tracking fields into the
static publisher and every query response route. They also reject nested
values in allowed fields. They contain no real private values.

## On-demand plan email (api/send_plan_email.py, Vercel)

A separate opt-in service, owner-approved November 9, 2026; it reads only the
public rows above and exposes no private data.

- What is stored: the typed email address, plan id, page language, a random
  token, timestamps (and the status last seen, for subscribers). Nothing else;
  no request logging, no analytics on the endpoint, no sharing.
- Nothing is emailed to an address until its owner presses the confirm button
  on the confirmation link's page (a GET never changes state, so link scanners
  cannot confirm or unsubscribe anyone).
- Retention: a pending request is deleted on confirmation or after 48 hours.
  A subscription (only if the subscribe box was ticked) lives until the
  person unsubscribes; unsubscribing deletes the record at once.
- Where: Vercel serverless function (Hobby) with Upstash Redis in Frankfurt
  (eu-central-1), free tier. Sending uses the owner's SMTP account (Gmail app
  password) held only in Vercel environment variables.
- Abuse counters are kept as hashed keys (IP and recipient digests) with
  automatic expiry; they hold no readable addresses.

