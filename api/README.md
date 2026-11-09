# api/ - Vercel serverless functions

## send_plan_email.py

On-demand plan-objection email. The site's `email.html` form posts
`{email, plan_number}` here; the function reads the plan's public row from
the site's own published `data.json`, composes a Hebrew email (plan
number/name, status, objection deadline, mavat link, how-to-object pointer)
and sends it over SMTP. The recipient address is used in memory to send and
is never logged or stored.

### Sender account: how to swap it (no code change)

Everything about the sender is a Vercel environment variable. To move the
sender to another account or provider, change these in the Vercel project
settings (Environment Variables) and redeploy - no code change:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `465` | SMTP port (SSL) |
| `SMTP_USER` | - (required) | SMTP login; also the envelope sender |
| `SMTP_PASSWORD` | - (required) | SMTP password / Gmail app password |
| `EMAIL_FROM_ADDRESS` | `SMTP_USER` | Visible From address |
| `EMAIL_FROM_NAME` | `reihlinstinct` | Visible From display name |
| `EMAIL_REPLY_TO` | `reihlinstinct@gmail.com` | Reply-To (set empty to disable) |

For Gmail, `SMTP_PASSWORD` is an app password of the `SMTP_USER` account.
The app password lives only in the vault and in Vercel env vars - never in
the repo, never in logs.

### Other configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `SITE_DATA_URL` | the site's public `data.json` | Plan data source |
| `ALLOWED_ORIGIN` | `*` | CORS origin for the form |
| `PER_IP_HOURLY_CAP` | `3` | Per-IP hourly send throttle |
| `DAILY_SEND_CAP` | `50` | Global daily send cap |
| `BASE_URL` | project `.vercel.app` origin | Base for confirm/unsubscribe links |
| `CRON_SECRET` | - (required for notify) | Bearer secret for the daily cron call |
| `KV_REST_API_URL` / `KV_REST_API_TOKEN` | unset | Vercel KV (Upstash) storage; unset = subscriptions inert |

## Subscriptions (privacy-first)

The form's subscribe checkbox starts a double opt-in: a confirmation email
with a 48-hour link; only after it is confirmed does a subscriber record
exist. Stored fields, nothing else: email address, plan id, page language,
confirm/unsubscribe tokens, timestamps. One-click unsubscribe (link in every
notification) deletes the record immediately - no flag, no archive. Pending
records expire after 48 hours. No content logging, no sharing.

Storage: Vercel KV (Upstash Redis), region eu-central-1 (Frankfurt), free
tier, no card. Retention: a record lives only until unsubscribe.

A daily Vercel cron GETs `/api/send_plan_email?action=notify` with
`Authorization: Bearer $CRON_SECRET`; subscribers get a mail (in their page
language) when the plan's objection deadline is within 7 days or its status
changed.

## Email languages

The email is composed in the language of the page the visitor used
(`lang` field: he/en/ar/ru/am/fr; unknown values fall back to Hebrew).
Hebrew is the source of truth; the rest are machine drafts pending
native-speaker review (issue #942). The signature is always
"reihlinstinct".

### Abuse protection

- Honeypot field `website`: a filled honeypot gets a fake success and no send.
- Per-IP hourly throttle and a global daily cap, both in-memory per
  serverless instance (they reset on cold start; Gmail's own ~500/day SMTP
  cap is the hard backstop).
- Cloudflare Turnstile can be added later behind `REQUIRE_TURNSTILE`.
- Responses are generic (no account enumeration); recipient addresses are
  never logged.

### Deployment

Draft only: do not deploy or connect Vercel until the owner approves. The
form page reads the function URL from `EMAIL_ENDPOINT` in
`src/ginot/page_email.py` - the one place to update after deployment.
