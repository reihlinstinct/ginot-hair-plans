# workers.dev API hostname: legacy TLS review (#1005)

Research findings only; no infrastructure change. Observation (from the
issue, SSLyze 6.3.1 configuration-only scan, 2026-11-15):
`ginot-hair-api.reihlinstinct.workers.dev` accepts TLS 1.0 and 1.1 (two
cipher suites each) as well as 1.2/1.3; SSLv2/v3 rejected; certificate
chain valid. This is transport hardening for a read-only public-data API,
not an exploitable application vulnerability. Modern clients can already
use TLS 1.2/1.3.

## What Cloudflare exposes for a workers.dev hostname (checked 2026-11-18)

- Cloudflare's own docs describe the `workers.dev` subdomain as "treated as
  a Free website", intended for personal/hobby projects, and recommend
  running production Workers on a Workers route or **custom domain**
  instead (https://developers.cloudflare.com/workers/configuration/routing/workers-dev/).
- The minimum-TLS-version setting is a **zone-level** control. The
  `workers.dev` zone is managed by Cloudflare, not onboarded to the
  account, so there is no documented per-hostname minimum-TLS control for
  `<worker>.<account>.workers.dev` hostnames. Community confirmation:
  https://www.answeroverflow.com/m/1121189760334049342 ("you can change the
  minimum TLS version for the whole zone ... not for a specific hostname").
- Cloudflare documents an in-Worker alternative, the official "Block on
  TLS" example: inspect the incoming request's TLS version
  (`request.cf.tlsVersion`) and reject handshakes below TLSv1.2
  (https://developers.cloudflare.com/workers/examples/block-on-tls). This
  enforces at the application layer after the handshake, so old TLS is
  still *accepted at the edge* and then refused - it raises the effective
  floor for API responses but does not remove the edge listener.

Conclusion for acceptance criterion 1: no setting on an unrelated
user-owned zone changes Cloudflare's managed workers.dev zone. The controls
that exist are (a) in-Worker TLS-version refusal and (b) serving the API
from an owned custom domain on an account zone where minimum TLS 1.2 is
configurable.

## Options (no decision taken here)

- **A. In-Worker refusal**: add the documented `cf.tlsVersion` check to the
  API worker (code lives outside this repo). Zero cost, no DNS change;
  old TLS still terminates at the edge, responses are refused. A rollback
  is a one-line revert.
- **B. Owned custom domain**: move the API hostname onto an existing
  account-owned Cloudflare zone, set minimum TLS 1.2 there. Compatibility
  check first: any client pinned to the workers.dev hostname breaks; keep
  the workers.dev route answering during migration and record a rollback
  (re-point the custom hostname, keep the worker route). No-cost on the
  existing plan, pending confirmation the account holds a suitable zone.

Either way, the fix belongs to the API worker's own deployment, not to this
repo's Pages site; this document only records the verified control surface.

## Sources

- Cloudflare Workers docs, workers.dev routing (fetched 2026-11-18):
  https://developers.cloudflare.com/workers/configuration/routing/workers-dev/
- Cloudflare Workers example "Block on TLS" (listed in the official Workers
  docs index, fetched 2026-11-18):
  https://developers.cloudflare.com/workers/examples/block-on-tls
- AnswerOverflow archive of the Cloudflare Discord thread on per-hostname
  minimum TLS for workers.dev (secondary):
  https://www.answeroverflow.com/m/1121189760334049342
