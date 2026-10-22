# Changelog

## [0.2.1] - 2026-10-22

- #283: Fix random-area citywide popups; preserve displayed-plan boundary clicks

## [0.2.0] - 2026-10-22

- Semantic version baseline, bilingual release notes and visible footer version.
- Map matches visible table rows, live boundary controls and smallest-plan overlap selection.
- Permit filters restored, closed requests hidden by default.
- Per-review automatic sharing cards, favicon fallbacks and visible statistics bars.
- Checkpoint recovery and strict-branch publication fixes; regression evidence required for every Bug.
- Hebrew/English release notes: releases/0.2.0.md.


## 2026-10-22

- Optional mobile map below the tables: real representative plan points on OSM,
  table-filter sync, status colors and toggleable legend. Selected boundaries
  load live in the visitor browser; no stored boundary export (#253).

- Harden permit scan recovery: resume completed parcel checkpoints, persist
  detail progress, retry failed checkpoint writes and stop if no durable save
  is confirmed. Existing checkpoint format and scan schedule unchanged (#251).

Notable changes to the tracker and the public site. Every change also has an
issue + PR record in this repo.

## 2026-10-21

- Permit scan backfill doubled: two 280-parcel windows daily, 03:00 +
  09:00 UTC (06:00/12:00 Israel); same cursor/checkpoint logic, no
  double-scanning, enrichment runs share the single queue (#211, PR #212).

- Site restyled in the Ginot HaIr palette (navy/mint), owner-approved mockup (#154, PR #161).
- Plans table: inside/partial column hidden (filter kept); new "סקירת AI"
  column linking plans that have an AI-generated review (#162, PR #163).
- index.html slimmed: full plan rows ship as `rows.html`, full permit rows as
  `permits.html`, both fetched client-side; 20 embedded rows + noscript
  fallback each (#164 PR #165, #169 PR #171). Page weight 581KB -> ~64KB.
- AI reviews render as styled RTL site pages at build time from the repo .md;
  the column links them instead of raw GitHub markdown (#177, PR #178).
- Footer: GitHub link text shortened (#167, PR #168); "שינויים אחרונים" in a
  card like the urgent row (#175, PR #176).
- New combined About page: about text + data-sources table + datasets list
  (moved off the main page); sources.html redirects (#173 PR #174, #183 PR #184).
- Folder-driven `docs/index.json` for the datasets list, no dedicated Action
  (#152); client-side urgent row (#153); scan checkpointing to survive runner
  loss (#155).
- Early-stage permit enrichment backfill complete: 1,123/1,123 tiks (#145, PR #146).
- Parcel scan batch 500 -> 280 to fit the runner timeout (#147, PR #148).
- weekly-refresh publish: waits for a mergeable state and updates the PR
  branch (main can move during the long fetch); authenticates with the
  REFRESH_DISPATCH_TOKEN repo secret so refresh PRs trigger CI (#170, PRs
  #172, #181, #182).

## Earlier

- Public site, weekly refresh, diff/feed/badges, planner tracking - see git
  history and issues #1-#150.

## 2026-10-21 - open.json + API section
- `docs/open.json`: public static endpoint of open plans (still in the planning process; definition A: station_desc != "אישור"), each row with `in_objection_period`; regenerated on every refresh (issue: open plans API, owner request).
- About page: new "גישה לנתונים (API)" section documenting data.json / open.json / feed.xml / badge endpoints.

## 2026-10-21 - favicon, API worker, API docs
- Site favicon on all pages (issue #192, PR #193): stylised garden tree in the site palette (SVG + PNG + apple-touch-icon), regeneration script `scripts/make_favicon.py`.
- Read-only API query layer as a free Cloudflare Worker (issue #197, PR #198): `https://ginot-hair-api.reihlinstinct.workers.dev` - `/plans`, `/permits`, `/open`, `/status` with substring filters; CORS open; 5-min edge cache; best-effort rate limit. Node tests + CI job.
- README: new "Data API" section (English + Hebrew) documenting the static endpoints and the Worker with curl examples.

## 2026-10-21 - Cloudflare Pages mirror, quota-limited
- Cloudflare Pages mirror at https://ginot-hair-plans.pages.dev (GitHub-app integration on this repo only; reports builds as the "Cloudflare Pages" check run).
- Quota limiting (owner request): the mirror's production branch is `mirror`; the weekly-refresh publish step pushes main to `mirror` after merging, so the mirror builds only on the weekly refresh or a manual run - not on every push. PR previews disabled in the project's branch controls.
- README: "Mirrors" section documents the setup.

- Fix statistics bar charts: restore visible track/fill CSS with responsive label
  widths and text counts; regression checks at 390px and 1280px (#256).
