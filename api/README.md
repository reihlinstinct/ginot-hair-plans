# api/ - Vercel serverless functions

## send_plan_email.py

On-demand plan-objection email. The site's `email.html` form posts
`{email, plan_number, lang, subscribe}` here. Nothing is sent to the typed
address until its owner confirms: the function stores a pending record
(deleted on confirmation or after 48 hours) and sends one confirmation email;
the link opens a page with a button, and only the button's POST sends the
plan email (plan number/name, status, objection deadline, mavat link,
how-to-object pointer) in the page's language over SMTP. Without storage
(`KV_REST_API_*` unset) the endpoint answers 503 and sends nothing. The
address is stored only as described under Subscriptions, and is never logged.

### Sender account: how to swap it (no code change)

Everything about the sender is a Vercel environment variable. To move the
sender to another account or provider, change these in the Vercel project
settings (Environment Variables) and redeploy - no code change:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `465` | SMTP port (465 = SSL, 587 = STARTTLS) |
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
| `ALLOWED_ORIGIN` | `https://reihlinstinct.github.io` | CORS origin for the form |
| `PER_IP_HOURLY_CAP` | `3` | Per-IP hourly request cap (KV counter) |
| `PER_RECIPIENT_DAILY_CAP` | `3` | Per-address daily cap (hashed key) |
| `DAILY_SEND_CAP` | `50` | Global daily cap, counting every message sent |
| `BASE_URL` | project `.vercel.app` origin | Base for confirm/unsubscribe links |
| `CRON_SECRET` | - (required for notify) | Bearer secret for the daily cron call |
| `KV_REST_API_URL` / `KV_REST_API_TOKEN` | unset | Vercel KV (Upstash) storage; unset = the endpoint refuses (503) |

## Subscriptions (privacy-first)

Every request is double opt-in (see above). Ticking subscribe makes the same
confirmation also create a subscriber record. Stored fields, nothing else:
email address, plan id, page language, tokens, timestamps, last status seen.
Unsubscribe is a page with a POST button (GET never changes state, so mail
scanners cannot trigger it), plus RFC 8058 `List-Unsubscribe-Post` headers on
every subscriber email; it deletes the record immediately - no flag, no
archive. Pending records expire after 48 hours. No content logging, no
sharing.

Storage: Vercel KV (Upstash Redis), region eu-central-1 (Frankfurt), free
tier, no card. Retention: a pending record lives until confirmation or 48h;
a subscription lives until unsubscribe. See `API_PRIVACY.md`.

`vercel.json` configures a daily Vercel cron (05:00 UTC) that calls
`/api/send_plan_email?action=notify` with `Authorization: Bearer
$CRON_SECRET`; subscribers get a mail (in their page language) once when a
plan's objection deadline is within 7 days, and on every status change.

## Email languages

The email is composed in the language of the page the visitor used
(`lang` field: he/en/ar/ru/am/fr; unknown values fall back to Hebrew).
Hebrew is the source of truth; the rest are machine drafts pending
native-speaker review (issue #942). The signature is always
"reihlinstinct".

### Abuse protection

- Confirm-before-send: no mail reaches an address whose owner has not pressed
  the confirm button; the one unconfirmed message is the confirmation.
- Honeypot field `website`: a filled honeypot gets a fake success and no send.
- Strict address check (single `@`, no `,;<>`, whitespace or control chars).
- KV-backed atomic counters shared by all instances: per-IP hourly,
  per-recipient daily (hashed) and a global daily cap, counting every message
  sent. The client IP is the platform-set `x-vercel-forwarded-for` header.
- Gmail's own ~500/day SMTP cap remains the last backstop.
- Cloudflare Turnstile can be added later behind `REQUIRE_TURNSTILE`.
- Responses are generic (no account enumeration); recipient addresses are
  never logged.

### Deployment

Production (`main`) deploys the function. Scope `SMTP_PASSWORD` and
`CRON_SECRET` to Production only, so branch previews cannot send mail. The
form page reads the function URL from `EMAIL_ENDPOINT` in
`src/ginot/page_email.py` - the one place to update if the domain changes.
