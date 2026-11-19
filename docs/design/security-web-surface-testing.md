# Web surface testing plan: static-site DAST and container scan (#126)

Plan only; implementation lands as its own reviewed PR per the standard
gates. The repo's only web surface is the static GitHub Pages site built
into `docs/` - there is no server, no API backend and no auth surface of our
own. That shapes everything below.

## Scope and non-goals

- In scope: passive baseline scanning of a local build of `docs/`,
  documentation of the hosting limits, and a container scan trigger
  condition.
- Out of scope: active/attack scanning (nothing stateful to attack, and ZAP
  active mode against a static mirror tests ZAP, not the site), scanning the
  live site from CI (adds no signal over a local build and generates traffic
  we do not need), and any change to Pages hosting configuration (not ours
  to change).

## 1. ZAP baseline in CI against a local build

- Job shape: build the site exactly as `pages.yml` does, serve `docs/` with
  a throwaway local HTTP server on the runner, run the ZAP baseline action
  (passive-only rules) against `http://127.0.0.1:<port>`, upload the report
  as a build artifact.
- Determinism rules: pin the ZAP action and Docker image by digest like
  every other action in this repo; fail the job on new WARN or FAIL findings
  only, with a checked-in rules file for any accepted finding (each with a
  one-line justification, mirroring the ruff ratchet style - entries only
  shrink).
- Locale matrix: the scan covers `docs/` including the localized trees
  (`am/`, `ar/`, `en/`, `fr/`, `ru/`), since each carries its own markup.
- Budget: passive baseline over the full tree must stay inside the job's
  timeout; if the growing `permits.html` pages (14-16 MiB each today) push
  it over, scan one representative locale's permits page plus all
  non-permits pages, and record the sampling decision in the job comment.
- No secrets, tokens or municipal endpoints are involved; the scan touches
  only files already published on the site.

## 2. Security headers: out of our control on Pages (documented)

GitHub Pages serves the site; response headers (`Content-Security-Policy`,
`X-Frame-Options`, `Strict-Transport-Security` and friends) are set by the
hosting platform and cannot be configured from this repository. Consequences:

- The ZAP baseline WILL flag missing headers. Those findings are expected,
  listed in the checked-in rules file with a link to this section, and never
  treated as site defects.
- What IS ours stays tested: markup-level hardening we control
  (`referrer` meta, `rel="noopener"` on outbound links, no inline event
  handlers) is covered by the existing pytest/Playwright suites; new
  markup-level expectations go there, not into the DAST rules file.

## 3. Container scan: trigger condition, not a job yet

No Dockerfile exists in the repo today (#115/#116 will add the first ones).
When the first Dockerfile lands, that PR (or its immediate follow-up) adds a
Trivy image scan job: build the image in CI, scan with a digest-pinned Trivy
action, fail on CRITICAL/HIGH unless a checked-in `.trivyignore` entry
carries a justification and an expiry date. Until then there is nothing to
scan and no placeholder job is added.

## Acceptance for the implementing PR

- Baseline job runs green on a clean tree and demonstrably fails when a
  seeded WARN-level finding is introduced (one seeded-fixture test run shown
  in the PR, not committed).
- Rules file entries carry justifications; header findings reference
  section 2.
- Report artifact uploaded on every run; counts-only in job logs (no page
  bodies).
- No increase to CI minute budget beyond one short job on PRs touching
  `docs/` and a weekly full run.
