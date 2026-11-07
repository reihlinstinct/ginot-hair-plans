# Branch-cleanup checklist

## Protected deployment branches

"Protected" here means excluded from cleanup. This checklist does not create
or change GitHub branch-protection rules or repository settings.

| Branch | Purpose | Cleanup rule |
| --- | --- | --- |
| `main` | Default branch and reviewed source for the primary GitHub Pages site | Never delete |
| `mirror` | Production branch of Cloudflare Pages project `ginot-hair-plans`, serving `https://ginot-hair-plans.pages.dev/` from `docs/` | Never delete |

`mirror` is operational even when its tip is an ancestor of `main`, no PR uses
it as a head, or no workflow currently pushes it. The Cloudflare production
branch is an external setting, not a GitHub Pages environment pin. The
[reviewed publication procedure](data-publication.md#cloudflare-production-branch-keep-mirror)
explains the separate mirror continuation.

## Before deleting any other branch

- Read the current branch list, default branch and branch-protection rules.
  Exclude the protected deployment branches above from every candidate list.
- Inspect current GitHub Pages and environment branch policies, workflow refs,
  and external deployment projects such as Cloudflare Pages. Check repository
  documentation for operational branch references too. Do not restrict the
  check to workflow checkout refs or dismiss a documented deployment target
  because no workflow currently pushes it.
- Check open PRs, merged PR heads and current branch tips. Being fully merged
  or having a merged PR is not proof that a branch is unused. Preserve data, ledger, baseline, evidence and other
  operational branches unless their purpose has been checked and deletion is
  explicitly authorized.
- If a deployment setting cannot be inspected, a reference is ambiguous, or a
  branch has a purpose not covered by the cleanup approval, keep the branch and
  report the gap. Do not delete it to test whether anything still depends on it.
- Record the candidate branch, tip SHA and reason before the authorized delete.
  Recheck that the ref has not moved, then verify the result. Do not change
  deployment settings or branch-protection rules as part of cleanup.

## Incident reference

On 3 November 2026 at 10:34 Asia/Jerusalem, `mirror` was deleted during a
merged-branch cleanup despite remaining the Cloudflare production target. The
site stayed on its last successful 25 October deployment. On 7 November the
branch was restored at the reviewed main commit and Cloudflare production was
verified current. See [the branch activity](https://github.com/reihlinstinct/ginot-hair-plans/activity?ref=mirror).
