# Changelog

Notable changes to the tracker and the public site. Every change also has an
issue + PR record in this repo.

## 2026-10-21

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
