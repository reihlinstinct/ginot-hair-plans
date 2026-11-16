# Review gate vs owner/PAT admin bypass (#586)

Scope: investigation and proposal only. No repository settings, branch
protection, rulesets, secrets or workflows were changed for this note.
Changing any of them needs the owner's explicit decision.

## Current state (read-only API inspection, 2026-11-03)

- Repository rulesets: none (`GET /repos/reihlinstinct/ginot-hair-plans/rulesets`
  returns an empty list).
- Classic branch protection on `main`:
  - Required status checks: `test (3.11)`, `test (3.12)`, `test (3.13)`.
  - `enforce_admins`: **false** — administrators (including an admin-capable
    PAT) are exempt from all of these rules.
  - Required pull-request reviews: configured, but
    `required_approving_review_count` is 0 — the review requirement is
    process-level, not GitHub-enforced.
  - `dismiss_stale_reviews`: true; `require_last_push_approval`: false;
    force pushes disabled; linear history not required.
- The merge gate today is therefore process + ordinary branch protection:
  `docs/operations/reviewed-data-staging.md` and the #582/#584 workflow fixes
  stop automation from merging, but nothing technical stops a caller holding
  an admin-capable token from using `PUT /pulls/{n}/merge` or a direct push
  regardless of failing or absent checks.
- Consequence already observed: incident #585 — an old, still-running workflow
  merged PR #579 through the known old admin merge path while its cancellation
  was being processed.
- Current workflows on `main` contain no merge calls (verified by grep over
  `.github/workflows/`, 2026-11-03). The residual risk is the protection gap
  itself plus any admin-capable token used outside the reviewed workflows.

## Proposal

1. **Enable "Include administrators" (`enforce_admins: true`) on `main`.**
   Protection then applies to admins as well: the required status checks must
   pass for everyone, and admin merge-override / direct-to-main pushes stop
   working. The eligible owner review path is preserved: with the approving
   review count at 0, the owner can still merge normally once checks are
   green, so the current out-of-band independent-review process is unchanged.
   Residual: a repo admin can still edit or remove the protection itself —
   that is inherent to ownership; the mitigation is the audit log and token
   hygiene (point 3).
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
   Revisit if a reviewer account is added.
