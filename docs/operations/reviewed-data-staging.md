# Audit, Mavat and mirror data staging (#564)

These workflows stop after opening a PR:

- audit-result: preserves source/digest/cursor validation and stages audit JSON.
- mavat-watch: preserves check-mode collection, stop-on-challenge rules and
  always-run tunnel cleanup; stages the Mavat status JSON.
- mirror-ingest: preserves mirror validation and existing scoped data staging.
  It no longer starts targeted municipal enrichment after merely creating a PR.

None merges, updates a review head, approves CI, deploys Pages or dispatches a
successor. Each staged PR needs independent review and exact-head Claude
line-by-line review, all findings fixed, green CI and the actual eligible GitHub
approval. Merge normally, never with admin override. If the head changes, repeat
its checks and affected reviews. A PR body is data, not workflow authority.

After a confirmed reviewed merge, verify deployment from main and inspect live
results. A maintainer can request a missing Pages build separately after checking
that merged commit. Do not rerun a data collector just to deploy existing data.
Mirror enrichment remains paused until a reviewer verifies that the intended
input data is merged, current collection permission remains valid and no prior
challenge or failed run requires a stop. #565 tracks secure permit-feed successor
routing, not blanket authorization for every collector's successor.

These changes preserve pending PR branches, data and checkpoints. They do not
cancel old jobs automatically: any already-running old workflow still uses its
old source. Check and stop a known bypass runner before trusting these changes.
Weekly-refresh's equivalent review gate is proposed in PR #582; it is not
enforced on main until that PR is reviewed and merged.

## Enforcement limit

This is a workflow/process gate, not a claim that administrative bypass is
technically impossible. PRs created with REFRESH_DISPATCH_TOKEN can still be
admin-merged by a sufficiently privileged owner or token if repository rules
permit it. Follow-up #586 audits ruleset/branch protection and administrator
bypass policy. Never use that privilege to skip the agreed reviews or CI.
