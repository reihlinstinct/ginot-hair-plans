# Review gate vs owner/PAT admin bypass (#586)

Scope: investigation, proposal and status record. No repository settings were
changed by this note or its PRs. The owner approved the one hardening change
(`enforce_admins`) explicitly and it was applied through the settings UI on
2026-11-16; any further settings change needs the owner's explicit decision.

## Current status (2026-11-16)

`enforce_admins` (**"Do not allow bypassing the above settings"**) is now
**enabled** on `main`. Verified two ways on 2026-11-16:

- Branch-protection rule UI: the toggle is on and persisted across reload;
  the rule is otherwise unchanged (required checks remain `test (3.11)`,
  `test (3.12)`, `test (3.13)`; approving-review count 0; dismiss-stale on;
  strict off; force pushes and deletions stay disabled).
- Read-only API corroboration that does not need Administration permission:
  `GET /branches/main` reports `required_status_checks.enforcement_level:
  "everyone"` (GitHub reports `non_admins` when admins are exempt), and
  `GET /rulesets` and `GET /rules/branches/main` both return empty lists, so
  no ruleset overrides this.

Admin merge-override and direct-to-main pushes by admin tokens are now blocked
by GitHub for operations that do not satisfy the protection rule, not only by
process. With the approving-review count at 0, the owner can still merge
normally once checks are green, so the current out-of-band independent-review
process is unchanged. The residual owner-settings path from proposal point 1
below remains inherent to ownership.

## State as of 2026-11-03 (superseded, see Current status)

Read-only API inspection on 2026-11-03, before the owner's change:

- Repository rulesets: none (`GET /repos/reihlinstinct/ginot-hair-plans/rulesets`
  returned an empty list).
- Classic branch protection on `main`:
  - Required status checks: `test (3.11)`, `test (3.12)`, `test (3.13)`.
  - `enforce_admins`: **false** — administrators (including an admin-capable
    PAT) were exempt from all of these rules.
  - Required pull-request reviews: configured, but
    `required_approving_review_count` was 0 — the review requirement was
    process-level, not GitHub-enforced.
  - `dismiss_stale_reviews`: true; `require_last_push_approval`: false;
    force pushes disabled; linear history not required.
- The merge gate then was process + ordinary branch protection:
  `docs/operations/reviewed-data-staging.md` and the #582/#584 workflow fixes
  stopped automation from merging, but nothing technical stopped a caller
  holding an admin-capable token from using `PUT /pulls/{n}/merge` or a
  direct push regardless of failing or absent checks.
- Consequence already observed: incident #585 — an old, still-running workflow
  merged PR #579 through the known old admin merge path while its cancellation
  was being processed.
- Workflows on `main` contained no merge calls (grep over
  `.github/workflows/`, 2026-11-03; re-verified 2026-11-16, still none). The
  residual risk was the protection gap itself plus any admin-capable token
  used outside the reviewed workflows.

Notes on what can no longer be re-read directly: the fine-grained automation
PAT gets 403 on `GET .../branches/main/protection` (no Administration read),
and the write-permission collaborator token gets the same 403. The 2026-11-16
UI check plus the `enforcement_level: "everyone"` field above are the current
verification path for future re-checks.

## Proposal

1. **Enable "Include administrators" (`enforce_admins: true`) on `main` (done 2026-11-16, owner-approved).**
   Protection now applies to admins as well: the required status checks must
   pass for everyone, and admin merge-override / direct-to-main pushes no
   longer work. The eligible owner review path is preserved: with the
   approving review count at 0, the owner can still merge normally once
   checks are green, so the current out-of-band independent-review process is
   unchanged. Residual: a repo admin can still edit or remove the protection
   itself — that is inherent to ownership; the mitigation is the audit log
   and token hygiene (point 3).
2. **Optionally migrate to a repository branch ruleset targeting `main`**
   with bypass actors set to none. Rulesets make bypass explicit and
   auditable and show enforcement status in the UI; the effect is equivalent
   to point 1 through a newer surface.
3. **Token hygiene.** The #585 path existed because a broad token was
   available to automation. Prefer fine-grained PATs without admin rights for
   automation, and keep admin-capable tokens out of workflows.
4. **Not recommended now:** `required_approving_review_count >= 1` or
   `require_last_push_approval: true`. Both would encode the
   "fresh review at exact head" rule in GitHub mechanics, but they require an
   approving reviewer identity on GitHub; the independent review is currently
   out-of-band (relayed), and a sole owner cannot approve their own PR, so
   enabling either would block all merges until a reviewer identity exists.
   Revisit if a reviewer account is added. Note (2026-11-16): collaborator
   `reihl` (write) now relays the out-of-band independent review as a formal
   COMMENTED review on the exact head; switching that lane to APPROVED so
   GitHub could enforce it remains an owner decision, since it changes merge
   mechanics for every PR.
