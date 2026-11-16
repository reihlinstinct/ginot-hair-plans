# Security Policy

## Reporting a vulnerability

Please open a private security advisory on this repository
(Security → Advisories) rather than a public issue: https://github.com/reihlinstinct/ginot-hair-plans/security/advisories/new

Languages: Hebrew or English. No personal email is published on purpose.
Machine-readable copy (RFC 9116): `docs/.well-known/security.txt`, also served by the
Cloudflare Workers at `/.well-known/security.txt`. It expires 2027-10-01 and is renewed before then.

## Scope notes

- No credentials, tokens or personal data belong in this repo; it is scanned
  with GitHub secret scanning + push protection.
- Plan data is derived from the Israel Planning Administration public API;
  the derived council boundary polygon comes from a municipal GIS export and
  is geometry only (no personal data).
- The planner's tracking-state file (data/plan_status.json) is intentionally
  gitignored and never published.
