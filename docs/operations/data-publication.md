# Reviewed data publication

## Weekly refresh (#564)

The weekly-refresh workflow fetches public data, renders the site and opens a
PR. It stops there. A successful fetch or green CI is not approval to publish.
Existing generated files stay in that PR until reviewed. Do not rerun the fetch
just to complete a review or deploy an already-reviewed result.

Before merging, inspect the complete current diff, resolve every finding from
both the independent reviewer and the exact-head Claude line-by-line review,
and verify required CI on that same head. Obtain the repository's actual eligible
approving review. Use a normal merge, never an admin override. If the head moves,
repeat the affected reviews and checks.

After the reviewed merge is confirmed, verify the deployed site's data and dates.
GitHub Pages may already deploy from the normal merge. If a build request is
needed, a maintainer may request it after verifying the merged commit on main.
The fetch workflow no longer requests builds or advances the Cloudflare mirror.
Do not force-push the mirror from a still-running fetch job. Any manual mirror
continuation must use the confirmed reviewed main commit and check current mirror
state first; deploy and verify it separately. Until that continuation is performed,
the mirror may lag main. No callback or PR body text authorizes a scan, deployment,
or successor workflow.

This change does not remove the remaining legacy publication paths tracked in
#564 (audit-result, mavat-watch and mirror-ingest). Those need their own reviewed
fixes. Permit-feed successor routing remains fail-closed pending #565.

## One pending data PR at a time (#564)

weekly-refresh, mavat-watch (check mode) and mirror-ingest each start with a
read-only `pending` job. It runs `scripts/ci/pending_data_pr.py` with the
branch prefix that the workflow pushes (`weekly-refresh/`, `mavat-check/`,
`mirror-ingest/`). The data job runs only after a `pending=false` verdict, so no
fetch, VPN or tunnel starts and no second PR is stacked while one still waits
for review.

- **A PR is still open:** the run ends green with a `::notice::` that gives
  only its PR numbers. Review and merge, or close, that PR. Do not cancel it
  just to let a new fetch run.
- **The guard can't decide:** the run is red and fetches nothing (fail
  closed). This covers any API error, a malformed page, or more than 5,000
  open PRs.
- **Which PRs count:** all pages are read. Only same-repository heads count.
  Fork PRs and PRs from deleted forks are ignored.

Mavat discover mode never stages a PR, so it is exempt.
`tests/test_no_review_bypass.py` scans every workflow and CI script for merge,
approval, dispatch, re-run, Pages and default-branch or mirror push forms. Its
allowlist names each remaining exception with a reason.
