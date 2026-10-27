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
